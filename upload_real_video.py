"""
Upload a real video file to test the complete pipeline
"""
import requests
import sys
import os


def upload_video(video_file_path):
    """Upload a video file to the API"""

    # Check if file exists
    if not os.path.exists(video_file_path):
        print(f"[ERROR] File not found: {video_file_path}")
        return

    # Check file extension
    valid_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    file_ext = os.path.splitext(video_file_path)[1].lower()
    if file_ext not in valid_extensions:
        print(f"[ERROR] Invalid file type. Use: {', '.join(valid_extensions)}")
        return

    print(f"[INFO] Uploading: {video_file_path}")
    print(f"[INFO] File size: {os.path.getsize(video_file_path) / 1024 / 1024:.2f} MB")

    try:
        url = "http://localhost:8000/upload-video"
        with open(video_file_path, "rb") as f:
            files = {"file": (os.path.basename(video_file_path), f, "video/mp4")}
            response = requests.post(url, files=files)

        if response.status_code == 200:
            data = response.json()
            print("\n" + "="*60)
            print("[SUCCESS] Video uploaded!")
            print("="*60)
            print(f"Task ID: {data['task_id']}")
            print(f"Filename: {data['filename']}")
            print(f"Status: {data['status']}")
            print(f"Message: {data['message']}")
            print("\nWatch the ASR Worker terminal to see processing!")
            print(f"Results will be saved to: results/{data['task_id']}_transcript.json")
            print("="*60)
        else:
            print(f"[ERROR] Upload failed: {response.status_code}")
            print(response.text)

    except requests.exceptions.ConnectionError:
        print("[ERROR] Cannot connect to API")
        print("Make sure the API is running: python api/main.py")
    except Exception as e:
        print(f"[ERROR] {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_real_video.py <path_to_video>")
        print("\nExample:")
        print("  python upload_real_video.py my_video.mp4")
        print("  python upload_real_video.py C:\\Videos\\speech_video.mp4")
    else:
        video_path = sys.argv[1]
        upload_video(video_path)
