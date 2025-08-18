import os
import tempfile
import shutil

def setup_custom_temp_directory():
    """Set temp directory to server.py location instead of system root"""
    
    # Get the directory where server.py is located
    server_dir = os.path.dirname(os.path.abspath(__file__))
    custom_temp_dir = os.path.join(server_dir, 'tmp')
    
    # Create the temp directory if it doesn't exist
    os.makedirs(custom_temp_dir, exist_ok=True)
    
    # Set permissions (important for hosted servers)
    os.chmod(custom_temp_dir, 0o755)
    
    # Override Python's default temp directory
    tempfile.tempdir = custom_temp_dir
    
    # Set environment variables (affects all subprocesses)
    os.environ['TMPDIR'] = custom_temp_dir
    os.environ['TEMP'] = custom_temp_dir
    os.environ['TMP'] = custom_temp_dir
    
    print(f"[TEMP] Using custom temp directory: {custom_temp_dir}")
    
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


app = Flask(__name__)
CORS(app)

PROCESSED_FOLDER = 'processed'
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

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
        video_url = f"http://{request.host}/python-app/processed/{output_filename}"
        print(f"[UPLOAD] Returning video URL: {video_url}")

        # Optimize memory usage after processing
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
