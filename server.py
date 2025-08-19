import os
import tempfile
import shutil
import sys

def setup_custom_temp_directory():
    """Set temp directory with proper permissions and fallback"""
    
    # Try your preferred path first
    preferred_paths = [
        '/var/www/pythonapp/tmp',
        '/tmp/pythonapp',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp')
    ]
    
    custom_temp_dir = None
    
    for path in preferred_paths:
        try:
            # Create the temp directory if it doesn't exist
            os.makedirs(path, exist_ok=True)
            
            # Test write permissions
            test_file = os.path.join(path, 'write_test.tmp')
            with open(test_file, 'w') as f:
                f.write('test')
            os.unlink(test_file)
            
            # If we get here, the path works
            custom_temp_dir = path
            print(f"[TEMP] Successfully using: {custom_temp_dir}")
            break
            
        except (OSError, PermissionError) as e:
            print(f"[TEMP] Failed to use {path}: {e}")
            continue
    
    # Fallback to system temp if nothing works
    if custom_temp_dir is None:
        custom_temp_dir = tempfile.gettempdir()
        print(f"[TEMP] Falling back to system temp: {custom_temp_dir}")
    
    # Set permissions (with error handling)
    try:
        os.chmod(custom_temp_dir, 0o755)
    except (OSError, PermissionError) as e:
        print(f"[TEMP] Warning: Could not set permissions on {custom_temp_dir}: {e}")
    
    # Override Python's default temp directory
    tempfile.tempdir = custom_temp_dir
    
    # Set environment variables (affects all subprocesses)
    os.environ['TMPDIR'] = custom_temp_dir
    os.environ['TEMP'] = custom_temp_dir
    os.environ['TMP'] = custom_temp_dir
    
    print(f"[TEMP] Using temp directory: {custom_temp_dir}")
    
    # Test if temp directory is writable
    try:
        test_file = tempfile.NamedTemporaryFile(delete=True)
        test_file.close()
        print(f"[TEMP] ✅ Temp directory is writable")
    except Exception as e:
        print(f"[TEMP] ❌ Temp directory test failed: {e}")
        raise e
    
    return custom_temp_dir

# ✅ CRITICAL: Call this BEFORE importing Flask or other libraries
custom_temp = setup_custom_temp_directory()


import uuid
import traceback
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip

from PIL import Image, ImageDraw, ImageFont, ImageColor
from pilmoji import Pilmoji

import time

#Memory Optimization
import gc

#Filter
import colorsys
from scipy import ndimage

#Subtitles
# import whisper
from faster_whisper import WhisperModel

from moviepy.video.tools.subtitles import SubtitlesClip
WHISPER_MODEL = None



app = Flask(__name__)
CORS(app)

PROCESSED_FOLDER = 'processed'
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

import subprocess

def validate_video_file(file_path):
    """Validate video file integrity using both file checks and ffprobe"""
    try:
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise ValueError("Empty file uploaded")
        
        if file_size < 1024:  # Less than 1KB is suspicious
            raise ValueError("File too small to be a valid video")
        
        print(f"[VALIDATION] File size check passed: {file_size} bytes")
        
        # Try ffprobe first (faster and more reliable than MoviePy)
        try:
            result = subprocess.run([
                'ffprobe', 
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=duration',
                '-of', 'csv=p=0',
                file_path
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                raise ValueError("ffprobe validation failed - invalid video format")
                
            duration_str = result.stdout.strip()
            if duration_str and float(duration_str) > 0:
                print(f"[VALIDATION] ffprobe validation passed - duration: {duration_str}s")
            else:
                raise ValueError("Video has invalid duration")
                
        except subprocess.TimeoutExpired:
            raise ValueError("Video validation timeout - file may be corrupted")
        except subprocess.CalledProcessError:
            raise ValueError("Video format validation failed")
        except FileNotFoundError:
            print("[VALIDATION] ffprobe not found, falling back to MoviePy validation")
            # Fallback to MoviePy validation
            pass
        
        # Additional MoviePy validation as fallback
        try:
            with VideoFileClip(file_path) as clip:
                duration = clip.duration
                if duration <= 0:
                    raise ValueError("Invalid video duration from MoviePy")
                width, height = clip.size
                if width <= 0 or height <= 0:
                    raise ValueError("Invalid video dimensions")
                print(f"[VALIDATION] MoviePy validation passed - {width}x{height}, {duration}s")
        except Exception as moviepy_error:
            raise ValueError(f"MoviePy validation failed: {str(moviepy_error)}")
        
        print("[VALIDATION] ✅ Video file validation completed successfully")
        return True
        
    except ValueError:
        # Re-raise ValueError as-is
        raise
    except Exception as e:
        # Convert other exceptions to ValueError for consistent handling
        raise ValueError(f"Video validation error: {str(e)}")

#Subtitle
#Subtitles
def get_whisper_model():
    """Get or create global WhisperModel instance"""
    global WHISPER_MODEL
    
    if WHISPER_MODEL is None:
        print("[WHISPER] Loading model...")
        try:
            model_size = os.getenv('WHISPER_MODEL_SIZE', 'small')
            device = "cpu"  # Use CPU for production stability
            compute_type = "int8"  # Memory efficient
            
            WHISPER_MODEL = WhisperModel(
                model_size, 
                device=device, 
                compute_type=compute_type,
                num_workers=1  # Single worker for stability
            )
            print(f"[WHISPER] Model loaded: {model_size}")
        except Exception as e:
            print(f"[WHISPER] Model loading failed: {e}")
            # Fallback to tiny model
            WHISPER_MODEL = WhisperModel("tiny", device="cpu", compute_type="int8")
            print("[WHISPER] Using fallback tiny model")
    
    return WHISPER_MODEL

def generate_subtitles_with_whisper_trimmed(video_path, language="auto", translate_to_english=False, trim_start=0, trim_end=None):
    """
    Generate auto-subtitles for TRIMMED video portion with proper timing synchronization
    """
    temp_video_path = None
    temp_audio_file = None
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

        temp_dir = tempfile.gettempdir()
        print(f"[GENERATE SUBTITLE TEMP DEBUG] System temp directory: {temp_dir}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Temp directory exists: {os.path.exists(temp_dir)}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Temp directory writable: {os.access(temp_dir, os.W_OK)}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Current working directory: {os.getcwd()}")
        unique_id = f"{os.getpid()}-{int(time.time())}"
        temp_video_path = os.path.join(temp_dir, f"whisper-trimmed-{unique_id}.mp4")
        temp_audio_file = os.path.join(temp_dir, f"whisper-temp-audio-{unique_id}.m4a")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Generated unique ID: {unique_id}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Process ID: {os.getpid()}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Timestamp: {int(time.time())}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Temp video path: {temp_video_path}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Temp audio path: {temp_audio_file}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Temp video parent dir exists: {os.path.exists(os.path.dirname(temp_video_path))}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Temp audio parent dir exists: {os.path.exists(os.path.dirname(temp_audio_file))}")
        
        original_cwd = os.getcwd()
        print(f"[TEMP DEBUG] Original working directory: {original_cwd}")
        # Save trimmed video to temp file
        try:
            os.chdir(temp_dir)  # Force MoviePy to use temp directory
            print(f"[WHISPER] Changed working directory to: {temp_dir}")
            print(f"[GENERATE SUBTITLE TEMP DEBUG] Changed working directory to: {temp_dir}")
            print(f"[GENERATE SUBTITLE TEMP DEBUG] Current working directory after change: {os.getcwd()}")

            print(f"[GENERATE SUBTITLE TEMP DEBUG] About to create trimmed video file...")
            print(f"[GENERATE SUBTITLE TEMP DEBUG] MoviePy will create temp files in: {os.getcwd()}")
            
            trimmed_clip.write_videofile(
                temp_video_path,
                verbose=False,
                logger=None,
                audio_codec='aac',
                temp_audiofile=temp_audio_file,  # ✅ Specify temp audio location
                remove_temp=True,
                ffmpeg_params=['-movflags', 'faststart']
            )

            if os.path.exists(temp_video_path):
                file_size = os.path.getsize(temp_video_path)
                print(f"[GENERATE SUBTITLE TEMP DEBUG] ✅ Trimmed video created successfully")
                print(f"[GENERATE SUBTITLE TEMP DEBUG] File size: {file_size / 1024 / 1024:.2f} MB")
                print(f"[GENERATE SUBTITLE TEMP DEBUG] File permissions: {oct(os.stat(temp_video_path).st_mode)[-3:]}")
            else:
                print(f"[GENERATE SUBTITLE TEMP DEBUG] ❌ Trimmed video file NOT created!")
                
            if os.path.exists(temp_audio_file):
                audio_size = os.path.getsize(temp_audio_file)
                print(f"[GENERATE SUBTITLE TEMP DEBUG] ✅ Temp audio file created: {audio_size / 1024:.2f} KB")
            else:
                print(f"[GENERATE SUBTITLE TEMP DEBUG] ⚠️ Temp audio file not found (may be auto-removed)")
                
        except Exception as video_create_error:
            print(f"[GENERATE SUBTITLE TEMP DEBUG] ❌ Error creating trimmed video: {video_create_error}")
            print(f"[GENERATE SUBTITLE TEMP DEBUG] Error type: {type(video_create_error).__name__}")
            raise video_create_error
            
        finally:
            os.chdir(original_cwd)  # Always restore working directory
            print(f"[GENERATE SUBTITLE TEMP DEBUG] Restored working directory to: {original_cwd}")
            print(f"[GENERATE SUBTITLE TEMP DEBUG] Current working directory after restore: {os.getcwd()}")
            print(f"[WHISPER] Restored working directory to: {original_cwd}")
        
        
        # Clean up clips
        trimmed_clip.close()
        original_clip.close()
        
        print(f"[WHISPER] Created trimmed video: {temp_video_path}")
        print(f"[WHISPER] Trimmed duration: {trim_end - trim_start}s")
        
        # ✅ STEP 2: Generate subtitles from trimmed video (timing will be 0-based)
        # model = load_whisper_model("small")
        # In your function, replace the model creation with:
        WHISPER_MODEL = get_whisper_model()

        
        # Extract audio from trimmed video
        print(f"[GENERATE SUBTITLE TEMP DEBUG] About to extract audio from: {temp_video_path}")
        audio_path = extract_audio_for_whisper(temp_video_path)
        print(f"[GENERATE SUBTITLE TEMP DEBUG] Audio extracted to: {audio_path}")
        
        # Define task
        task = 'translate' if translate_to_english else 'transcribe'

        segments, info = WHISPER_MODEL.transcribe(
            audio_path, 
            task=task,
            language=None if language == "auto" else language,
            beam_size=5,  # Use beam_size instead of verbose
            word_timestamps=True,  # This might work, but check documentation
            temperature=0.0,
            vad_filter=True,  # Instead of no_speech_threshold
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False
        )


        
        print(f"[WHISPER] Detected language: {getattr(info, 'language', 'unknown')}")
    

        # ✅ STEP 3: Process subtitles using segments generator
        subtitles = []
        segment_count = 0
        MAX_CHARS_PER_SUBTITLE = 50
        MAX_WORDS_PER_SUBTITLE = 8

        for i, segment in enumerate(segments):
            start_time = segment.start  # float
            end_time = segment.end      # float
            text = segment.text.strip()
            
            print(f"[WHISPER] Segment {i}: {start_time:.2f}s-{end_time:.2f}s: '{text}'")
            
            if not text:
                continue

            if len(text) > MAX_CHARS_PER_SUBTITLE or len(text.split()) > MAX_WORDS_PER_SUBTITLE:
                split_subtitles = split_long_subtitle(text, start_time, end_time, MAX_CHARS_PER_SUBTITLE, MAX_WORDS_PER_SUBTITLE)
                subtitles.extend(split_subtitles)
                print(f"[WHISPER] Split long text: '{text[:30]}...' into {len(split_subtitles)} parts")
            else:
                subtitles.append(((start_time, end_time), text))
            
            segment_count += 1

        
        print(f"[WHISPER] Generated {len(subtitles)} subtitle segments for trimmed video (0-based timing)")
    
        return {
            'subtitles': subtitles,
            'language': getattr(info, 'language', 'unknown'),
            'segments_count': len(subtitles),
            'trim_start': trim_start,
            'trim_end': trim_end,
            'trimmed_duration': trim_end - trim_start
        }

        
    except Exception as e:
        print(f"[WHISPER] Trimmed subtitle generation failed: {e}")
        print(f"[GENERATE SUBTITLE TEMP DEBUG] ❌ Exception details: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e
    finally:
        # Enhanced cleanup
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.unlink(temp_video_path)
                print("[WHISPER] Cleaned up trimmed video file")
            except Exception as cleanup_error:
                print(f"[WHISPER] Trimmed video cleanup warning: {cleanup_error}")
        
        if temp_audio_file and os.path.exists(temp_audio_file):
            try:
                os.unlink(temp_audio_file)
                print("[WHISPER] Cleaned up temp audio file")
            except Exception as cleanup_error:
                print(f"[WHISPER] Temp audio cleanup warning: {cleanup_error}")

        if audio_path:
          print(f"[TEMP DEBUG] Checking extracted audio file: {audio_path}")
          if os.path.exists(audio_path):
              try:
                  file_size = os.path.getsize(audio_path)
                  print(f"[TEMP DEBUG] File exists, size: {file_size / 1024:.2f} KB")
                  os.unlink(audio_path)
                  print("[TEMP DEBUG] ✅ Extracted audio file deleted successfully")
              except Exception as cleanup_error:
                  print(f"[TEMP DEBUG] ❌ Failed to delete audio: {cleanup_error}")
          else:
              print(f"[TEMP DEBUG] ⚠️ Audio file already gone: {audio_path}")

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
        
        # File validation (keeping your existing code)
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        file_size = os.path.getsize(video_path)
        if file_size == 0:
            raise ValueError(f"Video file is empty: {video_path} (0 bytes)")
        
        print(f"[WHISPER] Video file validated - Size: {file_size / (1024*1024):.2f} MB")
        
        try:
            video = VideoFileClip(video_path)
        except Exception as moviepy_error:
            raise ValueError(f"MoviePy failed to load video: {moviepy_error}")
        
        if video is None:
            raise ValueError("MoviePy returned None - video file may be corrupted")
        
        if not hasattr(video, 'duration') or video.duration <= 0:
            raise ValueError(f"Invalid video duration: {getattr(video, 'duration', 'None')}")
        
        if video.audio is None:
            video.close()
            raise ValueError("Video file has no audio track - cannot generate subtitles")
        
        print(f"[WHISPER] Video validated - Duration: {video.duration:.2f}s, Size: {video.size}")
        
        # ✅ FIXED: Use consistent temp directory approach (same as your working functions)
        temp_dir = tempfile.gettempdir()
        print(f"[EXTRACT AUDIO TEMP DEBUG] Using temp directory: {temp_dir}")
        os.makedirs(temp_dir, exist_ok=True)
        
        unique_id = f"{os.getpid()}-{int(time.time())}"
        audio_path = os.path.join(temp_dir, f"whisper-audio-{unique_id}.wav")

        print(f"[EXTRACT AUDIO TEMP DEBUG] Generated audio path: {audio_path}")
        print(f"[EXTRACT AUDIO TEMP DEBUG] Audio parent directory: {os.path.dirname(audio_path)}")
        print(f"[EXTRACT AUDIO TEMP DEBUG] Audio parent dir exists: {os.path.exists(os.path.dirname(audio_path))}")
        print(f"[WHISPER] Extracting audio to: {audio_path}")

        print(f"[WHISPER] Extracting audio to: {audio_path}")
        
        # ✅ AGGRESSIVE FIX: Change working directory to force MoviePy compliance
        original_cwd = os.getcwd()
        print(f"[EXTRACT AUDIO TEMP DEBUG] Original CWD: {original_cwd}")
        try:
            os.chdir(temp_dir)  # Force MoviePy to use temp directory
            print(f"[EXTRACT AUDIO TEMP DEBUG] Changed CWD to: {temp_dir}")
            print(f"[EXTRACT AUDIO TEMP DEBUG] Current CWD: {os.getcwd()}")
            print(f"[WHISPER] Changed working directory to: {temp_dir}")
            
            # ✅ Log before audio extraction
            print(f"[EXTRACT AUDIO TEMP DEBUG] About to extract audio...")
            print(f"[EXTRACT AUDIO TEMP DEBUG] MoviePy will create temp files in: {os.getcwd()}")
            
            video.audio.write_audiofile(
                audio_path, 
                verbose=False, 
                logger=None,
                codec='pcm_s16le',
            )
            if os.path.exists(audio_path):
                audio_size = os.path.getsize(audio_path)
                print(f"[EXTRACT AUDIO TEMP DEBUG] ✅ Audio file created successfully")
                print(f"[EXTRACT AUDIO TEMP DEBUG] Audio file size: {audio_size / 1024:.2f} KB")
                print(f"[EXTRACT AUDIO TEMP DEBUG] Audio file permissions: {oct(os.stat(audio_path).st_mode)[-3:]}")
            else:
                print(f"[EXTRACT AUDIO TEMP DEBUG] ❌ Audio file NOT created!")
        except Exception as audio_error:
            print(f"[EXTRACT AUDIO TEMP DEBUG] ❌ Audio extraction error: {audio_error}")
            print(f"[EXTRACT AUDIO TEMP DEBUG] Error type: {type(audio_error).__name__}")
            raise audio_error
        finally:
            os.chdir(original_cwd)  # Always restore working directory
            print(f"[EXTRACT AUDIO TEMP DEBUG] Restored CWD to: {original_cwd}")
            print(f"[WHISPER] Restored working directory to: {original_cwd}")
        
        # Rest of your function remains the same...
        enhanced_audio_path = enhance_audio_for_speech(audio_path)
        
        if enhanced_audio_path != audio_path:
            try:
                os.unlink(audio_path)
            except:
                pass
            audio_path = enhanced_audio_path
        
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise ValueError("Audio extraction failed - output file is empty")
        
        print(f"[WHISPER] Audio extraction successful: {os.path.getsize(audio_path)} bytes")
        
        video.close()
        return audio_path
        
    except Exception as e:
        print(f"[WHISPER] Audio extraction failed: {e}")
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
        
        # ✅ FIXED: Use system temp directory
        temp_dir = tempfile.gettempdir()
        unique_id = f"{os.getpid()}-{int(time.time())}"
        enhanced_path = os.path.join(temp_dir, f"enhanced-audio-{unique_id}.wav")
        
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

        # Text overlay processing (your existing code)
        if params.get('text'):
            print("[PROCESSING] Adding text overlay with IMPROVED aspect-ratio sizing...")
            
            text = params.get('text', 'Sample Text')
            user_font_size = int(float(params.get('font_size', 48)))
            font_color = params.get('font_color', 'white')
            bg_color = params.get('background_color', 'transparent')
            
            video_w, video_h = clip.size
            aspect_ratio = video_w / video_h

            final_font_size = user_font_size
            
            # Get position parameters
            center_x = int(float(params.get('pos_x', video_w // 2)))
            center_y = int(float(params.get('pos_y', video_h // 2))) - 11
            
            print(f"[PROCESSING] Video: {video_w}x{video_h} (AR: {aspect_ratio:.2f})")
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

        
        # Handle subtitle overlay (your existing code)
        if params.get('enable_subtitles') == 'true':
            print("[PROCESSING] Adding auto-generated subtitles...")
            
            subtitle_font_size = int(float(params.get('subtitle_font_size', 32)))
            subtitle_color = params.get('subtitle_color', 'white')
            subtitle_bg_color = params.get('subtitle_bg_color', 'black')
            
            print(f"[PROCESSING] Using trim parameters for subtitles: {start_time}s to {end_time}s")
            print(f"[PROCESSING] Subtitle generation duration: {end_time - start_time}s")
            
            subtitle_language = params.get('subtitle_language', 'auto')
            translate_to_english = params.get('translate_to_english', 'false').lower() == 'true'
            
            subtitle_result = generate_subtitles_with_whisper_trimmed(
                input_path,
                language=subtitle_language,
                translate_to_english=translate_to_english,
                trim_start=start_time,
                trim_end=end_time
            )
            
            print(f"[DEBUG] Generated trimmed subtitles: {subtitle_result}")
            
            subtitle_clip = create_subtitle_clip(
                subtitle_result['subtitles'],
                video_w, video_h,
                font_size=subtitle_font_size,
                font_color=subtitle_color,
                bg_color=subtitle_bg_color
            )
            
            if isinstance(video, CompositeVideoClip):
                video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
            else:
                video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
            
            print(f"[PROCESSING] Added {len(subtitle_result['subtitles'])} subtitle segments for trimmed video")


        # Preserve original audio if no replacement audio
        if not video.audio and clip.audio:
            video = video.set_audio(clip.audio)

        # ✅ FIXED: Use system temp directory for all temp files
        print(f"[PROCESSING] Writing output to: {output_path}")
        
        # Create unique temp file names using system temp directory
        temp_dir = tempfile.gettempdir()
        unique_id = f"{os.getpid()}-{int(time.time())}"
        temp_audio_path = os.path.join(temp_dir, f"temp-audio-{unique_id}.m4a")
        
        print(f"[PROCESSING] Using temp audio file: {temp_audio_path}")
        
        try:
            video.write_videofile(
                output_path, 
                codec="libx264", 
                audio_codec="aac",
                temp_audiofile=temp_audio_path,  # ✅ Use system temp directory
                remove_temp=True,
                verbose=False,
                logger=None,
                threads=4,  # Use multiple threads for faster processing
                preset='medium',  # Good balance of speed vs quality
                ffmpeg_params=['-movflags', 'faststart']
            )
            
            print("[SUCCESS] Processing complete.")
            
        except Exception as write_error:
            print(f"[ERROR] Video writing failed: {write_error}")
            # Manual cleanup of temp file if write_videofile fails
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                    print(f"[CLEANUP] Manually removed temp audio file: {temp_audio_path}")
                except:
                    pass
            raise write_error
        finally:
            # Extra safety cleanup - ensure temp audio file is removed
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                    print(f"[CLEANUP] Final cleanup of temp audio file: {temp_audio_path}")
                except:
                    pass
        
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
        if video_file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
            
        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False, dir=tempfile.gettempdir())
        video_file.save(temp_video.name)
        temp_video.close()
        
        print(f"[UPLOAD] Video saved to temp file: {temp_video.name}")

        # ✅ ADD VALIDATION HERE - Check file integrity before processing
        try:
            file_size = os.path.getsize(temp_video.name)
            if file_size == 0:
                raise ValueError("Uploaded file is empty")
            
            print(f"[VALIDATION] File size: {file_size} bytes")
            
            # Validate the video file using your function
            validate_video_file(temp_video.name)
            print("[VALIDATION] ✅ Video file validation passed")
            
        except ValueError as validation_error:
            print(f"[VALIDATION] ❌ Video validation failed: {validation_error}")
            return jsonify({"error": f"Invalid video file: {str(validation_error)}"}), 400
        except Exception as validation_error:
            print(f"[VALIDATION] ❌ Unexpected validation error: {validation_error}")
            return jsonify({"error": "Corrupted or invalid video file"}), 400

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

        # Process the video (only after validation passes)
        processed_path = process_video_file(temp_video.name, output_path, request.form, audio_path)
        
        # Return network-accessible URL
        video_url = f"http://{request.host}/python-app/processed/{output_filename}"
        print(f"[UPLOAD] Returning video URL: {video_url}")

        return jsonify({
            "processed_video_uri": video_url,
            "success": True,
            "message": "Video processed successfully with emoji support"
        })

    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        traceback.print_exc()
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

# Add this to fix Railway health checks
@app.route('/')
def root():
    return jsonify({
        "status": "healthy",
        "service": "video-processing-server",
        "message": "Server is running"
    }), 200

@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/ping')
def ping():
    return "pong", 200

@app.route('/test-temp', methods=['GET'])
def test_temp_directory():
    """Test endpoint to verify temp directory setup"""
    try:
        temp_dir = tempfile.gettempdir()
        
        # Create a test file
        test_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
        test_file.write(b'Test temp file content')
        test_file.close()
        
        # Check file exists
        file_exists = os.path.exists(test_file.name)
        file_size = os.path.getsize(test_file.name) if file_exists else 0
        
        # Clean up test file
        if file_exists:
            os.unlink(test_file.name)
        
        return jsonify({
            "success": True,
            "temp_directory": temp_dir,
            "server_directory": os.path.dirname(os.path.abspath(__file__)),
            "test_file_created": file_exists,
            "test_file_size": file_size,
            "disk_usage": {
                "total": shutil.disk_usage(temp_dir).total // (1024**3),
                "free": shutil.disk_usage(temp_dir).free // (1024**3)
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "temp_directory": tempfile.gettempdir()
        }), 500

@app.route('/test-whisper-lite', methods=['GET'])
def test_whisper_lite():
    """
    Very simple health endpoint for Faster Whisper.
    - Verifies import
    - Attempts to load a tiny model (fast, low RAM)
    - Reports basic info and any available local models
    """
    info = {
        "success": False,
        "whisper_imported": False,
        "model_load_success": False,
        "model_size": "tiny",
        "device": "cpu",
        "compute_type": "int8",
        "available_local_models": [],
        "env": {
            "WHISPER_MODEL_SIZE": os.getenv("WHISPER_MODEL_SIZE"),
            "TMPDIR": os.getenv("TMPDIR"),
            "TEMP": os.getenv("TEMP"),
            "TMP": os.getenv("TMP"),
        },
        "temp_directory": tempfile.gettempdir()
    }
    try:
        # 1) Import check
        from faster_whisper import WhisperModel
        info["whisper_imported"] = True

        # 2) List common local model directories (if present)
        candidates = [
            os.path.expanduser("~/.cache/whisper"),
            os.path.expanduser("~/.cache/faster_whisper"),
            "/root/.cache/whisper",
            "/root/.cache/faster_whisper",
            "./models",
        ]
        seen = set()
        for p in candidates:
            if os.path.isdir(p):
                for name in os.listdir(p):
                    full = os.path.join(p, name)
                    if os.path.isdir(full) and name not in seen:
                        seen.add(name)
        info["available_local_models"] = sorted(seen)

        # 3) Try loading a tiny model on CPU with int8
        try:
            model = WhisperModel("tiny", device="cpu", compute_type="int8", num_workers=1)
            # Touch a small attribute to ensure it’s usable
            _ = model  # noqa: F841
            info["model_load_success"] = True
            info["success"] = True
            return jsonify(info), 200
        except Exception as e:
            info["error"] = f"Model load failed: {type(e).__name__}: {str(e)}"
            return jsonify(info), 500

    except Exception as e:
        info["error"] = f"Whisper import failed: {type(e).__name__}: {str(e)}"
        return jsonify(info), 500



if __name__ == '__main__':
    # Railway-specific configuration
    port = int(os.environ.get('PORT', 5000))
    print(f"[SERVER] Starting on Railway - Port: {port}")
    print("[SERVER] Production mode - Railway deployment")
    
    # Don't pre-load heavy models on Railway
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)


else:
    # Production server (Render will use this)
    print("[SERVER] Production mode - using Gunicorn")
