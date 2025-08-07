# import os
# import uuid
# import traceback
# import tempfile
# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from werkzeug.utils import secure_filename
# from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip, AudioFileClip

# import moviepy.config as mpyconf

# # Configure ImageMagick path
# mpyconf.change_settings({
#     "IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
# })

# app = Flask(__name__)
# CORS(app)

# PROCESSED_FOLDER = 'processed'
# os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# def process_video_file(input_path, output_path, params, audio_path=None):
#     clip = None
#     audio_clip = None
#     audio_subclip = None
#     txt_clip = None
#     video = None
    
#     try:
#         print(f"[PROCESSING] Loading video: {input_path}")
#         clip = VideoFileClip(input_path)
        
#         # Get trim parameters
#         start_time = float(params.get('start_time', 0))
#         end_time = params.get('end_time')
#         end_time = float(end_time) if end_time else clip.duration
        
#         print(f"[PROCESSING] Trimming video from {start_time}s to {end_time}s")
#         clip = clip.subclip(start_time, end_time)
#         video_w, video_h = clip.size
#         trim_duration = end_time - start_time

#         # Handle audio replacement if audio file is provided
#         if audio_path and os.path.exists(audio_path):
#             print(f"[PROCESSING] Adding audio from: {audio_path}")
#             audio_start_time = float(params.get('audio_start_time', 0))
#             audio_clip = AudioFileClip(audio_path)
#             print(f"[PROCESSING] Audio start time: {audio_start_time}s")
#             print(f"[PROCESSING] Trim duration: {trim_duration}s")
            
#             if audio_start_time < audio_clip.duration:
#                 available_audio_duration = min(trim_duration, audio_clip.duration - audio_start_time)
#                 audio_subclip = audio_clip.subclip(audio_start_time, audio_start_time + available_audio_duration)
                
#                 if available_audio_duration < trim_duration:
#                     print(f"[PROCESSING] Audio shorter than video. Available: {available_audio_duration}s, needed: {trim_duration}s")
                
#                 print(f"[PROCESSING] Using audio from {audio_start_time}s to {audio_start_time + available_audio_duration}s")
#                 clip = clip.set_audio(audio_subclip)
#             else:
#                 print(f"[PROCESSING] Audio start time ({audio_start_time}s) exceeds audio duration ({audio_clip.duration}s)")
#                 clip = clip.set_audio(None)

#         # Get positions (center-based from React Native)
#         center_x = int(float(params.get('pos_x', 0)))
#         center_y = int(float(params.get('pos_y', 0)))

#         if params.get('text'):
#             print("[PROCESSING] Adding text overlay...")
#             txt_clip = TextClip(
#                 params['text'],
#                 fontsize=int(float(params.get('font_size', 48))),
#                 color=params.get('font_color', 'white'),
#                 bg_color=params.get('background_color', None) if params.get('background_color') != 'transparent' else None
#             )
#             text_w, text_h = txt_clip.size
#             top_left_x = center_x - (text_w // 2)
#             top_left_y = center_y - (text_h // 2)
#             top_left_x = max(0, min(top_left_x, video_w - text_w))
#             top_left_y = max(0, min(top_left_y, video_h - text_h))
#             print(f"[PROCESSING] Text dimensions: {text_w}x{text_h}")
#             print(f"[PROCESSING] Center: ({center_x}, {center_y}) → Top-left: ({top_left_x}, {top_left_y})")
            
#             txt_clip = (
#                 txt_clip
#                 .set_position((top_left_x, top_left_y))
#                 .set_opacity(float(params.get('opacity', 1.0)))
#                 .set_duration(clip.duration)
#             )
#             video = CompositeVideoClip([clip, txt_clip])
#         else:
#             video = clip

#         if not video.audio and clip.audio:
#             video = video.set_audio(clip.audio)

#         print(f"[PROCESSING] Writing output to: {output_path}")
#         # Use specific codecs that work well with audio
#         video.write_videofile(
#             output_path, 
#             codec="libx264", 
#             audio_codec="aac",
#             temp_audiofile="temp-audio.m4a",
#             remove_temp=True
#         )
        
#         print("[SUCCESS] Processing complete.")
#         return output_path
        
#     except Exception as e:
#         print(f"[ERROR] Processing failed: {e}")
#         traceback.print_exc()
#         raise e
        
#     finally:
#         # Clean up clips in the correct order - NEVER close the original clips before subclips
#         try:
#             if video and video != clip:
#                 video.close()
#             if txt_clip:
#                 txt_clip.close()
#             if audio_subclip:
#                 audio_subclip.close()
#             if audio_clip:
#                 audio_clip.close()
#             if clip:
#                 clip.close()
#         except Exception as cleanup_error:
#             print(f"[WARNING] Cleanup error: {cleanup_error}")

# @app.route('/process-video', methods=['POST'])
# def handle_video_upload():
#     temp_video = None
#     temp_audio = None
    
#     try:
#         if 'video' not in request.files:
#             print("[ERROR] No video part in request.")
#             return jsonify({"error": "No video file uploaded"}), 400

#         # Create temp video file
#         video_file = request.files['video']
#         temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         video_file.save(temp_video.name)
#         temp_video.close()  # Close so MoviePy can access it on Windows
        
#         print(f"[UPLOAD] Video saved to temp file: {temp_video.name}")

#         # Handle optional audio file
#         audio_path = None
#         if 'audio' in request.files:
#             audio_file = request.files['audio']
#             temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
#             audio_file.save(temp_audio.name)
#             temp_audio.close()  # Close so MoviePy can access it on Windows
#             audio_path = temp_audio.name
#             print(f"[UPLOAD] Audio saved to temp file: {temp_audio.name}")

#         # Create output path for processed video
#         output_filename = f"processed_{uuid.uuid4()}.mp4"
#         output_path = os.path.join(PROCESSED_FOLDER, output_filename)

#         print("[UPLOAD] Starting processing with parameters:")
#         for key in request.form:
#             print(f"  {key}: {request.form[key]}")

#         # Process the video
#         processed_path = process_video_file(temp_video.name, output_path, request.form, audio_path)
#         abs_path = os.path.abspath(processed_path)
#         print(f"[UPLOAD] Returning processed URI: {abs_path}")

#         return jsonify({
#             "processed_video_uri": abs_path
#         })

#     except Exception as e:
#         print(f"[ERROR] Upload failed: {e}")
#         traceback.print_exc()
#         return jsonify({"error": str(e)}), 500

#     finally:
#         # Clean up temp video file
#         if temp_video is not None:
#             try:
#                 if os.path.exists(temp_video.name):
#                     os.unlink(temp_video.name)
#                     print(f"[CLEANUP] Deleted temp video file: {temp_video.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp video file: {e}")
        
#         # Clean up temp audio file
#         if temp_audio is not None:
#             try:
#                 if os.path.exists(temp_audio.name):
#                     os.unlink(temp_audio.name)
#                     print(f"[CLEANUP] Deleted temp audio file: {temp_audio.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp audio file: {e}")

# if __name__ == '__main__':
#     print("[SERVER] Flask server starting on port 5000...")
#     app.run(host='0.0.0.0', port=5000, debug=True)


# import os
# import uuid
# import traceback
# import tempfile
# from flask import Flask, request, jsonify, send_from_directory
# from flask_cors import CORS
# from werkzeug.utils import secure_filename
# from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip, AudioFileClip

# import moviepy.config as mpyconf

# # Configure ImageMagick path
# mpyconf.change_settings({
#     "IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
# })

# app = Flask(__name__)
# CORS(app)

# PROCESSED_FOLDER = 'processed'
# os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# def process_video_file(input_path, output_path, params, audio_path=None):
#     clip = None
#     audio_clip = None
#     audio_subclip = None
#     txt_clip = None
#     video = None
    
#     try:
#         print(f"[PROCESSING] Loading video: {input_path}")
#         clip = VideoFileClip(input_path)
        
#         # Get trim parameters
#         start_time = float(params.get('start_time', 0))
#         end_time = params.get('end_time')
#         end_time = float(end_time) if end_time else clip.duration
        
#         print(f"[PROCESSING] Trimming video from {start_time}s to {end_time}s")
#         clip = clip.subclip(start_time, end_time)
#         video_w, video_h = clip.size
#         trim_duration = end_time - start_time

#         # Handle audio replacement if audio file is provided
#         if audio_path and os.path.exists(audio_path):
#             print(f"[PROCESSING] Adding audio from: {audio_path}")
#             audio_start_time = float(params.get('audio_start_time', 0))
#             audio_clip = AudioFileClip(audio_path)
#             print(f"[PROCESSING] Audio start time: {audio_start_time}s")
#             print(f"[PROCESSING] Trim duration: {trim_duration}s")
            
#             if audio_start_time < audio_clip.duration:
#                 available_audio_duration = min(trim_duration, audio_clip.duration - audio_start_time)
#                 audio_subclip = audio_clip.subclip(audio_start_time, audio_start_time + available_audio_duration)
                
#                 if available_audio_duration < trim_duration:
#                     print(f"[PROCESSING] Audio shorter than video. Available: {available_audio_duration}s, needed: {trim_duration}s")
                
#                 print(f"[PROCESSING] Using audio from {audio_start_time}s to {audio_start_time + available_audio_duration}s")
#                 clip = clip.set_audio(audio_subclip)
#             else:
#                 print(f"[PROCESSING] Audio start time ({audio_start_time}s) exceeds audio duration ({audio_clip.duration}s)")
#                 clip = clip.set_audio(None)

#         # Get positions (center-based from React Native)
#         center_x = int(float(params.get('pos_x', 0)))
#         center_y = int(float(params.get('pos_y', 0)))

#         if params.get('text'):
#             print("[PROCESSING] Adding text overlay...")
#             txt_clip = TextClip(
#                 params['text'],
#                 fontsize=int(float(params.get('font_size', 48))),
#                 color=params.get('font_color', 'white'),
#                 bg_color=params.get('background_color', 'transparent') if params.get('background_color') != 'transparent' else 'none'
#             )
#             text_w, text_h = txt_clip.size
#             top_left_x = center_x - (text_w // 2)
#             top_left_y = center_y - (text_h // 2)
#             top_left_x = max(0, min(top_left_x, video_w - text_w))
#             top_left_y = max(0, min(top_left_y, video_h - text_h))
#             print(f"[PROCESSING] Text dimensions: {text_w}x{text_h}")
#             print(f"[PROCESSING] Center: ({center_x}, {center_y}) → Top-left: ({top_left_x}, {top_left_y})")
            
#             txt_clip = (
#                 txt_clip
#                 .set_position((top_left_x, top_left_y))
#                 .set_opacity(float(params.get('opacity', 1.0)))
#                 .set_duration(clip.duration)
#             )
#             video = CompositeVideoClip([clip, txt_clip])
#         else:
#             video = clip

#         if not video.audio and clip.audio:
#             video = video.set_audio(clip.audio)

#         print(f"[PROCESSING] Writing output to: {output_path}")
#         # Use specific codecs that work well with audio
#         video.write_videofile(
#             output_path, 
#             codec="libx264", 
#             audio_codec="aac",
#             temp_audiofile="temp-audio.m4a",
#             remove_temp=True
#         )
        
#         print("[SUCCESS] Processing complete.")
#         return output_path
        
#     except Exception as e:
#         print(f"[ERROR] Processing failed: {e}")
#         traceback.print_exc()
#         raise e
        
#     finally:
#         # Clean up clips in the correct order
#         try:
#             if video and video != clip:
#                 video.close()
#             if txt_clip:
#                 txt_clip.close()
#             if audio_subclip:
#                 audio_subclip.close()
#             if audio_clip:
#                 audio_clip.close()
#             if clip:
#                 clip.close()
#         except Exception as cleanup_error:
#             print(f"[WARNING] Cleanup error: {cleanup_error}")

# # NEW: Route to serve processed video files
# @app.route('/processed-videos/<filename>')
# def serve_processed_video(filename):
#     """Serve processed video files to clients"""
#     try:
#         print(f"[SERVE] Serving video file: {filename}")
#         return send_from_directory(
#             PROCESSED_FOLDER,
#             filename,
#             as_attachment=False,  # Allow direct playback in browser/video players
#             mimetype='video/mp4'
#         )
#     except FileNotFoundError:
#         print(f"[ERROR] Video file not found: {filename}")
#         return jsonify({"error": "Video file not found"}), 404
#     except Exception as e:
#         print(f"[ERROR] Failed to serve video: {e}")
#         return jsonify({"error": "Failed to serve video"}), 500

# @app.route('/process-video', methods=['POST'])
# def handle_video_upload():
#     temp_video = None
#     temp_audio = None
    
#     try:
#         if 'video' not in request.files:
#             print("[ERROR] No video part in request.")
#             return jsonify({"error": "No video file uploaded"}), 400

#         # Create temp video file
#         video_file = request.files['video']
#         temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         video_file.save(temp_video.name)
#         temp_video.close()  # Close so MoviePy can access it on Windows
        
#         print(f"[UPLOAD] Video saved to temp file: {temp_video.name}")

#         # Handle optional audio file
#         audio_path = None
#         if 'audio' in request.files:
#             audio_file = request.files['audio']
#             temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
#             audio_file.save(temp_audio.name)
#             temp_audio.close()  # Close so MoviePy can access it on Windows
#             audio_path = temp_audio.name
#             print(f"[UPLOAD] Audio saved to temp file: {temp_audio.name}")

#         # Create output path for processed video
#         output_filename = f"processed_{uuid.uuid4()}.mp4"
#         output_path = os.path.join(PROCESSED_FOLDER, output_filename)

#         print("[UPLOAD] Starting processing with parameters:")
#         for key in request.form:
#             print(f"  {key}: {request.form[key]}")

#         # Process the video
#         processed_path = process_video_file(temp_video.name, output_path, request.form, audio_path)
        
#         # NEW: Return network-accessible URL instead of local file path
#         video_url = f"http://{request.host}/processed-videos/{output_filename}"
#         print(f"[UPLOAD] Returning video URL: {video_url}")

#         return jsonify({
#             "processed_video_uri": video_url
#         })

#     except Exception as e:
#         print(f"[ERROR] Upload failed: {e}")
#         traceback.print_exc()
#         return jsonify({"error": str(e)}), 500

#     finally:
#         # Clean up temp video file
#         if temp_video is not None:
#             try:
#                 if os.path.exists(temp_video.name):
#                     os.unlink(temp_video.name)
#                     print(f"[CLEANUP] Deleted temp video file: {temp_video.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp video file: {e}")
        
#         # Clean up temp audio file
#         if temp_audio is not None:
#             try:
#                 if os.path.exists(temp_audio.name):
#                     os.unlink(temp_audio.name)
#                     print(f"[CLEANUP] Deleted temp audio file: {temp_audio.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp audio file: {e}")

# if __name__ == '__main__':
#     print("[SERVER] Flask server starting on port 5000...")
#     # IMPORTANT: Use host='0.0.0.0' to make server accessible from mobile devices
#     app.run(host='0.0.0.0', port=5000, debug=True)

# import os
# import uuid
# import traceback
# import tempfile
# import numpy as np
# from flask import Flask, request, jsonify, send_from_directory
# from flask_cors import CORS
# from werkzeug.utils import secure_filename
# from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
# from PIL import Image, ImageDraw, ImageFont
# import power_text

# app = Flask(__name__)
# CORS(app)

# PROCESSED_FOLDER = 'processed'
# os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# def create_text_with_emoji_powertext(text, font_size=48, color='white', bg_color='transparent', size=(800, 200)):
#     """Create text image with emoji support using PowerText"""
#     try:
#         print(f"[TEXT] Creating text with PowerText: '{text}' | Size: {font_size} | Color: {color}")
        
#         # Create image with transparent background
#         if bg_color == 'transparent':
#             img = Image.new('RGBA', size, (0, 0, 0, 0))
#         else:
#             # Convert hex color to RGB
#             if bg_color.startswith('#'):
#                 bg_rgb = tuple(int(bg_color[i:i+2], 16) for i in (1, 3, 5))
#                 img = Image.new('RGBA', size, bg_rgb + (255,))
#             else:
#                 img = Image.new('RGBA', size, (0, 0, 0, 255))
        
#         # Load font - try multiple font paths
#         font = None
#         font_paths = [
#             "arial.ttf",
#             "C:/Windows/Fonts/arial.ttf",
#             "C:/Windows/Fonts/calibri.ttf",
#             "C:/Windows/Fonts/segoeui.ttf"
#         ]
        
#         for font_path in font_paths:
#             try:
#                 font = ImageFont.truetype(font_path, font_size)
#                 print(f"[TEXT] Successfully loaded font: {font_path}")
#                 break
#             except:
#                 continue
        
#         if not font:
#             font = ImageFont.load_default()
#             print("[TEXT] Using default font")
        
#         # Convert text color from hex to RGB if needed
#         if color.startswith('#'):
#             text_color = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
#         elif color == 'white':
#             text_color = (255, 255, 255)
#         elif color == 'black':
#             text_color = (0, 0, 0)
#         elif color.lower() == 'red':
#             text_color = (255, 0, 0)
#         elif color.lower() == 'green':
#             text_color = (0, 255, 0)
#         elif color.lower() == 'blue':
#             text_color = (0, 0, 255)
#         else:
#             text_color = (255, 255, 255)  # Default to white
        
#         print(f"[TEXT] Using text color RGB: {text_color}")
        
#         # Use PowerText to render text with emojis
#         power_text.draw_text(
#             img,
#             (10, 10),  # Starting position
#             text,
#             [
#                 power_text.Font(font, lambda _: True, text_color)  # Use font for all characters
#             ],
#             text_color,  # Default text color
#             max_x=size[0] - 20,  # Max width (with padding)
#             max_y=size[1] - 20,  # Max height (with padding)
#             has_emoji=True,  # Enable emoji support
#             end_text="..."  # Truncation symbol if needed
#         )
        
#         print("[TEXT] Text with emoji successfully created using PowerText")
#         return np.array(img)
        
#     except Exception as e:
#         print(f"[ERROR] Failed to create emoji text with PowerText: {e}")
#         traceback.print_exc()
#         # Fallback: create simple colored rectangle with error text
#         fallback_img = Image.new('RGBA', size, (255, 0, 0, 128))
#         draw = ImageDraw.Draw(fallback_img)
#         draw.text((10, 10), "TEXT ERROR", fill=(255, 255, 255, 255))
#         return np.array(fallback_img)

# def process_video_file(input_path, output_path, params, audio_path=None):
#     clip = None
#     audio_clip = None
#     audio_subclip = None
#     text_img_clip = None
#     video = None
    
#     try:
#         print(f"[PROCESSING] Loading video: {input_path}")
#         clip = VideoFileClip(input_path)
        
#         # Get trim parameters
#         start_time = float(params.get('start_time', 0))
#         end_time = params.get('end_time')
#         end_time = float(end_time) if end_time else clip.duration
        
#         print(f"[PROCESSING] Trimming video from {start_time}s to {end_time}s")
#         clip = clip.subclip(start_time, end_time)
#         video_w, video_h = clip.size
#         trim_duration = end_time - start_time

#         # Handle audio replacement if audio file is provided
#         if audio_path and os.path.exists(audio_path):
#             print(f"[PROCESSING] Adding audio from: {audio_path}")
#             audio_start_time = float(params.get('audio_start_time', 0))
#             audio_clip = AudioFileClip(audio_path)
#             print(f"[PROCESSING] Audio start time: {audio_start_time}s")
#             print(f"[PROCESSING] Trim duration: {trim_duration}s")
            
#             if audio_start_time < audio_clip.duration:
#                 available_audio_duration = min(trim_duration, audio_clip.duration - audio_start_time)
#                 audio_subclip = audio_clip.subclip(audio_start_time, audio_start_time + available_audio_duration)
                
#                 if available_audio_duration < trim_duration:
#                     print(f"[PROCESSING] Audio shorter than video. Available: {available_audio_duration}s, needed: {trim_duration}s")
                
#                 print(f"[PROCESSING] Using audio from {audio_start_time}s to {audio_start_time + available_audio_duration}s")
#                 clip = clip.set_audio(audio_subclip)
#             else:
#                 print(f"[PROCESSING] Audio start time ({audio_start_time}s) exceeds audio duration ({audio_clip.duration}s)")
#                 clip = clip.set_audio(None)

#         # Handle text overlay using PowerText instead of Pilmoji
#         if params.get('text'):
#             print("[PROCESSING] Adding text overlay with PowerText emoji support...")
            
#             # Get text parameters
#             text = params.get('text', 'Sample Text')
#             font_size = int(float(params.get('font_size', 48)))
#             font_color = params.get('font_color', 'white')
#             bg_color = params.get('background_color', 'transparent')
            
#             # Get position parameters (center-based from React Native)
#             center_x = int(float(params.get('pos_x', video_w // 2)))
#             center_y = int(float(params.get('pos_y', video_h // 2)))
            
#             # Create text image with emoji support using PowerText
#             text_size = (min(video_w, 1000), min(video_h // 3, 300))
#             text_array = create_text_with_emoji_powertext(text, font_size, font_color, bg_color, text_size)
            
#             # Create ImageClip from the text array
#             text_img_clip = ImageClip(text_array, duration=clip.duration, transparent=True)
            
#             # Calculate position (convert center-based to top-left based)
#             text_w, text_h = text_size
#             top_left_x = center_x - (text_w // 2)
#             top_left_y = center_y - (text_h // 2)
            
#             # Clamp positions to keep text within video bounds
#             top_left_x = max(0, min(top_left_x, video_w - text_w))
#             top_left_y = max(0, min(top_left_y, video_h - text_h))
            
#             print(f"[PROCESSING] Text canvas size: {text_w}x{text_h}")
#             print(f"[PROCESSING] Center: ({center_x}, {center_y}) → Top-left: ({top_left_x}, {top_left_y})")
            
#             # Set position and opacity
#             text_img_clip = text_img_clip.set_position((top_left_x, top_left_y))
#             text_img_clip = text_img_clip.set_opacity(float(params.get('opacity', 1.0)))
            
#             video = CompositeVideoClip([clip, text_img_clip])
#         else:
#             video = clip

#         if not video.audio and clip.audio:
#             video = video.set_audio(clip.audio)

#         print(f"[PROCESSING] Writing output to: {output_path}")
#         video.write_videofile(
#             output_path, 
#             codec="libx264", 
#             audio_codec="aac",
#             temp_audiofile="temp-audio.m4a",
#             remove_temp=True,
#             verbose=False,
#             logger=None
#         )
        
#         print("[SUCCESS] Processing complete.")
#         return output_path
        
#     except Exception as e:
#         print(f"[ERROR] Processing failed: {e}")
#         traceback.print_exc()
#         raise e
        
#     finally:
#         # Clean up clips in the correct order
#         try:
#             if video and video != clip:
#                 video.close()
#             if text_img_clip:
#                 text_img_clip.close()
#             if audio_subclip:
#                 audio_subclip.close()
#             if audio_clip:
#                 audio_clip.close()
#             if clip:
#                 clip.close()
#         except Exception as cleanup_error:
#             print(f"[WARNING] Cleanup error: {cleanup_error}")

# # Route to serve processed video files
# @app.route('/processed-videos/<filename>')
# def serve_processed_video(filename):
#     """Serve processed video files to clients"""
#     try:
#         print(f"[SERVE] Serving video file: {filename}")
#         return send_from_directory(
#             PROCESSED_FOLDER,
#             filename,
#             as_attachment=False,
#             mimetype='video/mp4'
#         )
#     except FileNotFoundError:
#         print(f"[ERROR] Video file not found: {filename}")
#         return jsonify({"error": "Video file not found"}), 404
#     except Exception as e:
#         print(f"[ERROR] Failed to serve video: {e}")
#         return jsonify({"error": "Failed to serve video"}), 500

# @app.route('/process-video', methods=['POST'])
# def handle_video_upload():
#     temp_video = None
#     temp_audio = None
    
#     try:
#         if 'video' not in request.files:
#             print("[ERROR] No video part in request.")
#             return jsonify({"error": "No video file uploaded"}), 400

#         # Create temp video file
#         video_file = request.files['video']
#         temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         video_file.save(temp_video.name)
#         temp_video.close()
        
#         print(f"[UPLOAD] Video saved to temp file: {temp_video.name}")

#         # Handle optional audio file
#         audio_path = None
#         if 'audio' in request.files:
#             audio_file = request.files['audio']
#             temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
#             audio_file.save(temp_audio.name)
#             temp_audio.close()
#             audio_path = temp_audio.name
#             print(f"[UPLOAD] Audio saved to temp file: {temp_audio.name}")

#         # Create output path for processed video
#         output_filename = f"processed_{uuid.uuid4()}.mp4"
#         output_path = os.path.join(PROCESSED_FOLDER, output_filename)

#         print("[UPLOAD] Starting processing with parameters:")
#         for key in request.form:
#             print(f"  {key}: {request.form[key]}")

#         # Process the video
#         processed_path = process_video_file(temp_video.name, output_path, request.form, audio_path)
        
#         # Return network-accessible URL
#         video_url = f"http://{request.host}/processed-videos/{output_filename}"
#         print(f"[UPLOAD] Returning video URL: {video_url}")

#         return jsonify({
#             "processed_video_uri": video_url,
#             "success": True,
#             "message": "Video processed successfully with PowerText emoji support"
#         })

#     except Exception as e:
#         print(f"[ERROR] Upload failed: {e}")
#         traceback.print_exc()
#         return jsonify({
#             "error": str(e),
#             "success": False,
#             "message": "Video processing failed"
#         }), 500

#     finally:
#         # Clean up temp video file
#         if temp_video is not None:
#             try:
#                 if os.path.exists(temp_video.name):
#                     os.unlink(temp_video.name)
#                     print(f"[CLEANUP] Deleted temp video file: {temp_video.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp video file: {e}")
        
#         # Clean up temp audio file
#         if temp_audio is not None:
#             try:
#                 if os.path.exists(temp_audio.name):
#                     os.unlink(temp_audio.name)
#                     print(f"[CLEANUP] Deleted temp audio file: {temp_audio.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp audio file: {e}")

# if __name__ == '__main__':
#     print("="*50)
#     print("[SERVER] Video Processing Server with PowerText Emoji Support")
#     print("[SERVER] Features:")
#     print("[SERVER] - Video trimming and audio overlay")
#     print("[SERVER] - Full-color emoji text rendering (PowerText)")
#     print("[SERVER] - HTTP video serving")
#     print("[SERVER] - Automatic temp file cleanup")
#     print("[SERVER] - Cross-platform compatibility")
#     print("="*50)
#     print("[SERVER] Flask server starting on port 5000...")
#     print("[SERVER] Make sure to install: pip install PowerText[full]")
#     print("="*50)
    
#     app.run(host='0.0.0.0', port=5000, debug=True)


#----------------------------------

# import os
# import uuid
# import traceback
# import tempfile
# import numpy as np
# from flask import Flask, request, jsonify, send_from_directory
# from flask_cors import CORS
# from werkzeug.utils import secure_filename
# from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
# from PIL import Image, ImageDraw, ImageFont, ImageColor
# from pilmoji import Pilmoji

# app = Flask(__name__)
# CORS(app)

# PROCESSED_FOLDER = 'processed'
# os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# # def create_text_with_emoji_pilmoji(text, font_size=48, color='white', bg_color='transparent', size=(800, 200)):
# #     """Create text image with emoji support using Pilmoji"""
# #     try:
# #         print(f"[TEXT] Creating text with Pilmoji: '{text}' | Size: {font_size} | Color: {color}")
        
# #         # Create image with transparent background
# #         if bg_color == 'transparent':
# #             img = Image.new('RGBA', size, (0, 0, 0, 0))
# #         else:
# #             # Convert hex color to RGB
# #             if bg_color.startswith('#'):
# #                 bg_rgb = tuple(int(bg_color[i:i+2], 16) for i in (1, 3, 5))
# #                 img = Image.new('RGBA', size, bg_rgb + (255,))
# #             else:
# #                 img = Image.new('RGBA', size, (0, 0, 0, 255))
        
# #         # Load font - try multiple font paths
# #         font = None
# #         macos_font_paths = [
# #           "Arial.ttf",
# #           "/System/Library/Fonts/Arial.ttf",
# #           "/System/Library/Fonts/Helvetica.ttc",
# #           "/Library/Fonts/Arial.ttf",
# #           "/System/Library/Fonts/Times.ttc"
# #         ]
          
# #         for path in macos_font_paths:
# #           try:
# #               font = ImageFont.truetype(font_path, font_size)
# #               print(f"[TEXT] Successfully loaded font: {font_path}")
# #               break
# #           except:
# #               continue
        
# #         if not font:
# #             font = ImageFont.load_default()
# #             print("[TEXT] Using default font")
        
# #         # Convert text color from hex to RGB if needed
# #         if color.startswith('#'):
# #             text_color = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
# #         elif color == 'white':
# #             text_color = (255, 255, 255)
# #         elif color == 'black':
# #             text_color = (0, 0, 0)
# #         elif color.lower() == 'red':
# #             text_color = (255, 0, 0)
# #         elif color.lower() == 'green':
# #             text_color = (0, 255, 0)
# #         elif color.lower() == 'blue':
# #             text_color = (0, 0, 255)
# #         else:
# #             text_color = (255, 255, 255)  # Default to white
        
# #         print(f"[TEXT] Using text color RGB: {text_color}")
        
# #         # Use Pilmoji with auto-detection (no explicit source needed)
# #         with Pilmoji(img) as pilmoji:
# #             # Get text dimensions for centering
# #             text_width = len(text) * font_size // 2
# #             text_height = font_size
            
# #             x = (size[0] - text_width) // 2
# #             y = (size[1] - text_height) // 2
            
# #             print(f"[TEXT] Text dimensions: {text_width}x{text_height} at position ({x}, {y})")
            
# #             # Render text with emoji support
# #             pilmoji.text((x, y), text, fill=text_color, font=font)
        
# #         print("[TEXT] Text with emoji successfully created using Pilmoji")
# #         return np.array(img)
        
# #     except Exception as e:
# #         print(f"[ERROR] Failed to create emoji text with Pilmoji: {e}")
# #         traceback.print_exc()
        
# #         # Enhanced fallback with better error text
# #         try:
# #             fallback_img = Image.new('RGBA', size, (50, 50, 50, 200))
# #             draw = ImageDraw.Draw(fallback_img)
            
# #             # Try to render text without emojis as fallback
# #             try:
# #                 # Remove emojis for fallback rendering
# #                 clean_text = ''.join(char for char in text if ord(char) < 0x1F600)
# #                 if clean_text.strip():
# #                     font_fallback = ImageFont.load_default()
# #                     draw.text((10, 10), clean_text, fill=(255, 255, 255, 255), font=font_fallback)
# #                 else:
# #                     draw.text((10, 10), "EMOJI ERROR", fill=(255, 255, 255, 255))
# #             except:
# #                 draw.text((10, 10), "TEXT ERROR", fill=(255, 255, 255, 255))
            
# #             return np.array(fallback_img)
# #         except:
# #             # Ultimate fallback
# #             return np.full((size[1], size[0], 4), [255, 0, 0, 128], dtype=np.uint8)

# # def create_text_with_emoji_pilmoji(text, font_size=48, color='white',bg_color='transparent', size=(800, 200)):
# #     """
# #     Create a NumPy array of an RGBA image containing text with full-color emojis
# #     and a tight background box behind the text when bg_color != 'transparent'.
# #     """
# #     # 1. Always start with a transparent canvas
# #     img = Image.new('RGBA', size, (0, 0, 0, 0))
# #     draw = ImageDraw.Draw(img)

# #     # 2. Load a font, falling back to default if necessary
# #     font = None
# #     for path in ("arial.ttf","C:/Windows/Fonts/arial.ttf","C:/Windows/Fonts/segoeui.ttf"):
# #         try:
# #             font = ImageFont.truetype(path, font_size)
# #             break
# #         except:
# #             continue
# #     if font is None:
# #         font = ImageFont.load_default()

# #     # 3. Measure the text (accounts for emojis)
# #     bbox = draw.textbbox((0, 0), text, font=font)
# #     text_w = bbox[2] - bbox[0]
# #     text_h = bbox[3] - bbox[1]

# #     # 4. Compute centered position for the text
# #     x = (size[0] - text_w) // 2
# #     y = (size[1] - text_h) // 2

# #     # 5. Draw a tight background box if needed
# #     if bg_color != 'transparent':
# #         # Convert bg_color to RGB tuple
# #         box_rgb = ImageColor.getrgb(bg_color)
# #         padding = int(font_size * 0.2)
# #         box_coords = [
# #             x - padding, y - padding,
# #             x + text_w + padding, y + text_h + padding
# #         ]
# #         draw.rectangle(box_coords, fill=box_rgb + (255,))

# #     # 6. Render the text with Pilmoji (auto-detected emoji source)
# #     text_rgb = ImageColor.getrgb(color)
# #     with Pilmoji(img) as pilmoji:
# #         pilmoji.text((x, y), text, fill=text_rgb, font=font)

# #     # 7. Return as NumPy array for MoviePy ImageClip
# #     return np.array(img)

# # def create_text_with_emoji_pilmoji(text, font_size=48, color='white',bg_color='transparent', size=(800, 200)):
#     # """
#     # Create a NumPy array of an RGBA image containing text with full-color emojis
#     # and a tight, rounded background box behind the text when bg_color != 'transparent'.
#     # """
#     # # 1. Always start with a transparent canvas
#     # img = Image.new('RGBA', size, (0, 0, 0, 0))
#     # draw = ImageDraw.Draw(img)

#     # # 2. Load a font, falling back to default if necessary
#     # font = None
#     # # for path in ("arial.ttf","C:/Windows/Fonts/arial.ttf","C:/Windows/Fonts/segoeui.ttf"):
#     # macos_font_paths = [
#     #     "Arial.ttf",
#     #     "/System/Library/Fonts/Arial.ttf",
#     #     "/System/Library/Fonts/Helvetica.ttc",
#     #     "/Library/Fonts/Arial.ttf",
#     #     "/System/Library/Fonts/Times.ttc"
#     # ]
    
#     # for path in macos_font_paths:
#     #     try:
#     #         font = ImageFont.truetype(path, font_size)
#     #         break
#     #     except:
#     #         continue
#     # if font is None:
#     #     font = ImageFont.load_default()

#     # # 3. Measure the text (accounts for emojis)
#     # bbox = draw.textbbox((0, 0), text, font=font)
#     # text_w = bbox[2] - bbox[0]
#     # text_h = bbox[3] - bbox[1]

#     # # 4. Compute centered position for the text
#     # x = (size[0] - text_w) // 2
#     # y = (size[1] - text_h) // 2

#     # # # 5. Draw a tight, rounded background box if needed
#     # # if bg_color != 'transparent':
#     # #     box_rgb = ImageColor.getrgb(bg_color)
#     # #     pad_x = int(font_size * 0.2)   # extra horizontal padding
#     # #     pad_y = int(font_size * 0.4)   # vertical padding
#     # #     box_coords = [
#     # #         x - pad_x, y - pad_y,
#     # #         x + text_w + pad_x, y + text_h + pad_y
#     # #     ]
#     # #     # Draw rounded rectangle
#     # #     draw.rounded_rectangle(box_coords, radius=pad_y, fill=box_rgb + (255,))

#     # # 5. Draw a tight, rounded background box if needed
#     # if bg_color != 'transparent':
#     #     box_rgb = ImageColor.getrgb(bg_color)
#     #     # smaller, even horizontal padding
#     #     pad_x = 20
#     #     pad_y = 10
#     #     # get exact text bounds
#     #     tb = draw.textbbox((0, 0), text, font=font)
#     #     # shift to centered coordinates and apply padding
#     #     box_coords = [
#     #         x + tb[0] - pad_x,
#     #         y + tb[1] - pad_y,
#     #         x + tb[2] + pad_x,
#     #         y + tb[3] + pad_y
#     #     ]
#     #     draw.rounded_rectangle(box_coords, radius=pad_y, fill=box_rgb + (255,))

#     # # 6. Render the text with Pilmoji (auto-detected emoji source)
#     # text_rgb = ImageColor.getrgb(color)
#     # with Pilmoji(img) as pilmoji:
#     #     pilmoji.text((x, y), text, fill=text_rgb, font=font)

#     # # 7. Return as NumPy array for MoviePy ImageClip
#     # return np.array(img)

# def create_text_with_emoji_pilmoji_fixed_macos(text, font_size=48, color='white', bg_color='transparent', 
#                                                size=(800, 200), text_position=None):
#     """
#     FIXED VERSION FOR macOS: Create text image without forcing center alignment
    
#     Args:
#         text_position: (x, y) tuple for exact text placement within canvas, or None for center
#     """
#     # Create transparent canvas
#     img = Image.new('RGBA', size, (0, 0, 0, 0))
#     draw = ImageDraw.Draw(img)

#     # Load font - Updated for macOS paths
#     font = None
#     macos_font_paths = [
#         "Arial.ttf",
#         "/System/Library/Fonts/Arial.ttf",
#         "/System/Library/Fonts/Helvetica.ttc",
#         "/Library/Fonts/Arial.ttf",
#         "/System/Library/Fonts/Times.ttc",
#         "/System/Library/Fonts/Courier.ttc"
#     ]
    
#     for path in macos_font_paths:
#         try:
#             font = ImageFont.truetype(path, font_size)
#             print(f"[TEXT] Successfully loaded font: {path}")
#             break
#         except Exception as e:
#             print(f"[TEXT] Failed to load font {path}: {e}")
#             continue
    
#     if font is None:
#         font = ImageFont.load_default()
#         print("[TEXT] Using default font")

#     # Measure text dimensions
#     bbox = draw.textbbox((0, 0), text, font=font)
#     text_w = bbox[2] - bbox[0]
#     text_h = bbox[3] - bbox[1]

#     # FIXED: Use provided position or center if None
#     if text_position is not None:
#         x, y = text_position
#         print(f"[TEXT] Positioning text at exact coordinates: ({x}, {y})")
#     else:
#         x = (size[0] - text_w) // 2
#         y = (size[1] - text_h) // 2
#         print(f"[TEXT] Centering text at: ({x}, {y})")

#     # Draw background if needed
#     if bg_color != 'transparent':
#         box_rgb = ImageColor.getrgb(bg_color)
#         pad_x = 0
#         pad_y = 0
#         tb = draw.textbbox((0, 0), text, font=font)
#         box_coords = [
#             x + tb[0] - pad_x,
#             y + tb[1] - pad_y,
#             x + tb[2] + pad_x,
#             y + tb[3] + pad_y
#         ]
#         draw.rounded_rectangle(box_coords, radius=pad_y, fill=box_rgb + (255,))

#     # Render text with Pilmoji at exact position
#     text_rgb = ImageColor.getrgb(color)
#     with Pilmoji(img) as pilmoji:
#         pilmoji.text((x, y), text, fill=text_rgb, font=font)

#     print(f"[TEXT] Text rendered: '{text}' at ({x}, {y}) with font size {font_size}")
#     return np.array(img)


# def validate_font_scaling(font_size, video_w, video_h, preview_w, preview_h):
#     """
#     Validate and adjust font size if scaling appears incorrect
#     """
#     # Expected scale factor should be reasonable (typically 2-8x)
#     if preview_h > 0:
#         scale_factor = video_h / preview_h
#         if scale_factor < 1.5 or scale_factor > 10:
#             print(f"[WARNING] Unusual scale factor: {scale_factor}")
#             print(f"[WARNING] Video: {video_w}x{video_h}, Preview: {preview_w}x{preview_h}")

#             # Apply reasonable limits
#             if scale_factor < 1.5:
#                 font_size = max(font_size, 32)  # Minimum font size
#             elif scale_factor > 10:
#                 font_size = min(font_size, video_h / 20)  # Max 5% of video height

#     return font_size


# def process_video_file(input_path, output_path, params, audio_path=None):
#     clip = None
#     audio_clip = None
#     audio_subclip = None
#     text_img_clip = None
#     video = None
    
#     try:
#         print(f"[PROCESSING] Loading video: {input_path}")
#         clip = VideoFileClip(input_path)
        
#         # Get trim parameters
#         start_time = float(params.get('start_time', 0))
#         end_time = params.get('end_time')
#         end_time = float(end_time) if end_time else clip.duration

#         # FIX: Clamp end_time to actual video duration
#         end_time = min(end_time, clip.duration)
#         start_time = min(start_time, clip.duration)

#         if start_time >= end_time:  # Defensive check
#           end_time = min(start_time + 1, video_duration)
#           clip = clip.subclip(start_time, end_time)
        
#         # print(f"[PROCESSING] Trimming video from {start_time}s to {end_time}s")
#         print(f"[PROCESSING] Original video duration: {clip.duration}s")
#         print(f"[PROCESSING] Requested trim: {params.get('start_time', 0)}s to {params.get('end_time')}s")
#         print(f"[PROCESSING] Actual trim (clamped): {start_time}s to {end_time}s")
#         clip = clip.subclip(start_time, end_time)
#         video_w, video_h = clip.size
#         trim_duration = end_time - start_time

#         # Handle audio replacement if audio file is provided
#         if audio_path and os.path.exists(audio_path):
#             print(f"[PROCESSING] Adding audio from: {audio_path}")
#             audio_start_time = float(params.get('audio_start_time', 0))
#             audio_clip = AudioFileClip(audio_path)
#             print(f"[PROCESSING] Audio start time: {audio_start_time}s")
#             print(f"[PROCESSING] Trim duration: {trim_duration}s")
            
#             if audio_start_time < audio_clip.duration:
#                 available_audio_duration = min(trim_duration, audio_clip.duration - audio_start_time)
#                 audio_subclip = audio_clip.subclip(audio_start_time, audio_start_time + available_audio_duration)
                
#                 if available_audio_duration < trim_duration:
#                     print(f"[PROCESSING] Audio shorter than video. Available: {available_audio_duration}s, needed: {trim_duration}s")
                
#                 print(f"[PROCESSING] Using audio from {audio_start_time}s to {audio_start_time + available_audio_duration}s")
#                 clip = clip.set_audio(audio_subclip)
#             else:
#                 print(f"[PROCESSING] Audio start time ({audio_start_time}s) exceeds audio duration ({audio_clip.duration}s)")
#                 clip = clip.set_audio(None)

#         # Handle text overlay using Pilmoji
#         # if params.get('text'):
#         #     print("[PROCESSING] Adding text overlay with Pilmoji emoji support...")
            
#         #     # Get text parameters
#         #     text = params.get('text', 'Sample Text')
#         #     font_size = int(float(params.get('font_size', 48)))
#         #     font_color = params.get('font_color', 'white')
#         #     bg_color = params.get('background_color', 'transparent')
            
#         #     # Get position parameters (center-based from React Native)
#         #     center_x = int(float(params.get('pos_x', video_w // 2)))
#         #     center_y = int(float(params.get('pos_y', video_h // 2)))
            
#         #     # Create text image with emoji support using Pilmoji
#         #     text_size = (min(video_w, 1000), min(video_h // 3, 300))
#         #     text_array = create_text_with_emoji_pilmoji(text, font_size, font_color, bg_color, text_size)
            
#         #     # Create ImageClip from the text array
#         #     text_img_clip = ImageClip(text_array, duration=clip.duration, transparent=True)
            
#         #     # Calculate position (convert center-based to top-left based)
#         #     text_w, text_h = text_size
#         #     top_left_x = center_x - (text_w // 2)
#         #     top_left_y = center_y - (text_h // 2)
            
#         #     # Clamp positions to keep text within video bounds
#         #     top_left_x = max(0, min(top_left_x, video_w - text_w))
#         #     top_left_y = max(0, min(top_left_y, video_h - text_h))
            
#         #     print(f"[PROCESSING] Text canvas size: {text_w}x{text_h}")
#         #     print(f"[PROCESSING] Center: ({center_x}, {center_y}) → Top-left: ({top_left_x}, {top_left_y})")
            
#         #     # Set position and opacity
#         #     text_img_clip = text_img_clip.set_position((top_left_x, top_left_y))
#         #     text_img_clip = text_img_clip.set_opacity(float(params.get('opacity', 1.0)))
            
#         #     video = CompositeVideoClip([clip, text_img_clip])
#         # else:
#         #     video = clip

#         # Handle text overlay using Pilmoji - FIXED VERSION
#         if params.get('text'):
#             print("[PROCESSING] Adding text overlay with FIXED positioning for macOS...")
            
#             text = params.get('text', 'Sample Text')
#             font_size = int(float(params.get('font_size', 48)))
#             preview_h = float(params.get('preview_height', 0))
#             # if preview_h > 0:
#             #   font_size = validate_font_scaling(font_size, video_w, video_h,video_w, preview_h)
#             font_color = params.get('font_color', 'white')
#             bg_color = params.get('background_color', 'transparent')
            
#             # Get position parameters (center-based from React Native)
#             center_x = int(float(params.get('pos_x', video_w // 2)))
#             center_y = int(float(params.get('pos_y', video_h // 2))) - 18 # Position Vertical Value change here
#             # center_y = int(float(params.get('pos_y', video_h // 2))) # Position Vertical Value change here
            
#             print(f"[PROCESSING] Received position from frontend: center_x={center_x}, center_y={center_y}")
#             print(f"[PROCESSING] Video dimensions: {video_w}x{video_h}")
#             print(f"[PROCESSING] Font size: {font_size}")
            
#             # FIXED: Pre-calculate text dimensions for accurate positioning
#             temp_img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
#             temp_draw = ImageDraw.Draw(temp_img)
            
#             # Load font for measurement (macOS paths)
#             font = None
#             macos_font_paths = [
#                 "Arial.ttf",
#                 "/System/Library/Fonts/Arial.ttf",
#                 "/System/Library/Fonts/Helvetica.ttc",
#                 "/Library/Fonts/Arial.ttf",
#                 "/System/Library/Fonts/Times.ttc"
#             ]
            
#             for path in macos_font_paths:
#                 try:
#                     font = ImageFont.truetype(path,font_size)
#                     break
#                 except:
#                     continue
#             if font is None:
#                 font = ImageFont.load_default()
            
#             # Measure actual text dimensions
#             bbox = temp_draw.textbbox((0, 0), text, font=font)
#             text_w = bbox[2] - bbox[0]
#             text_h = bbox[3] - bbox[1]
            
#             print(f"[PROCESSING] Measured text dimensions: {text_w}x{text_h}")
            
#             # FIXED: Create video-sized canvas for precise positioning
#             canvas_w = video_w
#             canvas_h = video_h
            
#             # FIXED: Calculate exact text position within the canvas
#             # Convert center coordinates to top-left coordinates for text rendering
#             text_pos_x = center_x - text_w // 2
#             text_pos_y = center_y - text_h // 2
            
#             # Ensure text stays within video bounds
#             text_pos_x = max(0, min(text_pos_x, canvas_w - text_w))
#             text_pos_y = max(0, min(text_pos_y, canvas_h - text_h))
            
#             print(f"[PROCESSING] FIXED - Canvas size: {canvas_w}x{canvas_h}")
#             print(f"[PROCESSING] FIXED - Text will be positioned at: ({text_pos_x}, {text_pos_y})")
#             print(f"[PROCESSING] FIXED - Text bounds: ({text_pos_x}, {text_pos_y}) to ({text_pos_x + text_w}, {text_pos_y + text_h})")
            
#             # Create text image with exact positioning
#             text_array = create_text_with_emoji_pilmoji_fixed_macos(
#                 text, font_size, font_color, bg_color, 
#                 (canvas_w, canvas_h), 
#                 (text_pos_x, text_pos_y)
#             )
            
#             # Create ImageClip from the text array
#             text_img_clip = ImageClip(text_array, duration=clip.duration, transparent=True)
            
#             # Position canvas at origin since it's video-sized
#             # text_img_clip = text_img_clip.set_position((0, 0))
#             text_img_clip = text_img_clip.set_position((0, 0))
#             text_img_clip = text_img_clip.set_opacity(float(params.get('opacity', 1.0)))

            
#             print("[PROCESSING] FIXED - Final text positioning complete")
            
#             video = CompositeVideoClip([clip, text_img_clip])
#         else:
#             video = clip



#         if not video.audio and clip.audio:
#             video = video.set_audio(clip.audio)

#         print(f"[PROCESSING] Writing output to: {output_path}")
#         video.write_videofile(
#             output_path, 
#             codec="libx264", 
#             audio_codec="aac",
#             temp_audiofile="temp-audio.m4a",
#             remove_temp=True,
#             verbose=False,
#             logger=None
#         )
        
#         print("[SUCCESS] Processing complete.")
#         return output_path
        
#     except Exception as e:
#         print(f"[ERROR] Processing failed: {e}")
#         traceback.print_exc()
#         raise e
        
#     finally:
#         # Clean up clips in the correct order
#         try:
#             if video and video != clip:
#                 video.close()
#             if text_img_clip:
#                 text_img_clip.close()
#             if audio_subclip:
#                 audio_subclip.close()
#             if audio_clip:
#                 audio_clip.close()
#             if clip:
#                 clip.close()
#         except Exception as cleanup_error:
#             print(f"[WARNING] Cleanup error: {cleanup_error}")

# # Route to serve processed video files
# @app.route('/processed-videos/<filename>')
# def serve_processed_video(filename):
#     """Serve processed video files to clients"""
#     try:
#         print(f"[SERVE] Serving video file: {filename}")
#         return send_from_directory(
#             PROCESSED_FOLDER,
#             filename,
#             as_attachment=False,
#             mimetype='video/mp4'
#         )
#     except FileNotFoundError:
#         print(f"[ERROR] Video file not found: {filename}")
#         return jsonify({"error": "Video file not found"}), 404
#     except Exception as e:
#         print(f"[ERROR] Failed to serve video: {e}")
#         return jsonify({"error": "Failed to serve video"}), 500

# @app.route('/process-video', methods=['POST'])
# def handle_video_upload():
#     temp_video = None
#     temp_audio = None
    
#     try:
#         if 'video' not in request.files:
#             print("[ERROR] No video part in request.")
#             return jsonify({"error": "No video file uploaded"}), 400

#         # Create temp video file
#         video_file = request.files['video']
#         temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         video_file.save(temp_video.name)
#         temp_video.close()
        
#         print(f"[UPLOAD] Video saved to temp file: {temp_video.name}")

#         # Handle optional audio file
#         audio_path = None
#         if 'audio' in request.files:
#             audio_file = request.files['audio']
#             temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
#             audio_file.save(temp_audio.name)
#             temp_audio.close()
#             audio_path = temp_audio.name
#             print(f"[UPLOAD] Audio saved to temp file: {temp_audio.name}")

#         # Create output path for processed video
#         output_filename = f"processed_{uuid.uuid4()}.mp4"
#         output_path = os.path.join(PROCESSED_FOLDER, output_filename)

#         print("[UPLOAD] Starting processing with parameters:")
#         for key in request.form:
#             print(f"  {key}: {request.form[key]}")

#         # Process the video
#         processed_path = process_video_file(temp_video.name, output_path, request.form, audio_path)
        
#         # Return network-accessible URL
#         video_url = f"http://{request.host}/processed-videos/{output_filename}"
#         print(f"[UPLOAD] Returning video URL: {video_url}")

#         return jsonify({
#             "processed_video_uri": video_url,
#             "success": True,
#             "message": "Video processed successfully with emoji support"
#         })

#     except Exception as e:
#         print(f"[ERROR] Upload failed: {e}")
#         traceback.print_exc()
#         return jsonify({
#             "error": str(e),
#             "success": False,
#             "message": "Video processing failed"
#         }), 500

#     finally:
#         # Clean up temp video file
#         if temp_video is not None:
#             try:
#                 if os.path.exists(temp_video.name):
#                     os.unlink(temp_video.name)
#                     print(f"[CLEANUP] Deleted temp video file: {temp_video.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp video file: {e}")
        
#         # Clean up temp audio file
#         if temp_audio is not None:
#             try:
#                 if os.path.exists(temp_audio.name):
#                     os.unlink(temp_audio.name)
#                     print(f"[CLEANUP] Deleted temp audio file: {temp_audio.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp audio file: {e}")

# if __name__ == '__main__':
#     print("="*50)
#     print("[SERVER] Video Processing Server with Emoji Support")
#     print("[SERVER] Features:")
#     print("[SERVER] - Video trimming and audio overlay")
#     print("[SERVER] - Full-color emoji text rendering (Pilmoji)")
#     print("[SERVER] - HTTP video serving")
#     print("[SERVER] - Automatic temp file cleanup")
#     print("[SERVER] - Cross-platform compatibility")
#     print("="*50)
#     print("[SERVER] Flask server starting on port 5000...")
#     print("="*50)
    
#     app.run(host='0.0.0.0', port=5000, debug=True)
#--------------------------------------------------------------------------------------
# import os
# import uuid
# import traceback
# import tempfile
# import numpy as np
# from flask import Flask, request, jsonify, send_from_directory
# from flask_cors import CORS
# from werkzeug.utils import secure_filename
# from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
# import textwrap
# from PIL import Image, ImageDraw, ImageFont, ImageColor
# from pilmoji import Pilmoji

# #Filter
# import colorsys
# from scipy import ndimage

# #Subtitles
# import whisper
# import json
# from moviepy.video.tools.subtitles import SubtitlesClip
# WHISPER_MODEL = None


# app = Flask(__name__)
# CORS(app)

# PROCESSED_FOLDER = 'processed'
# os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# #Subtitles
# def load_whisper_model(model_size="base"):
#     """Load Whisper model once for reuse"""
#     global WHISPER_MODEL
#     if WHISPER_MODEL is None:
#         print(f"[WHISPER] Loading {model_size} model...")
#         WHISPER_MODEL = whisper.load_model(model_size)
#         print("[WHISPER] Model loaded successfully")
#     return WHISPER_MODEL

# def extract_audio_for_whisper(video_path):
#     """Extract audio from video for Whisper processing"""
#     try:
#         video = VideoFileClip(video_path)
#         audio_path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
#         video.audio.write_audiofile(audio_path, verbose=False, logger=None)
#         video.close()
#         print(f"[WHISPER] Audio extracted to: {audio_path}")
#         return audio_path
#     except Exception as e:
#         print(f"[WHISPER] Audio extraction failed: {e}")
#         raise e

# def generate_subtitles_with_whisper(video_path, language="auto", translate_to_english=False):
#     """
#     Generate auto-subtitles using Whisper
    
#     Args:
#         video_path: Path to video file
#         language: Language code ("auto", "en", "es", etc.) 
#         translate_to_english: Whether to translate foreign language to English
#     """
#     audio_path = None
#     try:
#         print("[WHISPER] Starting subtitle generation...")
        
#         # Load Whisper model
#         model = load_whisper_model("base")  # Options: tiny, base, small, medium, large
        
#         # Extract audio
#         audio_path = extract_audio_for_whisper(video_path)
        
#         # Transcribe with timestamps
#         task = 'translate' if translate_to_english else 'transcribe'
#         result = model.transcribe(
#             audio_path, 
#             task=task,
#             language=None if language == "auto" else language,
#             verbose=False
#         )
        
#         print(f"[WHISPER] Detected language: {result.get('language', 'unknown')}")
#         print(f"[WHISPER] Generated {len(result['segments'])} subtitle segments")
        
#         # Convert to MoviePy subtitle format
#         subtitles = []
#         for segment in result['segments']:
#             start_time = segment['start']
#             end_time = segment['end']
#             text = segment['text'].strip()
            
#             if text:  # Only add non-empty segments
#                 subtitles.append(((start_time, end_time), text))
        
#         return {
#             'subtitles': subtitles,
#             'language': result.get('language', 'unknown'),
#             'segments_count': len(subtitles)
#         }
        
#     except Exception as e:
#         print(f"[WHISPER] Subtitle generation failed: {e}")
#         raise e
#     finally:
#         # Cleanup extracted audio
#         if audio_path and os.path.exists(audio_path):
#             try:
#                 os.unlink(audio_path)
#                 print("[WHISPER] Cleaned up extracted audio file")
#             except Exception as cleanup_error:
#                 print(f"[WHISPER] Audio cleanup warning: {cleanup_error}")

# def create_subtitle_clip(subtitles, video_width, video_height, font_size=None, font_color='white', bg_color='black'):
#     """
#     Create MoviePy subtitle clip using your existing text rendering system
#     """
#     if not font_size:
#         # Use your existing aspect-ratio aware sizing
#         font_size = get_aspect_ratio_aware_font_size(48, video_width, video_height)
    
#     def make_textclip(txt):
#         """Generate individual subtitle text clip"""
#         # Use your existing text creation function
#         text_array = create_text_with_emoji_pilmoji_fixed_macos(
#             text=txt,
#             font_size=font_size,
#             color=font_color,
#             bg_color=bg_color,
#             size=(video_width, int(video_height * 0.2)),  # Subtitle area
#             text_position=None  # Center text
#         )
        
#         return ImageClip(text_array, transparent=True)
    
#     # Create subtitle clip
#     subtitle_clip = SubtitlesClip(subtitles, make_textclip)
    
#     # Position at bottom of video
#     return subtitle_clip.set_position(('center', video_height - int(video_height * 0.15)))

# def generate_subtitles_with_whisper(video_path, language="auto", translate_to_english=False):
#     """
#     Generate auto-subtitles using Whisper with text length limits
#     """
#     audio_path = None
#     try:
#         print("[WHISPER] Starting subtitle generation...")
        
#         # Load Whisper model
#         model = load_whisper_model("base")
        
#         # Extract audio
#         audio_path = extract_audio_for_whisper(video_path)
        
#         # Transcribe with timestamps
#         task = 'translate' if translate_to_english else 'transcribe'
#         result = model.transcribe(
#             audio_path, 
#             task=task,
#             language=None if language == "auto" else language,
#             verbose=False,
#             word_timestamps=True  # ✅ Enable word-level timestamps
#         )
        
#         print(f"[WHISPER] Detected language: {result.get('language', 'unknown')}")
        
#         # Convert to MoviePy subtitle format with length limits
#         subtitles = []
#         MAX_CHARS_PER_SUBTITLE = 50  # ✅ Character limit
#         MAX_WORDS_PER_SUBTITLE = 8   # ✅ Word limit
        
#         for segment in result['segments']:
#             start_time = segment['start']
#             end_time = segment['end']
#             text = segment['text'].strip()
            
#             if not text:
#                 continue
            
#             # ✅ Split long text into shorter segments
#             if len(text) > MAX_CHARS_PER_SUBTITLE or len(text.split()) > MAX_WORDS_PER_SUBTITLE:
#                 split_subtitles = split_long_subtitle(text, start_time, end_time, MAX_CHARS_PER_SUBTITLE, MAX_WORDS_PER_SUBTITLE)
#                 subtitles.extend(split_subtitles)
#                 print(f"[WHISPER] Split long text: '{text[:30]}...' into {len(split_subtitles)} parts")
#             else:
#                 subtitles.append(((start_time, end_time), text))
        
#         print(f"[WHISPER] Generated {len(subtitles)} subtitle segments (after splitting)")
        
#         return {
#             'subtitles': subtitles,
#             'language': result.get('language', 'unknown'),
#             'segments_count': len(subtitles)
#         }
        
#     except Exception as e:
#         print(f"[WHISPER] Subtitle generation failed: {e}")
#         raise e
#     finally:
#         # Cleanup extracted audio
#         if audio_path and os.path.exists(audio_path):
#             try:
#                 os.unlink(audio_path)
#                 print("[WHISPER] Cleaned up extracted audio file")
#             except Exception as cleanup_error:
#                 print(f"[WHISPER] Audio cleanup warning: {cleanup_error}")

# def generate_subtitles_with_whisper(video_path, language="auto", translate_to_english=False):
#     """
#     Generate auto-subtitles using Whisper with music-optimized settings
#     """
#     audio_path = None
#     try:
#         print("[WHISPER] Starting subtitle generation...")
        
#         # Load Whisper model - use 'small' or 'medium' for better music transcription
#         model = load_whisper_model("small")
        
#         # Extract audio
#         audio_path = extract_audio_for_whisper(video_path)
        
#         # ✅ Define task variable BEFORE using it
#         task = 'translate' if translate_to_english else 'transcribe'
        
#         # ✅ Enhanced transcription settings for music
#         result = model.transcribe(
#             audio_path, 
#             task=task,  # ✅ Now properly defined
#             language=None if language == "auto" else language,
#             verbose=False,
#             word_timestamps=True,
#             # ✅ Music-specific settings
#             temperature=0,  # More deterministic results
#             no_speech_threshold=0.3,  # Lower threshold to catch quiet vocals
#             logprob_threshold=-0.8,  # More lenient probability threshold
#             condition_on_previous_text=False,  # Prevent context bleeding
#             initial_prompt="This is a song with lyrics and music."  # Guide Whisper
#         )
        
#         print(f"[WHISPER] Detected language: {result.get('language', 'unknown')}")
        
#         # Convert to MoviePy subtitle format with length limits
#         subtitles = []
#         MAX_CHARS_PER_SUBTITLE = 50
#         MAX_WORDS_PER_SUBTITLE = 8
        
#         for segment in result['segments']:
#             start_time = segment['start']
#             end_time = segment['end']
#             text = segment['text'].strip()
            
#             if not text:
#                 continue
            
#             # Split long text into shorter segments
#             if len(text) > MAX_CHARS_PER_SUBTITLE or len(text.split()) > MAX_WORDS_PER_SUBTITLE:
#                 split_subtitles = split_long_subtitle(text, start_time, end_time, MAX_CHARS_PER_SUBTITLE, MAX_WORDS_PER_SUBTITLE)
#                 subtitles.extend(split_subtitles)
#                 print(f"[WHISPER] Split long text: '{text[:30]}...' into {len(split_subtitles)} parts")
#             else:
#                 subtitles.append(((start_time, end_time), text))
        
#         print(f"[WHISPER] Generated {len(subtitles)} subtitle segments (after splitting)")
        
#         return {
#             'subtitles': subtitles,
#             'language': result.get('language', 'unknown'),
#             'segments_count': len(subtitles)
#         }
        
#     except Exception as e:
#         print(f"[WHISPER] Subtitle generation failed: {e}")
#         raise e
#     finally:
#         # Cleanup extracted audio
#         if audio_path and os.path.exists(audio_path):
#             try:
#                 os.unlink(audio_path)
#                 print("[WHISPER] Cleaned up extracted audio file")
#             except Exception as cleanup_error:
#                 print(f"[WHISPER] Audio cleanup warning: {cleanup_error}")

# def generate_subtitles_with_whisper_trimmed(video_path, language="auto", translate_to_english=False, trim_start=0, trim_end=None):
#     """
#     Generate auto-subtitles for TRIMMED video portion with proper timing synchronization
#     """
#     temp_trimmed_video = None
#     audio_path = None
#     try:
#         print(f"[WHISPER] Starting subtitle generation for trimmed portion: {trim_start}s to {trim_end}s")
        
#         # ✅ STEP 1: Create trimmed video first
#         original_clip = VideoFileClip(video_path)
        
#         # ✅ FIX: Handle end_time properly - don't override with arbitrary value
#         if trim_end is None:
#             trim_end = original_clip.duration
        
#         # ✅ CRITICAL FIX: Use the actual trim_end value, don't recalculate
#         print(f"[WHISPER] Original video duration: {original_clip.duration}s")
#         print(f"[WHISPER] Using trim range: {trim_start}s to {trim_end}s")
#         print(f"[WHISPER] Expected trimmed duration: {trim_end - trim_start}s")
        
#         # Create trimmed clip with correct end time
#         trimmed_clip = original_clip.subclip(trim_start, trim_end)
        
#         # Save trimmed video to temp file
#         temp_trimmed_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         trimmed_clip.write_videofile(
#             temp_trimmed_video.name,
#             verbose=False,
#             logger=None,
#             audio_codec='aac'
#         )
#         temp_trimmed_video.close()
        
#         # Clean up clips
#         trimmed_clip.close()
#         original_clip.close()
        
#         print(f"[WHISPER] Created trimmed video: {temp_trimmed_video.name}")
#         print(f"[WHISPER] Trimmed duration: {trim_end - trim_start}s")
        
#         # ✅ STEP 2: Generate subtitles from trimmed video (timing will be 0-based)
#         model = load_whisper_model("small")
        
#         # Extract audio from trimmed video
#         audio_path = extract_audio_for_whisper(temp_trimmed_video.name)
        
#         # Define task
#         task = 'translate' if translate_to_english else 'transcribe'
        
#         # Transcribe trimmed audio (timing starts from 0)
#         result = model.transcribe(
#             audio_path, 
#             task=task,
#             language=None if language == "auto" else language,
#             verbose=False,
#             word_timestamps=True,
#             temperature=0,
#             no_speech_threshold=0.3,
#             logprob_threshold=-0.8,
#             condition_on_previous_text=False,
#             initial_prompt="This is a song with lyrics and music."
#         )
        
#         print(f"[WHISPER] Detected language: {result.get('language', 'unknown')}")
#         print(f"[WHISPER] Found {len(result['segments'])} raw segments")
        
#         # ✅ STEP 3: Process subtitles (already 0-based from trimmed video)
#         subtitles = []
#         MAX_CHARS_PER_SUBTITLE = 50
#         MAX_WORDS_PER_SUBTITLE = 8
        
#         for i, segment in enumerate(result['segments']):
#             start_time = segment['start']  # Already 0-based
#             end_time = segment['end']      # Already 0-based
#             text = segment['text'].strip()
            
#             print(f"[WHISPER] Segment {i}: {start_time:.2f}s-{end_time:.2f}s: '{text}'")
            
#             if not text:
#                 continue
            
#             # Split long text into shorter segments
#             if len(text) > MAX_CHARS_PER_SUBTITLE or len(text.split()) > MAX_WORDS_PER_SUBTITLE:
#                 split_subtitles = split_long_subtitle(text, start_time, end_time, MAX_CHARS_PER_SUBTITLE, MAX_WORDS_PER_SUBTITLE)
#                 subtitles.extend(split_subtitles)
#                 print(f"[WHISPER] Split long text: '{text[:30]}...' into {len(split_subtitles)} parts")
#             else:
#                 subtitles.append(((start_time, end_time), text))
        
#         print(f"[WHISPER] Generated {len(subtitles)} subtitle segments for trimmed video (0-based timing)")
        
#         return {
#             'subtitles': subtitles,
#             'language': result.get('language', 'unknown'),
#             'segments_count': len(subtitles),
#             'trim_start': trim_start,
#             'trim_end': trim_end,
#             'trimmed_duration': trim_end - trim_start
#         }
        
#     except Exception as e:
#         print(f"[WHISPER] Trimmed subtitle generation failed: {e}")
#         raise e
#     finally:
#         # Cleanup
#         if temp_trimmed_video and os.path.exists(temp_trimmed_video.name):
#             try:
#                 os.unlink(temp_trimmed_video.name)
#                 print("[WHISPER] Cleaned up trimmed video file")
#             except Exception as cleanup_error:
#                 print(f"[WHISPER] Trimmed video cleanup warning: {cleanup_error}")
                
#         if audio_path and os.path.exists(audio_path):
#             try:
#                 os.unlink(audio_path)
#                 print("[WHISPER] Cleaned up extracted audio file")
#             except Exception as cleanup_error:
#                 print(f"[WHISPER] Audio cleanup warning: {cleanup_error}")

# def fill_timeline_gaps(segments, audio_duration, gap_threshold=2.0):
#     """
#     Fill gaps in timeline where Whisper didn't detect speech
#     """
#     if not segments:
#         return segments
    
#     filled_segments = []
#     previous_end = 0
    
#     for segment in segments:
#         current_start = segment['start']
        
#         # If there's a significant gap, add a silence marker
#         if current_start - previous_end > gap_threshold:
#             gap_segment = {
#                 'start': previous_end,
#                 'end': current_start,
#                 'text': '[Music]'  # Optional: mark as music/silence
#             }
#             # Only add if you want to show music indicators
#             # filled_segments.append(gap_segment)
        
#         filled_segments.append(segment)
#         previous_end = segment['end']
    
#     # Handle gap at the end
#     if audio_duration - previous_end > gap_threshold:
#         final_segment = {
#             'start': previous_end,
#             'end': audio_duration,
#             'text': '[Music]'
#         }
#         # filled_segments.append(final_segment)
    
#     return filled_segments

# def get_audio_duration(audio_path):
#     """Get duration of audio file"""
#     try:
#         import librosa
#         y, sr = librosa.load(audio_path)
#         return len(y) / sr
#     except:
#         # Fallback using moviepy
#         from moviepy.editor import AudioFileClip
#         audio = AudioFileClip(audio_path)
#         duration = audio.duration
#         audio.close()
#         return duration


# def split_long_subtitle(text, start_time, end_time, max_chars, max_words):
#     """
#     Split long subtitle text into shorter segments with proper timing
#     """
#     words = text.split()
#     segments = []
#     current_segment = []
#     duration = end_time - start_time
    
#     for word in words:
#         # Check if adding this word exceeds limits
#         test_segment = current_segment + [word]
#         test_text = ' '.join(test_segment)
        
#         if len(test_text) > max_chars or len(test_segment) > max_words:
#             if current_segment:  # Save current segment
#                 segment_text = ' '.join(current_segment)
#                 segment_duration = duration * len(current_segment) / len(words)
#                 segment_start = start_time + duration * len(segments) * max_words / len(words)
#                 segment_end = min(segment_start + segment_duration, end_time)
                
#                 segments.append(((segment_start, segment_end), segment_text))
#                 current_segment = [word]  # Start new segment
#             else:
#                 # Single word is too long, truncate it
#                 truncated_word = word[:max_chars-3] + "..."
#                 segments.append(((start_time, end_time), truncated_word))
#                 current_segment = []
#         else:
#             current_segment.append(word)
    
#     # Add remaining words
#     if current_segment:
#         segment_text = ' '.join(current_segment)
#         segment_start = start_time + duration * len(segments) * max_words / len(words)
#         segments.append(((segment_start, end_time), segment_text))
    
#     return segments

# def extract_audio_for_whisper(video_path):
#     """Extract audio from video for Whisper processing with comprehensive validation"""
#     video = None
#     try:
#         print(f"[WHISPER] Starting audio extraction from: {video_path}")
        
#         # ✅ File existence and size validation
#         if not os.path.exists(video_path):
#             raise FileNotFoundError(f"Video file not found: {video_path}")
        
#         file_size = os.path.getsize(video_path)
#         if file_size == 0:
#             raise ValueError(f"Video file is empty: {video_path} (0 bytes)")
        
#         print(f"[WHISPER] Video file validated - Size: {file_size / (1024*1024):.2f} MB")
        
#         # ✅ Load video with enhanced error handling
#         try:
#             video = VideoFileClip(video_path)
#         except Exception as moviepy_error:
#             raise ValueError(f"MoviePy failed to load video: {moviepy_error}")
        
#         # ✅ Validate video object
#         if video is None:
#             raise ValueError("MoviePy returned None - video file may be corrupted or unsupported format")
        
#         # ✅ Check video properties
#         if not hasattr(video, 'duration') or video.duration <= 0:
#             raise ValueError(f"Invalid video duration: {getattr(video, 'duration', 'None')}")
        
#         # ✅ Verify audio track exists - ENHANCED ERROR MESSAGE
#         if video.audio is None:
#             video.close()
#             raise ValueError("Video file has no audio track - cannot generate subtitles. This video appears to be silent or recorded without audio.")
        
#         print(f"[WHISPER] Video validated - Duration: {video.duration:.2f}s, Size: {video.size}")
        
#         # ✅ Extract audio with proper temp file handling
#         audio_path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
#         print(f"[WHISPER] Extracting audio to: {audio_path}")
        
#         video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        
#         # ✅ Validate extracted audio file
#         if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
#             raise ValueError("Audio extraction failed - output file is empty")
        
#         print(f"[WHISPER] Audio extraction successful: {os.path.getsize(audio_path)} bytes")
        
#         # Clean up video object
#         video.close()
        
#         return audio_path
        
#     except Exception as e:
#         print(f"[WHISPER] Audio extraction failed: {e}")
#         # Ensure video object is cleaned up on error
#         if video is not None:
#             try:
#                 video.close()
#             except:
#                 pass
#         raise e

# def extract_audio_for_whisper(video_path):
#     """Extract and enhance audio from video for better Whisper performance"""
#     video = None
#     try:
#         print(f"[WHISPER] Starting audio extraction from: {video_path}")
        
#         # ✅ File existence and size validation
#         if not os.path.exists(video_path):
#             raise FileNotFoundError(f"Video file not found: {video_path}")
        
#         file_size = os.path.getsize(video_path)
#         if file_size == 0:
#             raise ValueError(f"Video file is empty: {video_path} (0 bytes)")
        
#         print(f"[WHISPER] Video file validated - Size: {file_size / (1024*1024):.2f} MB")
        
#         # ✅ Load video with enhanced error handling
#         try:
#             video = VideoFileClip(video_path)
#         except Exception as moviepy_error:
#             raise ValueError(f"MoviePy failed to load video: {moviepy_error}")
        
#         # ✅ Validate video object
#         if video is None:
#             raise ValueError("MoviePy returned None - video file may be corrupted or unsupported format")
        
#         # ✅ Check video properties
#         if not hasattr(video, 'duration') or video.duration <= 0:
#             raise ValueError(f"Invalid video duration: {getattr(video, 'duration', 'None')}")
        
#         # ✅ Verify audio track exists - ENHANCED ERROR MESSAGE
#         if video.audio is None:
#             video.close()
#             raise ValueError("Video file has no audio track - cannot generate subtitles. This video appears to be silent or recorded without audio.")
        
#         print(f"[WHISPER] Video validated - Duration: {video.duration:.2f}s, Size: {video.size}")
        
#         # ✅ Extract audio with enhanced settings
#         audio_path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
#         print(f"[WHISPER] Extracting audio to: {audio_path}")
        
#         # Enhanced audio extraction for better speech recognition
#         video.audio.write_audiofile(
#             audio_path, 
#             verbose=False, 
#             logger=None,
#             # ✅ Audio enhancement settings
#             codec='pcm_s16le',  # Uncompressed for better quality
#             # ffmpeg_params=['-ac', '1']  # Convert to mono for better recognition
#         )
        
#         # ✅ Optional: Apply audio filtering to enhance vocals
#         enhanced_audio_path = enhance_audio_for_speech(audio_path)
        
#         # Clean up original if enhanced version was created
#         if enhanced_audio_path != audio_path:
#             os.unlink(audio_path)
#             audio_path = enhanced_audio_path
        
#         # ✅ Validate extracted audio file
#         if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
#             raise ValueError("Audio extraction failed - output file is empty")
        
#         print(f"[WHISPER] Audio extraction successful: {os.path.getsize(audio_path)} bytes")
        
#         # Clean up video object
#         video.close()
        
#         return audio_path
        
#     except Exception as e:
#         print(f"[WHISPER] Audio extraction failed: {e}")
#         # Ensure video object is cleaned up on error
#         if video is not None:
#             try:
#                 video.close()
#             except:
#                 pass
#         raise e

# def enhance_audio_for_speech(audio_path):
#     """Enhance audio to improve speech recognition in music"""
#     try:
#         import subprocess
#         enhanced_path = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        
#         # Use FFmpeg to enhance vocals and reduce background music
#         subprocess.run([
#             'ffmpeg', '-i', audio_path,
#             '-af', 'highpass=f=200,lowpass=f=3000,volume=1.5',  # Filter for vocal range
#             '-ac', '1',  # Convert to mono
#             '-ar', '16000',  # Whisper's preferred sample rate
#             '-y',
#             enhanced_path
#         ], check=True, capture_output=True)
        
#         print("[WHISPER] Audio enhanced for better speech recognition")
#         return enhanced_path
        
#     except Exception as e:
#         print(f"[WHISPER] Audio enhancement failed: {e}, using original")
#         return audio_path



# def create_subtitle_clip(subtitles, video_width, video_height, font_size=None, font_color='white', bg_color='black'):
#     """
#     Create MoviePy subtitle clip using your existing text rendering system
#     """
#     print(f"[DEBUG] Creating subtitle clip with {len(subtitles)} segments")
#     for i, subtitle in enumerate(subtitles):
#         print(f"[DEBUG] Subtitle {i}: {subtitle[0]} -> '{subtitle[1]}'")
    
#     if not font_size:
#         # Use your existing aspect-ratio aware sizing
#         font_size = get_aspect_ratio_aware_font_size(48, video_width, video_height)
    
#     def make_textclip(txt):
#         """Generate individual subtitle text clip"""
#         print(f"[DEBUG] Creating text clip for: '{txt}'")
        
#         # Use your existing text creation function
#         text_array = create_text_with_emoji_pilmoji_fixed_macos(
#             text=txt,
#             font_size=font_size,
#             color=font_color,
#             bg_color=bg_color,
#             size=(video_width, int(video_height * 0.2)),  # Subtitle area
#             text_position=None  # Center text
#         )
        
#         return ImageClip(text_array, transparent=True)
    
#     # Create subtitle clip
#     subtitle_clip = SubtitlesClip(subtitles, make_textclip)
    
#     # Position at bottom of video
#     return subtitle_clip.set_position(('center', video_height - int(video_height * 0.15)))


# def get_aspect_ratio_aware_font_size(user_size, video_width, video_height, method='diagonal-based'):
#     """
#     Server-side font scaling to match frontend calculations
#     """
#     if not video_width or not video_height:
#         return user_size
    
#     if method == 'diagonal-based':
#         diagonal = (video_width ** 2 + video_height ** 2) ** 0.5
#         reference_diagonal = (1920 ** 2 + 1080 ** 2) ** 0.5
#         scale = diagonal / reference_diagonal
#         return round(user_size * scale)
    
#     elif method == 'height-based':
#         height_percentage = (user_size / 1080) * 100
#         return round((height_percentage / 100) * video_height)
    
#     elif method == 'adaptive':
#         aspect_ratio = video_width / video_height
#         if aspect_ratio > 1.5:
#             # Wide landscape
#             return round((user_size / 1080) * video_height)
#         elif aspect_ratio < 0.7:
#             # Tall portrait
#             return round((user_size / 1080) * video_width)
#         else:
#             # Square-ish - use diagonal
#             diagonal = (video_width ** 2 + video_height ** 2) ** 0.5
#             reference_diagonal = (1920 ** 2 + 1080 ** 2) ** 0.5
#             return round(user_size * (diagonal / reference_diagonal))
    
#     return user_size

# def get_aspect_ratio_aware_font_size(user_size, video_width, video_height, method='conservative-height'):
#     """
#     FIXED: More conservative font scaling to prevent text from becoming too small
#     """
#     if not video_width or video_height <= 0:
#         return user_size
    
#     if method == 'conservative-height':
#         # More conservative height-based scaling
#         min_height = 480  # Don't scale below this video height
#         effective_height = max(video_height, min_height)
#         baseline_height = 1080
#         height_scale = (effective_height / baseline_height) ** 0.5  # Gentler scaling
#         scaled_size = round(user_size * height_scale)
        
#         # Apply reasonable bounds
#         min_size = max(24, round(user_size * 0.5))  # Never go below 50% of original
#         max_size = round(user_size * 2)  # Never go above 200% of original
        
#         return max(min_size, min(max_size, scaled_size))
    
#     elif method == 'minimal':
#         # Minimal scaling - keeps text close to user's selection
#         if video_height < 600:
#             return max(user_size, 28)  # Ensure minimum readable size
#         else:
#             minimal_scale = (video_height / 1080) ** 0.3  # Very gentle scaling
#             return round(user_size * minimal_scale)
    
#     elif method == 'adaptive-smart':
#         # Smart scaling based on video characteristics
#         if video_height < 720:
#             # Small videos - minimal scaling
#             return max(round(user_size * 0.8), 24)
#         elif video_height > 1440:
#             # Large videos - allow more scaling
#             large_scale = min(video_height / 1080, 2.0)
#             return round(user_size * large_scale)
#         else:
#             # Medium videos - moderate scaling
#             medium_scale = (video_height / 1080) ** 0.5
#             return round(user_size * medium_scale)
    
#     return user_size

# def get_aspect_ratio_aware_font_size(user_size, video_width, video_height, method='proportional'):
#     """
#     FIXED: Dynamic font scaling that respects user input while providing aspect-ratio awareness
#     """
#     if not video_width or video_height <= 0:
#         return user_size
    
#     if method == 'proportional':
#         # NEW: Proportional scaling that maintains user control
#         aspect_ratio = video_width / video_height
        
#         # Base scaling factor on video size vs standard 1080p
#         size_factor = min(video_width, video_height) / 1080
        
#         # Aspect ratio adjustments (subtle, not overwhelming)
#         if aspect_ratio > 1.8:  # Ultra-wide
#             ar_factor = 0.9
#         elif aspect_ratio > 1.4:  # Wide (16:9)
#             ar_factor = 1.0  # No adjustment for most common case
#         elif aspect_ratio > 0.7:  # Standard/Square
#             ar_factor = 1.0
#         else:  # Portrait
#             ar_factor = 1.1
        
#         # Combine factors with user preference as PRIMARY driver
#         final_scale = (size_factor * ar_factor * 0.3) + 0.7  # 30% auto, 70% user choice
#         scaled_size = round(user_size * final_scale)
        
#         # Reasonable bounds to prevent extremes
#         min_size = max(16, round(user_size * 0.6))
#         max_size = round(user_size * 1.5)
        
#         return max(min_size, min(max_size, scaled_size))
    
#     return user_size


# def get_recommended_scaling_method(video_width, video_height):
#     """Get recommended scaling method based on video properties"""
#     if video_height < 720:
#         return 'minimal'  # Keep text readable on small videos
#     elif video_height > 1440:
#         return 'conservative-height'  # Allow scaling on large videos
#     else:
#         return 'adaptive-smart' 

# def get_recommended_scaling_method(video_width, video_height):
#     """Always use proportional for better user experience"""
#     return 'proportional'


# def load_font_with_size(font_size):
#     """Load font with fallback for different systems"""
#     font = None
#     font_paths = [
#         "Arial.ttf",
#         "/System/Library/Fonts/Arial.ttf",
#         "/System/Library/Fonts/Helvetica.ttc",
#         "/Library/Fonts/Arial.ttf",
#         "/System/Library/Fonts/Times.ttc",
#         "/System/Library/Fonts/Courier.ttc",
#         "C:/Windows/Fonts/arial.ttf",
#         "C:/Windows/Fonts/calibri.ttf",
#         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
#         "/usr/share/fonts/TTF/arial.ttf"
#     ]
    
#     for path in font_paths:
#         try:
#             font = ImageFont.truetype(path, font_size)
#             print(f"[FONT] Successfully loaded: {path}")
#             break
#         except Exception as e:
#             continue
    
#     if font is None:
#         font = ImageFont.load_default()
#         print("[FONT] Using default font")
    
#     return font

# def create_text_with_emoji_pilmoji_fixed_macos(text, font_size=48, color='white', bg_color='transparent', 
#                                                size=(800, 200), text_position=None):
#     """
#     FIXED VERSION: Create text image without forcing center alignment
    
#     Args:
#         text_position: (x, y) tuple for exact text placement within canvas, or None for center
#     """
#     # Create transparent canvas
#     img = Image.new('RGBA', size, (0, 0, 0, 0))
#     draw = ImageDraw.Draw(img)

#     # Load font
#     font = load_font_with_size(font_size)

#     # Measure text dimensions
#     bbox = draw.textbbox((0, 0), text, font=font)
#     text_w = bbox[2] - bbox[0]
#     text_h = bbox[3] - bbox[1]

#     # Use provided position or center if None
#     if text_position is not None:
#         x, y = text_position
#         print(f"[TEXT] Positioning text at exact coordinates: ({x}, {y})")
#     else:
#         x = (size[0] - text_w) // 2
#         y = (size[1] - text_h) // 2
#         print(f"[TEXT] Centering text at: ({x}, {y})")

#     # Draw background if needed
#     if bg_color != 'transparent':
#         box_rgb = ImageColor.getrgb(bg_color)
#         pad_x = 8
#         pad_y = 4
#         tb = draw.textbbox((0, 0), text, font=font)
#         box_coords = [
#             x + tb[0] - pad_x,
#             y + tb[1] - pad_y,
#             x + tb[2] + pad_x,
#             y + tb[3] + pad_y
#         ]
#         draw.rounded_rectangle(box_coords, radius=4, fill=box_rgb + (255,))

#     # Render text with Pilmoji at exact position
#     text_rgb = ImageColor.getrgb(color)
#     with Pilmoji(img) as pilmoji:
#         pilmoji.text((x, y), text, fill=text_rgb, font=font)

#     print(f"[TEXT] Text rendered: '{text}' at ({x}, {y}) with font size {font_size}")
#     return np.array(img)

# def create_text_with_emoji_pilmoji_fixed_macos(text, font_size=48, color='white', bg_color='transparent', 
#                                                size=(800, 200), text_position=None):
#     """
#     FIXED VERSION: Create text image with overflow prevention
#     """
#     # ✅ Truncate extremely long text
#     MAX_DISPLAY_LENGTH = 60
#     if len(text) > MAX_DISPLAY_LENGTH:
#         text = text[:MAX_DISPLAY_LENGTH-3] + "..."
#         print(f"[TEXT] Truncated long text to: '{text}'")
    
#     # Create transparent canvas
#     img = Image.new('RGBA', size, (0, 0, 0, 0))
#     draw = ImageDraw.Draw(img)

#     # Load font
#     font = load_font_with_size(font_size)

#     # Measure text dimensions
#     bbox = draw.textbbox((0, 0), text, font=font)
#     text_w = bbox[2] - bbox[0]
#     text_h = bbox[3] - bbox[1]

#     # ✅ Handle text wider than canvas
#     if text_w > size[0]:
#         print(f"[TEXT] Text too wide ({text_w}px > {size[0]}px), adjusting font size")
#         # Reduce font size to fit
#         adjusted_font_size = int(font_size * size[0] / text_w * 0.9)  # 90% of calculated size for margin
#         font = load_font_with_size(max(12, adjusted_font_size))  # Minimum 12px
#         bbox = draw.textbbox((0, 0), text, font=font)
#         text_w = bbox[2] - bbox[0]
#         text_h = bbox[3] - bbox[1]
#         print(f"[TEXT] Adjusted font size to {adjusted_font_size}px")

#     # Use provided position or center if None
#     if text_position is not None:
#         x, y = text_position
#         print(f"[TEXT] Positioning text at exact coordinates: ({x}, {y})")
#     else:
#         x = (size[0] - text_w) // 2
#         y = (size[1] - text_h) // 2
#         print(f"[TEXT] Centering text at: ({x}, {y})")

#     # ✅ Ensure text stays within bounds
#     x = max(0, min(x, size[0] - text_w))
#     y = max(0, min(y, size[1] - text_h))

#     # Draw background if needed
#     if bg_color != 'transparent':
#         box_rgb = ImageColor.getrgb(bg_color)
#         pad_x = 8
#         pad_y = 4
#         tb = draw.textbbox((0, 0), text, font=font)
#         box_coords = [
#             x + tb[0] - pad_x,
#             y + tb[1] - pad_y,
#             x + tb[2] + pad_x,
#             y + tb[3] + pad_y
#         ]
#         draw.rounded_rectangle(box_coords, radius=4, fill=box_rgb + (255,))

#     # Render text with Pilmoji at exact position
#     text_rgb = ImageColor.getrgb(color)
#     with Pilmoji(img) as pilmoji:
#         pilmoji.text((x, y), text, fill=text_rgb, font=font)

#     print(f"[TEXT] Text rendered: '{text}' at ({x}, {y}) with font size {font_size}")
#     return np.array(img)


# #Filter
# def apply_video_filter(clip, filter_name):
#     """Apply Instagram-style filters to video clips"""
    
#     if filter_name == 'none' or not filter_name:
#         return clip
    
#     print(f"[FILTER] Applying '{filter_name}' filter to video")
    
#     # Define filter functions with writable frame copies
#     def warm_filter(get_frame, t):
#         frame = get_frame(t).copy()  # Make writable copy
#         # Increase red/yellow tones, reduce blue
#         frame[:,:,0] = np.clip(frame[:,:,0] * 1.15, 0, 255)  # Red boost
#         frame[:,:,1] = np.clip(frame[:,:,1] * 1.05, 0, 255)  # Green slight boost  
#         frame[:,:,2] = np.clip(frame[:,:,2] * 0.9, 0, 255)   # Blue reduction
#         return frame.astype('uint8')
    
#     def cool_filter(get_frame, t):
#         frame = get_frame(t).copy()  # Make writable copy
#         # Increase blue tones, reduce red/yellow
#         frame[:,:,0] = np.clip(frame[:,:,0] * 0.85, 0, 255)  # Red reduction
#         frame[:,:,1] = np.clip(frame[:,:,1] * 0.95, 0, 255)  # Green slight reduction
#         frame[:,:,2] = np.clip(frame[:,:,2] * 1.2, 0, 255)   # Blue boost
#         return frame.astype('uint8')
    
#     def vintage_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)  # Make writable copy and convert to float
#         # Create vintage film look
#         frame[:,:,0] *= 1.1  # Slight red boost
#         frame[:,:,1] *= 0.95 # Slight green reduction
#         frame[:,:,2] *= 0.8  # Blue reduction
#         # Add slight vignette effect
#         h, w = frame.shape[:2]
#         Y, X = np.ogrid[:h, :w]
#         center_x, center_y = w/2, h/2
#         dist = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
#         vignette = 1 - (dist / np.max(dist)) * 0.3
#         frame *= vignette[:,:,np.newaxis]
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     def cinematic_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)  # Make writable copy
#         # Movie-like color grading
#         # Enhance contrast
#         frame = ((frame / 255.0 - 0.5) * 1.2 + 0.5) * 255
#         # Slight blue tint in shadows, orange in highlights
#         frame[:,:,0] = np.clip(frame[:,:,0] * 1.05, 0, 255)  # Red
#         frame[:,:,2] = np.clip(frame[:,:,2] * 1.02, 0, 255)  # Blue
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     def vivid_filter(get_frame, t):
#         frame = get_frame(t).copy()  # Make writable copy
#         # Boost saturation
#         hsv = np.array([colorsys.rgb_to_hsv(r/255, g/255, b/255) 
#                        for r, g, b in frame.reshape(-1, 3)])
#         hsv[:, 1] = np.clip(hsv[:, 1] * 1.4, 0, 1)  # Boost saturation
#         rgb = np.array([colorsys.hsv_to_rgb(h, s, v) for h, s, v in hsv])
#         return (rgb.reshape(frame.shape) * 255).astype('uint8')
    
#     def sepia_filter(get_frame, t):
#         frame = get_frame(t).copy()  # Make writable copy
#         # Classic sepia tone
#         sepia_frame = np.zeros_like(frame)
#         sepia_frame[:,:,0] = np.clip(0.393*frame[:,:,0] + 0.769*frame[:,:,1] + 0.189*frame[:,:,2], 0, 255)
#         sepia_frame[:,:,1] = np.clip(0.349*frame[:,:,0] + 0.686*frame[:,:,1] + 0.168*frame[:,:,2], 0, 255)
#         sepia_frame[:,:,2] = np.clip(0.272*frame[:,:,0] + 0.534*frame[:,:,1] + 0.131*frame[:,:,2], 0, 255)
#         return sepia_frame.astype('uint8')
    
#     def black_white_filter(get_frame, t):
#         frame = get_frame(t).copy()  # Make writable copy
#         # High contrast B&W
#         gray = np.dot(frame[...,:3], [0.2989, 0.5870, 0.1140])
#         return np.stack([gray, gray, gray], axis=-1).astype('uint8')
    
#     def sunset_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)  # Make writable copy
#         # Strong orange/red tones
#         frame[:,:,0] *= 1.3  # Red boost
#         frame[:,:,1] *= 1.1  # Green boost
#         frame[:,:,2] *= 0.7  # Blue reduction
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     def arctic_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)  # Make writable copy
#         # Cold blue tones
#         frame[:,:,0] *= 0.7  # Red reduction
#         frame[:,:,1] *= 0.9  # Green reduction
#         frame[:,:,2] *= 1.4  # Blue boost
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     def neon_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)  # Make writable copy
#         # Cyberpunk neon effect
#         # Enhance contrast dramatically
#         frame = ((frame / 255.0 - 0.5) * 1.8 + 0.5) * 255
#         # Add magenta/cyan tones
#         frame[:,:,0] = np.clip(frame[:,:,0] * 1.2, 0, 255)  # Red
#         frame[:,:,2] = np.clip(frame[:,:,2] * 1.2, 0, 255)  # Blue
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     # Add missing filter implementations
#     def fade_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)
#         # Faded film effect - reduce contrast and saturation
#         # Reduce contrast
#         frame = ((frame / 255.0 - 0.5) * 0.7 + 0.5) * 255
#         # Reduce saturation
#         hsv = np.array([colorsys.rgb_to_hsv(r/255, g/255, b/255) 
#                        for r, g, b in frame.reshape(-1, 3)])
#         hsv[:, 1] = np.clip(hsv[:, 1] * 0.6, 0, 1)  # Reduce saturation
#         rgb = np.array([colorsys.hsv_to_rgb(h, s, v) for h, s, v in hsv])
#         return (rgb.reshape(frame.shape) * 255).astype('uint8')
    
#     def instagram_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)
#         # Instagram-like filter: warm tones + slight vignette
#         frame[:,:,0] *= 1.1  # Red boost
#         frame[:,:,1] *= 1.05 # Green slight boost
#         frame[:,:,2] *= 0.95 # Blue slight reduction
        
#         # Add subtle vignette
#         h, w = frame.shape[:2]
#         Y, X = np.ogrid[:h, :w]
#         center_x, center_y = w/2, h/2
#         dist = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
#         vignette = 1 - (dist / np.max(dist)) * 0.2
#         frame *= vignette[:,:,np.newaxis]
        
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     def forest_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)
#         # Enhanced green tones for forest feel
#         frame[:,:,0] *= 0.8  # Red reduction
#         frame[:,:,1] *= 1.3  # Green boost
#         frame[:,:,2] *= 0.9  # Blue slight reduction
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     def desert_filter(get_frame, t):
#         frame = get_frame(t).copy().astype(float)
#         # Sandy warm colors
#         frame[:,:,0] *= 1.2  # Red boost
#         frame[:,:,1] *= 1.15 # Green boost (for sandy yellow)
#         frame[:,:,2] *= 0.8  # Blue reduction
#         return np.clip(frame, 0, 255).astype('uint8')
    
#     # Updated filter mapping with all filters
#     filter_functions = {
#         'warm': warm_filter,
#         'cool': cool_filter,
#         'vintage': vintage_filter,
#         'cinematic': cinematic_filter,
#         'vivid': vivid_filter,
#         'fade': fade_filter,
#         'black_white': black_white_filter,
#         'sepia': sepia_filter,
#         'instagram': instagram_filter,
#         'sunset': sunset_filter,
#         'arctic': arctic_filter,
#         'forest': forest_filter,
#         'desert': desert_filter,
#         'neon': neon_filter,
#     }
    
#     try:
#         if filter_name in filter_functions:
#             filtered_clip = clip.fl(filter_functions[filter_name])
#             print(f"[FILTER] Successfully applied '{filter_name}' filter")
#             return filtered_clip
#         else:
#             print(f"[FILTER] Unknown filter '{filter_name}', returning original")
#             return clip
#     except Exception as e:
#         print(f"[FILTER] Error applying filter '{filter_name}': {e}")
#         print("[FILTER] Returning original clip")
#         return clip


# def process_video_file(input_path, output_path, params, audio_path=None):
#     clip = None
#     audio_clip = None
#     audio_subclip = None
#     text_img_clip = None
#     video = None
    
#     try:
#         print(f"[PROCESSING] Loading video: {input_path}")
#         clip = VideoFileClip(input_path)
        
#         # Get trim parameters
#         start_time = float(params.get('start_time', 0))
#         end_time = params.get('end_time')
#         end_time = float(end_time) if end_time else clip.duration

#         # FIX: Clamp end_time to actual video duration
#         end_time = min(end_time, clip.duration)
#         start_time = min(start_time, clip.duration)

#         if start_time >= end_time:  # Defensive check
#             end_time = min(start_time + 1, clip.duration)
        
#         print(f"[PROCESSING] Original video duration: {clip.duration}s")
#         print(f"[PROCESSING] Requested trim: {params.get('start_time', 0)}s to {params.get('end_time')}s")
#         print(f"[PROCESSING] Actual trim (clamped): {start_time}s to {end_time}s")
#         clip = clip.subclip(start_time, end_time)
#         video_w, video_h = clip.size
#         trim_duration = end_time - start_time

#         # Apply filter BEFORE text overlay
#         filter_name = params.get('filter', 'none')
#         if filter_name and filter_name != 'none':
#             print(f"[PROCESSING] Applying filter: {filter_name}")
#             clip = apply_video_filter(clip, filter_name)

#         # Handle audio replacement if audio file is provided
#         if audio_path and os.path.exists(audio_path):
#             print(f"[PROCESSING] Adding audio from: {audio_path}")
#             audio_start_time = float(params.get('audio_start_time', 0))
#             audio_clip = AudioFileClip(audio_path)
#             print(f"[PROCESSING] Audio start time: {audio_start_time}s")
#             print(f"[PROCESSING] Trim duration: {trim_duration}s")
            
#             if audio_start_time < audio_clip.duration:
#                 available_audio_duration = min(trim_duration, audio_clip.duration - audio_start_time)
#                 audio_subclip = audio_clip.subclip(audio_start_time, audio_start_time + available_audio_duration)
                
#                 if available_audio_duration < trim_duration:
#                     print(f"[PROCESSING] Audio shorter than video. Available: {available_audio_duration}s, needed: {trim_duration}s")
                
#                 print(f"[PROCESSING] Using audio from {audio_start_time}s to {audio_start_time + available_audio_duration}s")
#                 clip = clip.set_audio(audio_subclip)
#             else:
#                 print(f"[PROCESSING] Audio start time ({audio_start_time}s) exceeds audio duration ({audio_clip.duration}s)")
#                 clip = clip.set_audio(None)

#         # Handle text overlay with ASPECT-RATIO AWARE sizing
#         # if params.get('text'):
#         #     print("[PROCESSING] Adding text overlay with ASPECT-RATIO AWARE sizing...")
            
#         #     text = params.get('text', 'Sample Text')
#         #     user_font_size = int(float(params.get('font_size', 48)))
#         #     font_color = params.get('font_color', 'white')
#         #     bg_color = params.get('background_color', 'transparent')
            
#         #     aspect_ratio = video_w / video_h
            
#         #     # Apply consistent font scaling
#         #     final_font_size = get_aspect_ratio_aware_font_size(
#         #         user_font_size, video_w, video_h, 'diagonal-based'
#         #     )
            
#         #     # Get position parameters
#         #     center_x = int(float(params.get('pos_x', video_w // 2)))
#         #     center_y = int(float(params.get('pos_y', video_h // 2)))
            
#         #     print(f"[PROCESSING] Video: {video_w}x{video_h} (AR: {aspect_ratio:.2f})")
#         #     print(f"[PROCESSING] Font scaling: {user_font_size}px → {final_font_size}px")
#         #     print(f"[PROCESSING] Text position: ({center_x}, {center_y})")
#         #here
#         if params.get('text'):
#             print("[PROCESSING] Adding text overlay with IMPROVED aspect-ratio sizing...")
            
#             text = params.get('text', 'Sample Text')
#             user_font_size = int(float(params.get('font_size', 48)))
#             font_color = params.get('font_color', 'white')
#             bg_color = params.get('background_color', 'transparent')
            
#             video_w, video_h = clip.size
#             aspect_ratio = video_w / video_h
            
#             # Use recommended scaling method
#             recommended_method = get_recommended_scaling_method(video_w, video_h)
#             final_font_size = get_aspect_ratio_aware_font_size(
#                 user_font_size, video_w, video_h, recommended_method
#             )
            
#             # Get position parameters
#             center_x = int(float(params.get('pos_x', video_w // 2)))
#             center_y = int(float(params.get('pos_y', video_h // 2))) - 11
            
#             print(f"[PROCESSING] Video: {video_w}x{video_h} (AR: {aspect_ratio:.2f})")
#             print(f"[PROCESSING] Recommended method: {recommended_method}")
#             print(f"[PROCESSING] Font scaling: {user_font_size}px → {final_font_size}px")
#             print(f"[PROCESSING] Text position: ({center_x}, {center_y})")
#             # Pre-calculate text dimensions
#             temp_img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
#             temp_draw = ImageDraw.Draw(temp_img)
            
#             # Load font for measurement
#             font = load_font_with_size(final_font_size)
            
#             # Measure text
#             bbox = temp_draw.textbbox((0, 0), text, font=font)
#             text_w = bbox[2] - bbox[0]
#             text_h = bbox[3] - bbox[1]
            
#             # Calculate position
#             text_pos_x = center_x - text_w // 2
#             text_pos_y = center_y - text_h // 2
            
#             # Clamp to video bounds
#             text_pos_x = max(0, min(text_pos_x, video_w - text_w))
#             text_pos_y = max(0, min(text_pos_y, video_h - text_h))
            
#             print(f"[PROCESSING] Final text positioning: ({text_pos_x}, {text_pos_y})")
#             print(f"[PROCESSING] Text dimensions: {text_w}x{text_h}")
            
#             # Create video-sized canvas with text at exact position
#             text_array = create_text_with_emoji_pilmoji_fixed_macos(
#                 text, final_font_size, font_color, bg_color,
#                 (video_w, video_h), (text_pos_x, text_pos_y)
#             )
            
#             # Create and composite the text overlay
#             text_img_clip = ImageClip(text_array, duration=clip.duration, transparent=True)
#             text_img_clip = text_img_clip.set_position((0, 0))
#             text_img_clip = text_img_clip.set_opacity(float(params.get('opacity', 1.0)))
            
#             video = CompositeVideoClip([clip, text_img_clip])
#         else:
#             video = clip


#         # Handle subtitle overlay
#         # if params.get('enable_subtitles') == 'true':
#             # print("[PROCESSING] Adding auto-generated subtitles...")
            
#             # subtitle_font_size = int(float(params.get('subtitle_font_size', 32)))
#             # subtitle_color = params.get('subtitle_color', 'white')
#             # subtitle_bg_color = params.get('subtitle_bg_color', 'black')
            
#             # # FIX: Pass language parameters correctly
#             # subtitle_language = params.get('subtitle_language', 'auto')
#             # translate_to_english = params.get('translate_to_english', 'false').lower() == 'true'
            
#             # # Generate subtitles with correct parameters
#             # subtitle_result = generate_subtitles_with_whisper(
#             #     input_path,
#             #     language=subtitle_language,           # ✅ Pass language
#             #     translate_to_english=translate_to_english  # ✅ Pass translation setting
#             # )
            
#             # print(f"[DEBUG] Generated subtitles: {subtitle_result}")  # Debug output
            
#             # # Create subtitle clip
#             # subtitle_clip = create_subtitle_clip(
#             #     subtitle_result['subtitles'],
#             #     video_w, video_h,
#             #     font_size=subtitle_font_size,
#             #     font_color=subtitle_color,
#             #     bg_color=subtitle_bg_color
#             # )
            
#             # # Composite with existing video
#             # if isinstance(video, CompositeVideoClip):
#             #     # If video already has text overlay
#             #     video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
#             # else:
#             #     # If video has no overlays yet
#             #     video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
            
#             # print(f"[PROCESSING] Added {len(subtitle_result['subtitles'])} subtitle segments")

#         # Handle subtitle overlay - FIXED VERSION
#         if params.get('enable_subtitles') == 'true':
#             print("[PROCESSING] Adding auto-generated subtitles...")
            
#             subtitle_font_size = int(float(params.get('subtitle_font_size', 32)))
#             subtitle_color = params.get('subtitle_color', 'white')
#             subtitle_bg_color = params.get('subtitle_bg_color', 'black')
            
#             # ✅ FIX: Use the SAME trim parameters that were used for video trimming
#             # These are the ALREADY CALCULATED values from earlier in the function
#             print(f"[PROCESSING] Using trim parameters for subtitles: {start_time}s to {end_time}s")
#             print(f"[PROCESSING] Subtitle generation duration: {end_time - start_time}s")
            
#             # FIX: Pass language parameters correctly
#             subtitle_language = params.get('subtitle_language', 'auto')
#             translate_to_english = params.get('translate_to_english', 'false').lower() == 'true'
            
#             # ✅ Generate subtitles with CORRECT trim parameters
#             subtitle_result = generate_subtitles_with_whisper_trimmed(
#                 input_path,
#                 language=subtitle_language,
#                 translate_to_english=translate_to_english,
#                 trim_start=start_time,  # ✅ Use already calculated start_time
#                 trim_end=end_time       # ✅ Use already calculated end_time
#             )
            
#             print(f"[DEBUG] Generated trimmed subtitles: {subtitle_result}")
            
#             # Create subtitle clip (timing is now 0-based for trimmed video)
#             subtitle_clip = create_subtitle_clip(
#                 subtitle_result['subtitles'],
#                 video_w, video_h,
#                 font_size=subtitle_font_size,
#                 font_color=subtitle_color,
#                 bg_color=subtitle_bg_color
#             )
            
#             # Composite with existing video
#             if isinstance(video, CompositeVideoClip):
#                 video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
#             else:
#                 video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
            
#             print(f"[PROCESSING] Added {len(subtitle_result['subtitles'])} subtitle segments for trimmed video")
 
#         # Handle subtitle overlay
#         # if params.get('enable_subtitles') == 'true':
#         #     print("[PROCESSING] Adding auto-generated subtitles...")
            
#         #     subtitle_font_size = int(float(params.get('subtitle_font_size', 32)))
#         #     subtitle_color = params.get('subtitle_color', 'white')
#         #     subtitle_bg_color = params.get('subtitle_bg_color', 'black')
            
#         #     # FIX: Pass language parameters correctly
#         #     subtitle_language = params.get('subtitle_language', 'auto')
#         #     translate_to_english = params.get('translate_to_english', 'false').lower() == 'true'
            
#         #     # ✅ Check if video has audio before attempting subtitle generation
#         #     try:
#         #         # Quick audio check
#         #         temp_clip = VideoFileClip(input_path)
#         #         has_audio = temp_clip.audio is not None
#         #         temp_clip.close()
                
#         #         if not has_audio:
#         #             print("[PROCESSING] Video has no audio track - skipping subtitle generation")
#         #             print("[PROCESSING] Continuing with video processing without subtitles")
#         #         else:
#         #             # Generate subtitles with correct parameters
#         #             subtitle_result = generate_subtitles_with_whisper(
#         #                 input_path,
#         #                 language=subtitle_language,
#         #                 translate_to_english=translate_to_english
#         #             )
                    
#         #             print(f"[DEBUG] Generated subtitles: {subtitle_result}")
                    
#         #             # Create subtitle clip
#         #             subtitle_clip = create_subtitle_clip(
#         #                 subtitle_result['subtitles'],
#         #                 video_w, video_h,
#         #                 font_size=subtitle_font_size,
#         #                 font_color=subtitle_color,
#         #                 bg_color=subtitle_bg_color
#         #             )
                    
#         #             # Composite with existing video
#         #             if isinstance(video, CompositeVideoClip):
#         #                 video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
#         #             else:
#         #                 video = CompositeVideoClip([video, subtitle_clip.set_duration(video.duration)])
                    
#         #             print(f"[PROCESSING] Added {len(subtitle_result['subtitles'])} subtitle segments")
                    
#         #     except Exception as subtitle_error:
#         #         print(f"[PROCESSING] Subtitle generation failed: {subtitle_error}")
#         #         print("[PROCESSING] Continuing with video processing without subtitles")
#         #         # Don't raise the error - continue processing without subtitles



#         # Preserve original audio if no replacement audio
#         if not video.audio and clip.audio:
#             video = video.set_audio(clip.audio)

#         print(f"[PROCESSING] Writing output to: {output_path}")
#         video.write_videofile(
#             output_path, 
#             codec="libx264", 
#             audio_codec="aac",
#             temp_audiofile="temp-audio.m4a",
#             remove_temp=True,
#             verbose=False,
#             logger=None
#         )
        
#         print("[SUCCESS] Processing complete.")
#         return output_path
        
#     except Exception as e:
#         print(f"[ERROR] Processing failed: {e}")
#         traceback.print_exc()
#         raise e
        
#     finally:
#         # Clean up clips in the correct order
#         try:
#             if video and video != clip:
#                 video.close()
#             if text_img_clip:
#                 text_img_clip.close()
#             if audio_subclip:
#                 audio_subclip.close()
#             if audio_clip:
#                 audio_clip.close()
#             if clip:
#                 clip.close()
#         except Exception as cleanup_error:
#             print(f"[WARNING] Cleanup error: {cleanup_error}")

# # Route to serve processed video files
# @app.route('/processed-videos/<filename>')
# def serve_processed_video(filename):
#     """Serve processed video files to clients"""
#     try:
#         print(f"[SERVE] Serving video file: {filename}")
#         return send_from_directory(
#             PROCESSED_FOLDER,
#             filename,
#             as_attachment=False,
#             mimetype='video/mp4'
#         )
#     except FileNotFoundError:
#         print(f"[ERROR] Video file not found: {filename}")
#         return jsonify({"error": "Video file not found"}), 404
#     except Exception as e:
#         print(f"[ERROR] Failed to serve video: {e}")
#         return jsonify({"error": "Failed to serve video"}), 500

# @app.route('/process-video', methods=['POST'])
# def handle_video_upload():
#     temp_video = None
#     temp_audio = None
    
#     try:
#         if 'video' not in request.files:
#             print("[ERROR] No video part in request.")
#             return jsonify({"error": "No video file uploaded"}), 400

#         # Create temp video file
#         video_file = request.files['video']
#         temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         video_file.save(temp_video.name)
#         temp_video.close()
        
#         print(f"[UPLOAD] Video saved to temp file: {temp_video.name}")

#         # Handle optional audio file
#         audio_path = None
#         if 'audio' in request.files:
#             audio_file = request.files['audio']
#             temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
#             audio_file.save(temp_audio.name)
#             temp_audio.close()
#             audio_path = temp_audio.name
#             print(f"[UPLOAD] Audio saved to temp file: {temp_audio.name}")

#         # Create output path for processed video
#         output_filename = f"processed_{uuid.uuid4()}.mp4"
#         output_path = os.path.join(PROCESSED_FOLDER, output_filename)

#         print("[UPLOAD] Starting processing with parameters:")
#         for key in request.form:
#             print(f"  {key}: {request.form[key]}")

#         # Process the video
#         processed_path = process_video_file(temp_video.name, output_path, request.form, audio_path)
        
#         # Return network-accessible URL
#         video_url = f"http://{request.host}/processed-videos/{output_filename}"
#         print(f"[UPLOAD] Returning video URL: {video_url}")

#         return jsonify({
#             "processed_video_uri": video_url,
#             "success": True,
#             "message": "Video processed successfully with emoji support"
#         })

#     except Exception as e:
#         print(f"[ERROR] Upload failed: {e}")
#         traceback.print_exc()
#         return jsonify({
#             "error": str(e),
#             "success": False,
#             "message": "Video processing failed"
#         }), 500

#     finally:
#         # Clean up temp video file
#         if temp_video is not None:
#             try:
#                 if os.path.exists(temp_video.name):
#                     os.unlink(temp_video.name)
#                     print(f"[CLEANUP] Deleted temp video file: {temp_video.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp video file: {e}")
        
#         # Clean up temp audio file
#         if temp_audio is not None:
#             try:
#                 if os.path.exists(temp_audio.name):
#                     os.unlink(temp_audio.name)
#                     print(f"[CLEANUP] Deleted temp audio file: {temp_audio.name}")
#             except Exception as e:
#                 print(f"[CLEANUP] Failed to delete temp audio file: {e}")

#Subtitles
# @app.route('/generate-subtitles', methods=['POST'])
# def generate_subtitles():
#     """Generate auto-subtitles for uploaded video"""
#     temp_video = None
    
#     try:
#         if 'video' not in request.files:
#             return jsonify({"error": "No video file provided"}), 400
        
#         # Save uploaded video to temp file
#         video_file = request.files['video']
#         temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         video_file.save(temp_video.name)
#         temp_video.close()
        
#         # Get parameters
#         language = request.form.get('language', 'auto')
#         translate_to_english = request.form.get('translate_to_english', 'false').lower() == 'true'
        
#         print(f"[SUBTITLES] Generating subtitles for video with language: {language}")
        
#         # Generate subtitles
#         result = generate_subtitles_with_whisper(
#             temp_video.name, 
#             language=language,
#             translate_to_english=translate_to_english
#         )
        
#         return jsonify({
#             "success": True,
#             "subtitles": [
#                 {
#                     "start": sub[0][0],
#                     "end": sub[0][1], 
#                     "text": sub[1]
#                 } for sub in result['subtitles']
#             ],
#             "detected_language": result['language'],
#             "segments_count": result['segments_count'],
#             "message": f"Generated {result['segments_count']} subtitle segments"
#         })
        
#     except Exception as e:
#         print(f"[ERROR] Subtitle generation failed: {e}")
#         return jsonify({
#             "error": str(e),
#             "success": False,
#             "message": "Subtitle generation failed"
#         }), 500
    
#     finally:
#         # Cleanup
#         if temp_video and os.path.exists(temp_video.name):
#             try:
#                 os.unlink(temp_video.name)
#                 print("[CLEANUP] Deleted temp video file")
#             except Exception as e:
#                 print(f"[CLEANUP] Temp file cleanup failed: {e}")

# @app.route('/generate-subtitles', methods=['POST'])
# def generate_subtitles():
#     """Generate auto-subtitles for uploaded video with trim support"""
#     temp_video = None
    
#     try:
#         if 'video' not in request.files:
#             return jsonify({"error": "No video file provided"}), 400
        
#         # Save uploaded video to temp file
#         video_file = request.files['video']
#         temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
#         video_file.save(temp_video.name)
#         temp_video.close()
        
#         # Get parameters
#         language = request.form.get('language', 'auto')
#         translate_to_english = request.form.get('translate_to_english', 'false').lower() == 'true'
        
#         # ✅ Get trim parameters
#         trim_start = float(request.form.get('trim_start', 0))
#         trim_end = request.form.get('trim_end')
#         trim_end = float(trim_end) if trim_end else None
        
#         print(f"[SUBTITLES] Generating subtitles for trimmed video: {trim_start}s to {trim_end}s")
#         print(f"[SUBTITLES] Language: {language}, Translate: {translate_to_english}")
        
#         # ✅ Use trimmed subtitle generation
#         result = generate_subtitles_with_whisper_trimmed(
#             temp_video.name, 
#             language=language,
#             translate_to_english=translate_to_english,
#             trim_start=trim_start,
#             trim_end=trim_end
#         )
        
#         return jsonify({
#             "success": True,
#             "subtitles": [
#                 {
#                     "start": sub[0][0],
#                     "end": sub[0][1], 
#                     "text": sub[1]
#                 } for sub in result['subtitles']
#             ],
#             "detected_language": result['language'],
#             "segments_count": result['segments_count'],
#             "trim_info": {
#                 "trim_start": result['trim_start'],
#                 "trim_end": result['trim_end'],
#                 "trimmed_duration": result['trimmed_duration']
#             },
#             "message": f"Generated {result['segments_count']} subtitle segments for trimmed portion"
#         })
        
#     except Exception as e:
#         print(f"[ERROR] Subtitle generation failed: {e}")
#         return jsonify({
#             "error": str(e),
#             "success": False,
#             "message": "Subtitle generation failed"
#         }), 500
    
#     finally:
#         # Cleanup
#         if temp_video and os.path.exists(temp_video.name):
#             try:
#                 os.unlink(temp_video.name)
#                 print("[CLEANUP] Deleted temp video file")
#             except Exception as e:
#                 print(f"[CLEANUP] Temp file cleanup failed: {e}")


# if __name__ == '__main__':
#     print("="*50)
#     print("[SERVER] Video Processing Server with Aspect-Ratio Aware Text")
#     print("[SERVER] Features:")
#     print("[SERVER] - Video trimming and audio overlay")
#     print("[SERVER] - Aspect-ratio aware font scaling")
#     print("[SERVER] - Full-color emoji text rendering (Pilmoji)")
#     print("[SERVER] - HTTP video serving")
#     print("[SERVER] - Automatic temp file cleanup")
#     print("[SERVER] - Cross-platform compatibility")
#     print("="*50)
#     print("[SERVER] Flask server starting on port 5000...")
#     print("="*50)
    
#     app.run(host='0.0.0.0', port=5000, debug=True)







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
        model = load_whisper_model("small")
        
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
