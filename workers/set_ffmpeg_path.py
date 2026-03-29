"""
Configure FFmpeg path for moviepy and other libraries
Import this at the start of workers to set FFmpeg location
"""
import os
import sys

# Get project root directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ffmpeg_path = os.path.join(project_root, "ffmpeg")

# Add to system PATH for this process
if ffmpeg_path not in os.environ["PATH"]:
    os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ["PATH"]

# Set environment variable for imageio-ffmpeg (used by moviepy)
os.environ["IMAGEIO_FFMPEG_EXE"] = os.path.join(ffmpeg_path, "ffmpeg.exe")

print(f"[Config] FFmpeg path set to: {ffmpeg_path}")
