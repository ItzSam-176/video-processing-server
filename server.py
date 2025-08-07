
import os
import uuid
import traceback
import tempfile
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageColor
from pilmoji import Pilmoji

#Memory Optimization
import gc
import psutil

#Filter
import colorsys
from scipy import ndimage

#Subtitles
import whisper
import json
from moviepy.video.tools.subtitles import SubtitlesClip
WHISPER_MODEL = None


app = Flask(__name__)
CORS(app)

PROCESSED_FOLDER = 'processed'
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Memory optimization function
def optimize_memory():
    """Force garbage collection to free memory"""
    gc.collect()
    if hasattr(gc, 'set_threshold'):
        gc.set_threshold(700, 10, 10)

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024



#Subtitles
def load_whisper_model(model_size="base"):
    """Load Whisper model once for reuse"""
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        print(f"[WHISPER] Loading {model_size} model...")
        WHISPER_MODEL = whisper.load_model(model_size)
        print("[WHISPER] Model loaded successfully")
    return WHISPER_MODEL

def generate_subtitles_with_whisper_trimmed(video_path, language="auto", translate_to_english=False, trim_start=0, trim_end=None):
    """
    Generate auto-subtitles for TRIMMED video portion with proper timing synchronization
    """
    temp_trimmed_video = None
    audio_path = None
    try:
        print(f"[WHISPER] Starting subtitle generation for trimmed portion: {trim_start}s to {trim_end}s")
        
        # ✅ STEP 1: Create trimmed video first
        original_clip = VideoFileClip(video_path)
        
        # ✅ FIX: Handle end_time properly - don't override with arbitrary value
        if trim_end is None:
            trim_end = original_clip.duration
        
        # ✅ CRITICAL FIX: Use the actual trim_end value, don't recalculate
        print(f"[WHISPER] Original video duration: {original_clip.duration}s")
        print(f"[WHISPER] Using trim range: {trim_start}s to {trim_end}s")
        print(f"[WHISPER] Expected trimmed duration: {trim_end - trim_start}s")
        
        # Create trimmed clip with correct end time
        trimmed_clip = original_clip.subclip(trim_start, trim_end)
        
        # Save trimmed video to temp file
        temp_trimmed_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        trimmed_clip.write_videofile(
            temp_trimmed_video.name,
            verbose=False,
            logger=None,
            audio_codec='aac'
        )
        temp_trimmed_video.close()
        
        # Clean up clips
        trimmed_clip.close()
        original_clip.close()
        
        print(f"[WHISPER] Created trimmed video: {temp_trimmed_video.name}")
        print(f"[WHISPER] Trimmed duration: {trim_end - trim_start}s")
        
        # ✅ STEP 2: Generate subtitles from trimmed video (timing will be 0-based)
        model = load_whisper_model("tiny")
        
        # Extract audio from trimmed video
        audio_path = extract_audio_for_whisper(temp_trimmed_video.name)
        
        # Define task
        task = 'translate' if translate_to_english else 'transcribe'
        
        # Transcribe trimmed audio (timing starts from 0)
        result = model.transcribe(
            audio_path, 
            task=task,
            language=None if language == "auto" else language,
            verbose=False,
            word_timestamps=True,
            temperature=0,
            no_speech_threshold=0.3,
            logprob_threshold=-0.8,
            condition_on_previous_text=False,
            initial_prompt="This is a song with lyrics and music."
        )
        
        print(f"[WHISPER] Detected language: {result.get('language', 'unknown')}")
        print(f"[WHISPER] Found {len(result['segments'])} raw segments")
        
        # ✅ STEP 3: Process subtitles (already 0-based from trimmed video)
        subtitles = []
        MAX_CHARS_PER_SUBTITLE = 50
        MAX_WORDS_PER_SUBTITLE = 8
        
        for i, segment in enumerate(result['segments']):
            start_time = segment['start']  # Already 0-based
            end_time = segment['end']      # Already 0-based
            text = segment['text'].strip()
            
            print(f"[WHISPER] Segment {i}: {start_time:.2f}s-{end_time:.2f}s: '{text}'")
            
            if not text:
                continue
            
            # Split long text into shorter segments
            if len(text) > MAX_CHARS_PER_SUBTITLE or len(text.split()) > MAX_WORDS_PER_SUBTITLE:
                split_subtitles = split_long_subtitle(text, start_time, end_time, MAX_CHARS_PER_SUBTITLE, MAX_WORDS_PER_SUBTITLE)
                subtitles.extend(split_subtitles)
                print(f"[WHISPER] Split long text: '{text[:30]}...' into {len(split_subtitles)} parts")
            else:
                subtitles.append(((start_time, end_time), text))
        
        print(f"[WHISPER] Generated {len(subtitles)} subtitle segments for trimmed video (0-based timing)")
        
        return {
            'subtitles': subtitles,
            'language': result.get('language', 'unknown'),
            'segments_count': len(subtitles),
            'trim_start': trim_start,
            'trim_end': trim_end,
            'trimmed_duration': trim_end - trim_start
        }
        
    except Exception as e:
        print(f"[WHISPER] Trimmed subtitle generation failed: {e}")
        raise e
    finally:
        # Cleanup
        if temp_trimmed_video and os.path.exists(temp_trimmed_video.name):
            try:
                os.unlink(temp_trimmed_video.name)
                print("[WHISPER] Cleaned up trimmed video file")
            except Exception as cleanup_error:
                print(f"[WHISPER] Trimmed video cleanup warning: {cleanup_error}")
                
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
                print("[WHISPER] Cleaned up extracted audio file")
            except Exception as cleanup_error:
                print(f"[WHISPER] Audio cleanup warning: {cleanup_error}")

def fill_timeline_gaps(segments, audio_duration, gap_threshold=2.0):
    """
    Fill gaps in timeline where Whisper didn't detect speech
    """
    if not segments:
        return segments
    
    filled_segments = []
    previous_end = 0
    
    for segment in segments:
        current_start = segment['start']
        
        # If there's a significant gap, add a silence marker
        if current_start - previous_end > gap_threshold:
            gap_segment = {
                'start': previous_end,
                'end': current_start,
                'text': '[Music]'  # Optional: mark as music/silence
            }
            # Only add if you want to show music indicators
            # filled_segments.append(gap_segment)
        
        filled_segments.append(segment)
        previous_end = segment['end']
    
    # Handle gap at the end
    if audio_duration - previous_end > gap_threshold:
        final_segment = {
            'start': previous_end,
            'end': audio_duration,
            'text': '[Music]'
        }
        # filled_segments.append(final_segment)
    
    return filled_segments

def get_audio_duration(audio_path):
    """Get duration of audio file"""
    try:
        import librosa
        y, sr = librosa.load(audio_path)
        return len(y) / sr
    except:
        # Fallback using moviepy
        from moviepy.editor import AudioFileClip
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        audio.close()
        return duration


def split_long_subtitle(text, start_time, end_time, max_chars, max_words):
    """
    Split long subtitle text into shorter segments with proper timing
    """
    words = text.split()
    segments = []
    current_segment = []
    duration = end_time - start_time
    
    for word in words:
        # Check if adding this word exceeds limits
        test_segment = current_segment + [word]
        test_text = ' '.join(test_segment)
        
        if len(test_text) > max_chars or len(test_segment) > max_words:
            if current_segment:  # Save current segment
                segment_text = ' '.join(current_segment)
                segment_duration = duration * len(current_segment) / len(words)
                segment_start = start_time + duration * len(segments) * max_words / len(words)
                segment_end = min(segment_start + segment_duration, end_time)
                
                segments.append(((segment_start, segment_end), segment_text))
                current_segment = [word]  # Start new segment
            else:
                # Single word is too long, truncate it
                truncated_word = word[:max_chars-3] + "..."
                segments.append(((start_time, end_time), truncated_word))
                current_segment = []
        else:
            current_segment.append(word)
    
    # Add remaining words
    if current_segment:
        segment_text = ' '.join(current_segment)
        segment_start = start_time + duration * len(segments) * max_words / len(words)
        segments.append(((segment_start, end_time), segment_text))
    
    return segments

def extract_audio_for_whisper(video_path):
    """Extract and enhance audio from video for better Whisper performance"""
    video = None
    try:
        print(f"[WHISPER] Starting audio extraction from: {video_path}")
        
        # ✅ File existence and size validation
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        file_size = os.path.getsize(video_path)
        if file_size == 0:
            raise ValueError(f"Video file is empty: {video_path} (0 bytes)")
        
        print(f"[WHISPER] Video file validated - Size: {file_size / (1024*1024):.2f} MB")
        
        # ✅ Load video with enhanced error handling
        try:
            video = VideoFileClip(video_path)
        except Exception as moviepy_error:
            raise ValueError(f"MoviePy failed to load video: {moviepy_error}")
        
        # ✅ Validate video object
        if video is None:
            raise ValueError("MoviePy returned None - video file may be corrupted or unsupported format")
        
        # ✅ Check video properties
        if not hasattr(video, 'duration') or video.duration <= 0:
            raise ValueError(f"Invalid video duration: {getattr(video, 'duration', 'None')}")
        
        # ✅ Verify audio track exists - ENHANCED ERROR MESSAGE
        if video.audio is None:
            video.close()
            raise ValueError("Video file has no audio track - cannot generate subtitles. This video appears to be silent or recorded without audio.")
        
        print(f"[WHISPER] Video validated - Duration: {video.duration:.2f}s, Size: {video.size}")
        
        # ✅ Extract audio with enhanced settings
        audio_path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        print(f"[WHISPER] Extracting audio to: {audio_path}")
        
        # Enhanced audio extraction for better speech recognition
        video.audio.write_audiofile(
            audio_path, 
            verbose=False, 
            logger=None,
            # ✅ Audio enhancement settings
            codec='pcm_s16le',  # Uncompressed for better quality
            # ffmpeg_params=['-ac', '1']  # Convert to mono for better recognition
        )
        
        # ✅ Optional: Apply audio filtering to enhance vocals
        enhanced_audio_path = enhance_audio_for_speech(audio_path)
        
        # Clean up original if enhanced version was created
        if enhanced_audio_path != audio_path:
            os.unlink(audio_path)
            audio_path = enhanced_audio_path
        
        # ✅ Validate extracted audio file
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise ValueError("Audio extraction failed - output file is empty")
        
        print(f"[WHISPER] Audio extraction successful: {os.path.getsize(audio_path)} bytes")
        
        # Clean up video object
        video.close()
        
        return audio_path
        
    except Exception as e:
        print(f"[WHISPER] Audio extraction failed: {e}")
        # Ensure video object is cleaned up on error
        if video is not None:
            try:
                video.close()
            except:
                pass
        raise e

def enhance_audio_for_speech(audio_path):
    """Enhance audio to improve speech recognition in music"""
    try:
        import subprocess
        enhanced_path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        
        # Use FFmpeg to enhance vocals and reduce background music
        subprocess.run([
            'ffmpeg', '-i', audio_path,
            '-af', 'highpass=f=200,lowpass=f=3000,volume=1.5',  # Filter for vocal range
            '-ac', '1',  # Convert to mono
            '-ar', '16000',  # Whisper's preferred sample rate
            '-y',
            enhanced_path
        ], check=True, capture_output=True)
        
        print("[WHISPER] Audio enhanced for better speech recognition")
        return enhanced_path
        
    except Exception as e:
        print(f"[WHISPER] Audio enhancement failed: {e}, using original")
        return audio_path



def create_subtitle_clip(subtitles, video_width, video_height, font_size=None, font_color='white', bg_color='black'):
    """
    Create MoviePy subtitle clip using your existing text rendering system
    """
    print(f"[DEBUG] Creating subtitle clip with {len(subtitles)} segments")
    for i, subtitle in enumerate(subtitles):
        print(f"[DEBUG] Subtitle {i}: {subtitle[0]} -> '{subtitle[1]}'")
    
    if not font_size:
        # Use your existing aspect-ratio aware sizing
        font_size = get_aspect_ratio_aware_font_size(48, video_width, video_height)
    
    def make_textclip(txt):
        """Generate individual subtitle text clip"""
        print(f"[DEBUG] Creating text clip for: '{txt}'")
        
        # Use your existing text creation function
        text_array = create_text_with_emoji_pilmoji_fixed_macos(
            text=txt,
            font_size=font_size,
            color=font_color,
            bg_color=bg_color,
            size=(video_width, int(video_height * 0.2)),  # Subtitle area
            text_position=None  # Center text
        )
        
        return ImageClip(text_array, transparent=True)
    
    # Create subtitle clip
    subtitle_clip = SubtitlesClip(subtitles, make_textclip)
    
    # Position at bottom of video
    return subtitle_clip.set_position(('center', video_height - int(video_height * 0.15)))

def get_aspect_ratio_aware_font_size(user_size, video_width, video_height, method='proportional'):
    """
    FIXED: Dynamic font scaling that respects user input while providing aspect-ratio awareness
    """
    if not video_width or video_height <= 0:
        return user_size
    
    if method == 'proportional':
        # NEW: Proportional scaling that maintains user control
        aspect_ratio = video_width / video_height
        
        # Base scaling factor on video size vs standard 1080p
        size_factor = min(video_width, video_height) / 1080
        
        # Aspect ratio adjustments (subtle, not overwhelming)
        if aspect_ratio > 1.8:  # Ultra-wide
            ar_factor = 0.9
        elif aspect_ratio > 1.4:  # Wide (16:9)
            ar_factor = 1.0  # No adjustment for most common case
        elif aspect_ratio > 0.7:  # Standard/Square
            ar_factor = 1.0
        else:  # Portrait
            ar_factor = 1.1
        
        # Combine factors with user preference as PRIMARY driver
        final_scale = (size_factor * ar_factor * 0.3) + 0.7  # 30% auto, 70% user choice
        scaled_size = round(user_size * final_scale)
        
        # Reasonable bounds to prevent extremes
        min_size = max(16, round(user_size * 0.6))
        max_size = round(user_size * 1.5)
        
        return max(min_size, min(max_size, scaled_size))
    
    return user_size

def get_recommended_scaling_method(video_width, video_height):
    """Always use proportional for better user experience"""
    return 'proportional'


def load_font_with_size(font_size):
    """Load font with fallback for different systems"""
    font = None
    font_paths = [
        "Arial.ttf",
        "/System/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Times.ttc",
        "/System/Library/Fonts/Courier.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/arial.ttf"
    ]
    
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, font_size)
            print(f"[FONT] Successfully loaded: {path}")
            break
        except Exception as e:
            continue
    
    if font is None:
        font = ImageFont.load_default()
        print("[FONT] Using default font")
    
    return font

def create_text_with_emoji_pilmoji_fixed_macos(text, font_size=48, color='white', bg_color='transparent', 
                                               size=(800, 200), text_position=None):
    """
    FIXED VERSION: Create text image with overflow prevention
    """
    # ✅ Truncate extremely long text
    MAX_DISPLAY_LENGTH = 60
    if len(text) > MAX_DISPLAY_LENGTH:
        text = text[:MAX_DISPLAY_LENGTH-3] + "..."
        print(f"[TEXT] Truncated long text to: '{text}'")
    
    # Create transparent canvas
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load font
    font = load_font_with_size(font_size)

    # Measure text dimensions
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # ✅ Handle text wider than canvas
    if text_w > size[0]:
        print(f"[TEXT] Text too wide ({text_w}px > {size[0]}px), adjusting font size")
        # Reduce font size to fit
        adjusted_font_size = int(font_size * size[0] / text_w * 0.9)  # 90% of calculated size for margin
        font = load_font_with_size(max(12, adjusted_font_size))  # Minimum 12px
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        print(f"[TEXT] Adjusted font size to {adjusted_font_size}px")

    # Use provided position or center if None
    if text_position is not None:
        x, y = text_position
        print(f"[TEXT] Positioning text at exact coordinates: ({x}, {y})")
    else:
        x = (size[0] - text_w) // 2
        y = (size[1] - text_h) // 2
        print(f"[TEXT] Centering text at: ({x}, {y})")

    # ✅ Ensure text stays within bounds
    x = max(0, min(x, size[0] - text_w))
    y = max(0, min(y, size[1] - text_h))

    # Draw background if needed
    if bg_color != 'transparent':
        box_rgb = ImageColor.getrgb(bg_color)
        pad_x = 8
        pad_y = 4
        tb = draw.textbbox((0, 0), text, font=font)
        box_coords = [
            x + tb[0] - pad_x,
            y + tb[1] - pad_y,
            x + tb[2] + pad_x,
            y + tb[3] + pad_y
        ]
        draw.rounded_rectangle(box_coords, radius=4, fill=box_rgb + (255,))

    # Render text with Pilmoji at exact position
    text_rgb = ImageColor.getrgb(color)
    with Pilmoji(img) as pilmoji:
        pilmoji.text((x, y), text, fill=text_rgb, font=font)

    print(f"[TEXT] Text rendered: '{text}' at ({x}, {y}) with font size {font_size}")
    return np.array(img)


#Filter
def apply_video_filter(clip, filter_name):
    """Apply Instagram-style filters to video clips"""
    
    if filter_name == 'none' or not filter_name:
        return clip
    
    print(f"[FILTER] Applying '{filter_name}' filter to video")
    
    # Define filter functions with writable frame copies
    def warm_filter(get_frame, t):
        frame = get_frame(t).copy()  # Make writable copy
        # Increase red/yellow tones, reduce blue
        frame[:,:,0] = np.clip(frame[:,:,0] * 1.15, 0, 255)  # Red boost
        frame[:,:,1] = np.clip(frame[:,:,1] * 1.05, 0, 255)  # Green slight boost  
        frame[:,:,2] = np.clip(frame[:,:,2] * 0.9, 0, 255)   # Blue reduction
        return frame.astype('uint8')
    
    def cool_filter(get_frame, t):
        frame = get_frame(t).copy()  # Make writable copy
        # Increase blue tones, reduce red/yellow
        frame[:,:,0] = np.clip(frame[:,:,0] * 0.85, 0, 255)  # Red reduction
        frame[:,:,1] = np.clip(frame[:,:,1] * 0.95, 0, 255)  # Green slight reduction
        frame[:,:,2] = np.clip(frame[:,:,2] * 1.2, 0, 255)   # Blue boost
        return frame.astype('uint8')
    
    def vintage_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)  # Make writable copy and convert to float
        # Create vintage film look
        frame[:,:,0] *= 1.1  # Slight red boost
        frame[:,:,1] *= 0.95 # Slight green reduction
        frame[:,:,2] *= 0.8  # Blue reduction
        # Add slight vignette effect
        h, w = frame.shape[:2]
        Y, X = np.ogrid[:h, :w]
        center_x, center_y = w/2, h/2
        dist = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
        vignette = 1 - (dist / np.max(dist)) * 0.3
        frame *= vignette[:,:,np.newaxis]
        return np.clip(frame, 0, 255).astype('uint8')
    
    def cinematic_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)  # Make writable copy
        # Movie-like color grading
        # Enhance contrast
        frame = ((frame / 255.0 - 0.5) * 1.2 + 0.5) * 255
        # Slight blue tint in shadows, orange in highlights
        frame[:,:,0] = np.clip(frame[:,:,0] * 1.05, 0, 255)  # Red
        frame[:,:,2] = np.clip(frame[:,:,2] * 1.02, 0, 255)  # Blue
        return np.clip(frame, 0, 255).astype('uint8')
    
    def vivid_filter(get_frame, t):
        frame = get_frame(t).copy()  # Make writable copy
        # Boost saturation
        hsv = np.array([colorsys.rgb_to_hsv(r/255, g/255, b/255) 
                       for r, g, b in frame.reshape(-1, 3)])
        hsv[:, 1] = np.clip(hsv[:, 1] * 1.4, 0, 1)  # Boost saturation
        rgb = np.array([colorsys.hsv_to_rgb(h, s, v) for h, s, v in hsv])
        return (rgb.reshape(frame.shape) * 255).astype('uint8')
    
    def sepia_filter(get_frame, t):
        frame = get_frame(t).copy()  # Make writable copy
        # Classic sepia tone
        sepia_frame = np.zeros_like(frame)
        sepia_frame[:,:,0] = np.clip(0.393*frame[:,:,0] + 0.769*frame[:,:,1] + 0.189*frame[:,:,2], 0, 255)
        sepia_frame[:,:,1] = np.clip(0.349*frame[:,:,0] + 0.686*frame[:,:,1] + 0.168*frame[:,:,2], 0, 255)
        sepia_frame[:,:,2] = np.clip(0.272*frame[:,:,0] + 0.534*frame[:,:,1] + 0.131*frame[:,:,2], 0, 255)
        return sepia_frame.astype('uint8')
    
    def black_white_filter(get_frame, t):
        frame = get_frame(t).copy()  # Make writable copy
        # High contrast B&W
        gray = np.dot(frame[...,:3], [0.2989, 0.5870, 0.1140])
        return np.stack([gray, gray, gray], axis=-1).astype('uint8')
    
    def sunset_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)  # Make writable copy
        # Strong orange/red tones
        frame[:,:,0] *= 1.3  # Red boost
        frame[:,:,1] *= 1.1  # Green boost
        frame[:,:,2] *= 0.7  # Blue reduction
        return np.clip(frame, 0, 255).astype('uint8')
    
    def arctic_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)  # Make writable copy
        # Cold blue tones
        frame[:,:,0] *= 0.7  # Red reduction
        frame[:,:,1] *= 0.9  # Green reduction
        frame[:,:,2] *= 1.4  # Blue boost
        return np.clip(frame, 0, 255).astype('uint8')
    
    def neon_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)  # Make writable copy
        # Cyberpunk neon effect
        # Enhance contrast dramatically
        frame = ((frame / 255.0 - 0.5) * 1.8 + 0.5) * 255
        # Add magenta/cyan tones
        frame[:,:,0] = np.clip(frame[:,:,0] * 1.2, 0, 255)  # Red
        frame[:,:,2] = np.clip(frame[:,:,2] * 1.2, 0, 255)  # Blue
        return np.clip(frame, 0, 255).astype('uint8')
    
    # Add missing filter implementations
    def fade_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)
        # Faded film effect - reduce contrast and saturation
        # Reduce contrast
        frame = ((frame / 255.0 - 0.5) * 0.7 + 0.5) * 255
        # Reduce saturation
        hsv = np.array([colorsys.rgb_to_hsv(r/255, g/255, b/255) 
                       for r, g, b in frame.reshape(-1, 3)])
        hsv[:, 1] = np.clip(hsv[:, 1] * 0.6, 0, 1)  # Reduce saturation
        rgb = np.array([colorsys.hsv_to_rgb(h, s, v) for h, s, v in hsv])
        return (rgb.reshape(frame.shape) * 255).astype('uint8')
    
    def instagram_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)
        # Instagram-like filter: warm tones + slight vignette
        frame[:,:,0] *= 1.1  # Red boost
        frame[:,:,1] *= 1.05 # Green slight boost
        frame[:,:,2] *= 0.95 # Blue slight reduction
        
        # Add subtle vignette
        h, w = frame.shape[:2]
        Y, X = np.ogrid[:h, :w]
        center_x, center_y = w/2, h/2
        dist = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
        vignette = 1 - (dist / np.max(dist)) * 0.2
        frame *= vignette[:,:,np.newaxis]
        
        return np.clip(frame, 0, 255).astype('uint8')
    
    def forest_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)
        # Enhanced green tones for forest feel
        frame[:,:,0] *= 0.8  # Red reduction
        frame[:,:,1] *= 1.3  # Green boost
        frame[:,:,2] *= 0.9  # Blue slight reduction
        return np.clip(frame, 0, 255).astype('uint8')
    
    def desert_filter(get_frame, t):
        frame = get_frame(t).copy().astype(float)
        # Sandy warm colors
        frame[:,:,0] *= 1.2  # Red boost
        frame[:,:,1] *= 1.15 # Green boost (for sandy yellow)
        frame[:,:,2] *= 0.8  # Blue reduction
        return np.clip(frame, 0, 255).astype('uint8')
    
    # Updated filter mapping with all filters
    filter_functions = {
        'warm': warm_filter,
        'cool': cool_filter,
        'vintage': vintage_filter,
        'cinematic': cinematic_filter,
        'vivid': vivid_filter,
        'fade': fade_filter,
        'black_white': black_white_filter,
        'sepia': sepia_filter,
        'instagram': instagram_filter,
        'sunset': sunset_filter,
        'arctic': arctic_filter,
        'forest': forest_filter,
        'desert': desert_filter,
        'neon': neon_filter,
    }
    
    try:
        if filter_name in filter_functions:
            filtered_clip = clip.fl(filter_functions[filter_name])
            print(f"[FILTER] Successfully applied '{filter_name}' filter")
            return filtered_clip
        else:
            print(f"[FILTER] Unknown filter '{filter_name}', returning original")
            return clip
    except Exception as e:
        print(f"[FILTER] Error applying filter '{filter_name}': {e}")
        print("[FILTER] Returning original clip")
        return clip


def process_video_file(input_path, output_path, params, audio_path=None):
    clip = None
    audio_clip = None
    audio_subclip = None
    text_img_clip = None
    video = None
    
    try:
        print(f"[PROCESSING] Loading video: {input_path}")
        clip = VideoFileClip(input_path)
        
        # Get trim parameters
        start_time = float(params.get('start_time', 0))
        end_time = params.get('end_time')
        end_time = float(end_time) if end_time else clip.duration

        # FIX: Clamp end_time to actual video duration
        end_time = min(end_time, clip.duration)
        start_time = min(start_time, clip.duration)

        if start_time >= end_time:  # Defensive check
            end_time = min(start_time + 1, clip.duration)
        
        print(f"[PROCESSING] Original video duration: {clip.duration}s")
        print(f"[PROCESSING] Requested trim: {params.get('start_time', 0)}s to {params.get('end_time')}s")
        print(f"[PROCESSING] Actual trim (clamped): {start_time}s to {end_time}s")
        clip = clip.subclip(start_time, end_time)
        video_w, video_h = clip.size
        trim_duration = end_time - start_time

        # Apply filter BEFORE text overlay
        filter_name = params.get('filter', 'none')
        if filter_name and filter_name != 'none':
            print(f"[PROCESSING] Applying filter: {filter_name}")
            clip = apply_video_filter(clip, filter_name)

        # Handle audio replacement if audio file is provided
        if audio_path and os.path.exists(audio_path):
            print(f"[PROCESSING] Adding audio from: {audio_path}")
            audio_start_time = float(params.get('audio_start_time', 0))
            audio_clip = AudioFileClip(audio_path)
            print(f"[PROCESSING] Audio start time: {audio_start_time}s")
            print(f"[PROCESSING] Trim duration: {trim_duration}s")
            
            if audio_start_time < audio_clip.duration:
                available_audio_duration = min(trim_duration, audio_clip.duration - audio_start_time)
                audio_subclip = audio_clip.subclip(audio_start_time, audio_start_time + available_audio_duration)
                
                if available_audio_duration < trim_duration:
                    print(f"[PROCESSING] Audio shorter than video. Available: {available_audio_duration}s, needed: {trim_duration}s")
                
                print(f"[PROCESSING] Using audio from {audio_start_time}s to {audio_start_time + available_audio_duration}s")
                clip = clip.set_audio(audio_subclip)
            else:
                print(f"[PROCESSING] Audio start time ({audio_start_time}s) exceeds audio duration ({audio_clip.duration}s)")
                clip = clip.set_audio(None)

        #here
        if params.get('text'):
            print("[PROCESSING] Adding text overlay with IMPROVED aspect-ratio sizing...")
            
            text = params.get('text', 'Sample Text')
            user_font_size = int(float(params.get('font_size', 48)))
            font_color = params.get('font_color', 'white')
            bg_color = params.get('background_color', 'transparent')
            
            video_w, video_h = clip.size
            aspect_ratio = video_w / video_h
            
            # Use recommended scaling method
            recommended_method = get_recommended_scaling_method(video_w, video_h)
            final_font_size = get_aspect_ratio_aware_font_size(
                user_font_size, video_w, video_h, recommended_method
            )
            
            # Get position parameters
            center_x = int(float(params.get('pos_x', video_w // 2)))
            center_y = int(float(params.get('pos_y', video_h // 2))) - 11
            
            print(f"[PROCESSING] Video: {video_w}x{video_h} (AR: {aspect_ratio:.2f})")
            print(f"[PROCESSING] Recommended method: {recommended_method}")
            print(f"[PROCESSING] Font scaling: {user_font_size}px → {final_font_size}px")
            print(f"[PROCESSING] Text position: ({center_x}, {center_y})")
            # Pre-calculate text dimensions
            temp_img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            temp_draw = ImageDraw.Draw(temp_img)
            
            # Load font for measurement
            font = load_font_with_size(final_font_size)
            
            # Measure text
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            # Calculate position
            text_pos_x = center_x - text_w // 2
            text_pos_y = center_y - text_h // 2
            
            # Clamp to video bounds
            text_pos_x = max(0, min(text_pos_x, video_w - text_w))
            text_pos_y = max(0, min(text_pos_y, video_h - text_h))
            
            print(f"[PROCESSING] Final text positioning: ({text_pos_x}, {text_pos_y})")
            print(f"[PROCESSING] Text dimensions: {text_w}x{text_h}")
            
            # Create video-sized canvas with text at exact position
            text_array = create_text_with_emoji_pilmoji_fixed_macos(
                text, final_font_size, font_color, bg_color,
                (video_w, video_h), (text_pos_x, text_pos_y)
            )
            
            # Create and composite the text overlay
            text_img_clip = ImageClip(text_array, duration=clip.duration, transparent=True)
            text_img_clip = text_img_clip.set_position((0, 0))
            text_img_clip = text_img_clip.set_opacity(float(params.get('opacity', 1.0)))
            
            video = CompositeVideoClip([clip, text_img_clip])
        else:
            video = clip


        
        # Handle subtitle overlay - FIXED VERSION
        if params.get('enable_subtitles') == 'true':
            print("[PROCESSING] Adding auto-generated subtitles...")
            
            subtitle_font_size = int(float(params.get('subtitle_font_size', 32)))
            subtitle_color = params.get('subtitle_color', 'white')
            subtitle_bg_color = params.get('subtitle_bg_color', 'black')
            
            # ✅ FIX: Use the SAME trim parameters that were used for video trimming
            # These are the ALREADY CALCULATED values from earlier in the function
            print(f"[PROCESSING] Using trim parameters for subtitles: {start_time}s to {end_time}s")
            print(f"[PROCESSING] Subtitle generation duration: {end_time - start_time}s")
            
            # FIX: Pass language parameters correctly
            subtitle_language = params.get('subtitle_language', 'auto')
            translate_to_english = params.get('translate_to_english', 'false').lower() == 'true'
            
            # ✅ Generate subtitles with CORRECT trim parameters
            subtitle_result = generate_subtitles_with_whisper_trimmed(
                input_path,
                language=subtitle_language,
                translate_to_english=translate_to_english,
                trim_start=start_time,  # ✅ Use already calculated start_time
                trim_end=end_time       # ✅ Use already calculated end_time
            )
            
            print(f"[DEBUG] Generated trimmed subtitles: {subtitle_result}")
            
            # Create subtitle clip (timing is now 0-based for trimmed video)
            subtitle_clip = create_subtitle_clip(
                subtitle_result['subtitles'],
                video_w, video_h,
                font_size=subtitle_font_size,
                font_color=subtitle_color,
                bg_color=subtitle_bg_color
            )
            
            # Composite with existing video
            if isinstance(video, CompositeVideoClip):
                video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
            else:
                video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
            
            print(f"[PROCESSING] Added {len(subtitle_result['subtitles'])} subtitle segments for trimmed video")
 
        


        # Preserve original audio if no replacement audio
        if not video.audio and clip.audio:
            video = video.set_audio(clip.audio)

        print(f"[PROCESSING] Writing output to: {output_path}")
        video.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            verbose=False,
            logger=None
        )
        
        print("[SUCCESS] Processing complete.")
        return output_path
        
    except Exception as e:
        print(f"[ERROR] Processing failed: {e}")
        traceback.print_exc()
        raise e
        
    finally:
        # Clean up clips in the correct order
        try:
            if video and video != clip:
                video.close()
            if text_img_clip:
                text_img_clip.close()
            if audio_subclip:
                audio_subclip.close()
            if audio_clip:
                audio_clip.close()
            if clip:
                clip.close()
        except Exception as cleanup_error:
            print(f"[WARNING] Cleanup error: {cleanup_error}")

# Route to serve processed video files
@app.route('/processed-videos/<filename>')
def serve_processed_video(filename):
    """Serve processed video files to clients"""
    try:
        print(f"[SERVE] Serving video file: {filename}")
        return send_from_directory(
            PROCESSED_FOLDER,
            filename,
            as_attachment=False,
            mimetype='video/mp4'
        )
    except FileNotFoundError:
        print(f"[ERROR] Video file not found: {filename}")
        return jsonify({"error": "Video file not found"}), 404
    except Exception as e:
        print(f"[ERROR] Failed to serve video: {e}")
        return jsonify({"error": "Failed to serve video"}), 500

@app.route('/process-video', methods=['POST'])
def handle_video_upload():
    temp_video = None
    temp_audio = None
    
    try:
        if 'video' not in request.files:
            print("[ERROR] No video part in request.")
            return jsonify({"error": "No video file uploaded"}), 400

        # Create temp video file
        video_file = request.files['video']
        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        video_file.save(temp_video.name)
        temp_video.close()
        
        print(f"[UPLOAD] Video saved to temp file: {temp_video.name}")

        # Handle optional audio file
        audio_path = None
        if 'audio' in request.files:
            audio_file = request.files['audio']
            temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            audio_file.save(temp_audio.name)
            temp_audio.close()
            audio_path = temp_audio.name
            print(f"[UPLOAD] Audio saved to temp file: {temp_audio.name}")

        # Create output path for processed video
        output_filename = f"processed_{uuid.uuid4()}.mp4"
        output_path = os.path.join(PROCESSED_FOLDER, output_filename)

        print("[UPLOAD] Starting processing with parameters:")
        for key in request.form:
            print(f"  {key}: {request.form[key]}")

        # Process the video
        processed_path = process_video_file(temp_video.name, output_path, request.form, audio_path)
        
        # Return network-accessible URL
        video_url = f"http://{request.host}/processed-videos/{output_filename}"
        print(f"[UPLOAD] Returning video URL: {video_url}")

        # Optimize memory usage after processing
        print(f"[MEMORY] Usage before processing: {get_memory_usage():.1f}MB")
        optimize_memory()
        print(f"[MEMORY] Usage after processing: {get_memory_usage():.1f}MB")
        return jsonify({
            "processed_video_uri": video_url,
            "success": True,
            "message": "Video processed successfully with emoji support"
        })

    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        traceback.print_exc()
        print(f"[MEMORY] Usage before error: {get_memory_usage():.1f}MB")
         optimize_memory()
         print(f"[MEMORY] Usage after error: {get_memory_usage():.1f}MB")
        return jsonify({
            "error": str(e),
            "success": False,
            "message": "Video processing failed"
        }), 500

    finally:
        # Clean up temp video file
        if temp_video is not None:
            try:
                if os.path.exists(temp_video.name):
                    os.unlink(temp_video.name)
                    print(f"[CLEANUP] Deleted temp video file: {temp_video.name}")
            except Exception as e:
                print(f"[CLEANUP] Failed to delete temp video file: {e}")
        
        # Clean up temp audio file
        if temp_audio is not None:
            try:
                if os.path.exists(temp_audio.name):
                    os.unlink(temp_audio.name)
                    print(f"[CLEANUP] Deleted temp audio file: {temp_audio.name}")
            except Exception as e:
                print(f"[CLEANUP] Failed to delete temp audio file: {e}")

@app.route('/generate-subtitles', methods=['POST'])
def generate_subtitles():
    """Generate auto-subtitles for uploaded video with trim support"""
    temp_video = None
    
    try:
        if 'video' not in request.files:
            return jsonify({"error": "No video file provided"}), 400
        
        # Save uploaded video to temp file
        video_file = request.files['video']
        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        video_file.save(temp_video.name)
        temp_video.close()
        
        # Get parameters
        language = request.form.get('language', 'auto')
        translate_to_english = request.form.get('translate_to_english', 'false').lower() == 'true'
        
        # ✅ Get trim parameters
        trim_start = float(request.form.get('trim_start', 0))
        trim_end = request.form.get('trim_end')
        trim_end = float(trim_end) if trim_end else None
        
        print(f"[SUBTITLES] Generating subtitles for trimmed video: {trim_start}s to {trim_end}s")
        print(f"[SUBTITLES] Language: {language}, Translate: {translate_to_english}")
        
        # ✅ Use trimmed subtitle generation
        result = generate_subtitles_with_whisper_trimmed(
            temp_video.name, 
            language=language,
            translate_to_english=translate_to_english,
            trim_start=trim_start,
            trim_end=trim_end
        )
        
        return jsonify({
            "success": True,
            "subtitles": [
                {
                    "start": sub[0][0],
                    "end": sub[0][1], 
                    "text": sub[1]
                } for sub in result['subtitles']
            ],
            "detected_language": result['language'],
            "segments_count": result['segments_count'],
            "trim_info": {
                "trim_start": result['trim_start'],
                "trim_end": result['trim_end'],
                "trimmed_duration": result['trimmed_duration']
            },
            "message": f"Generated {result['segments_count']} subtitle segments for trimmed portion"
        })
        
    except Exception as e:
        print(f"[ERROR] Subtitle generation failed: {e}")
        return jsonify({
            "error": str(e),
            "success": False,
            "message": "Subtitle generation failed"
        }), 500
    
    finally:
        # Cleanup
        if temp_video and os.path.exists(temp_video.name):
            try:
                os.unlink(temp_video.name)
                print("[CLEANUP] Deleted temp video file")
            except Exception as e:
                print(f"[CLEANUP] Temp file cleanup failed: {e}")


if __name__ == '__main__':
    print("="*50)
    print("[SERVER] Video Processing Server with Aspect-Ratio Aware Text")
    print("[SERVER] Features:")
    print("[SERVER] - Video trimming and audio overlay")
    print("[SERVER] - Aspect-ratio aware font scaling")
    print("[SERVER] - Full-color emoji text rendering (Pilmoji)")
    print("[SERVER] - HTTP video serving")
    print("[SERVER] - Automatic temp file cleanup")
    print("[SERVER] - Cross-platform compatibility")
    print("="*50)
    print("[SERVER] Flask server starting on port 5000...")
    print("="*50)
    
    # app.run(host='0.0.0.0', port=5000, debug=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
else:
    # Production server (Render will use this)
    print("[SERVER] Production mode - using Gunicorn")
