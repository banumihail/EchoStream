from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from dotenv import load_dotenv
import time
import uvicorn
import uuid
import os
import sys

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

# Add parent directory to path to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.rabbitmq_client import RabbitMQClient
from shared.elasticsearch_client import ElasticsearchClient
from shared.schemas import VideoProcessingTask, VideoProcessingResponse
from pydantic import BaseModel

class CensorRequest(BaseModel):
    censor_audio: bool = True
    blur_objects: list[str] = ["person"]
    video_mode: str = "blur"   # box | blur | pixelate
    audio_mode: str = "beep"   # silence | beep | muffle


class UrlUploadRequest(BaseModel):
    url: str

app = FastAPI(title="EchoStream API")

# Setup CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve upload directory relative to the project root so it doesn't depend on
# which directory the API process is launched from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_upload_dir_env = os.getenv("UPLOAD_DIR", "uploads")
UPLOAD_DIR = _upload_dir_env if os.path.isabs(_upload_dir_env) else os.path.join(_PROJECT_ROOT, _upload_dir_env)

RABBITMQ_QUEUE = "video_processing_queue"
AUDIO_EVENT_QUEUE = "audio_event_queue"
VISION_QUEUE = "vision_queue"
CENSOR_QUEUE = "censor_queue"

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve static files for frontend video player
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Initialize clients (will connect lazily)
rabbitmq_client = None
es_client = None


def cleanup_old_files(max_age_seconds=None):
    """Delete files in UPLOAD_DIR older than max_age_seconds (default from env or 1 hour)"""
    if max_age_seconds is None:
        max_age_seconds = int(os.getenv("CLEANUP_MAX_AGE_SECONDS", "3600"))
    if not os.path.exists(UPLOAD_DIR):
        return
    now = time.time()
    for filename in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            if os.stat(file_path).st_mtime < now - max_age_seconds:
                try:
                    os.remove(file_path)
                    print(f"Deleted old file: {file_path}")
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")


def get_rabbitmq_client():
    """Initialize a fresh RabbitMQ client to avoid heartbeat timeouts"""
    client = RabbitMQClient()
    client.connect()
    client.declare_queue(RABBITMQ_QUEUE)
    client.declare_queue(AUDIO_EVENT_QUEUE)
    client.declare_queue(VISION_QUEUE)
    client.declare_queue(CENSOR_QUEUE)
    return client


def get_es_client():
    """Lazy initialization of Elasticsearch client"""
    global es_client
    if es_client is None:
        es_client = ElasticsearchClient()
        es_client.connect()
    return es_client


@app.get("/")
def read_root():
    return {
        "message": "EchoStream API is online!",
        "version": "1.1",
        "endpoints": {
            "upload": "/upload-video",
            "task": "/tasks/{task_id}",
            "tasks": "/tasks",
            "docs": "/docs"
        }
    }


@app.get("/tasks")
def list_tasks():
    """List all recent tasks"""
    es = get_es_client()
    tasks = es.list_tasks(size=50)
    return tasks


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    """Get the current progress and results of a task"""
    es = get_es_client()
    task = es.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.post("/tasks/{task_id}/censor")
async def censor_video(
    task_id: str,
    censor_audio: bool = Form(True),
    blur_objects: str = Form("person"),    # comma-separated to keep multipart simple
    video_mode: str = Form("blur"),
    audio_mode: str = Form("beep"),
    face_mode: str = Form("selected"),     # 'selected' | 'others'
    reference_names: str = Form(""),       # comma-separated, aligned with reference_faces
    reference_faces: list[UploadFile] = File(default=[]),
):
    """Trigger the Active Censorship pipeline. If reference photos are uploaded,
    the worker switches to per-frame face-tracking blur. With face_mode='selected'
    it blurs faces matching any reference; with 'others' it blurs everyone NOT
    matching a reference (anonymize-bystanders)."""
    es = get_es_client()
    task = es.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if face_mode not in ("selected", "others"):
        raise HTTPException(status_code=400, detail="face_mode must be 'selected' or 'others'")

    names = [n.strip() for n in reference_names.split(",")] if reference_names else []
    face_refs = []
    if reference_faces:
        ref_dir = os.path.join(UPLOAD_DIR, "refs")
        os.makedirs(ref_dir, exist_ok=True)
        for i, rf in enumerate(reference_faces):
            if not rf or not rf.filename:
                continue
            ext = os.path.splitext(rf.filename)[1].lower() or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                raise HTTPException(status_code=400, detail=f"Unsupported reference image type: {ext}")
            ref_filename = f"{task_id}_{i}_{uuid.uuid4().hex[:8]}{ext}"
            ref_full_path = os.path.join(ref_dir, ref_filename)
            with open(ref_full_path, "wb") as f:
                f.write(await rf.read())
            rel = os.path.relpath(ref_full_path, _PROJECT_ROOT).replace("\\", "/")
            face_refs.append({
                "path": rel,
                "name": (names[i] if i < len(names) and names[i] else f"Person {i + 1}"),
            })

    if face_mode == "selected" and not face_refs:
        # 'selected' without references is a no-op for face blur — fall through to FFmpeg path.
        pass

    censor_payload = {
        "task_id": task_id,
        "file_path": task.get("file_path"),
        "censor_audio": censor_audio,
        "blur_objects": [s.strip() for s in blur_objects.split(",") if s.strip()],
        "video_mode": video_mode,
        "audio_mode": audio_mode,
        "face_mode": face_mode,
        "face_references": face_refs,
    }
    client = get_rabbitmq_client()
    client.publish_message(CENSOR_QUEUE, censor_payload)
    client.close()
    es.update_worker_status(task_id, "censor", "pending")
    return {"message": "Censorship task queued successfully", "task_id": task_id}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task and its associated files"""
    es = get_es_client()
    task = es.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # Delete from DB
    es.delete_task(task_id)
    
    # Delete associated files from disk
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def safe_delete(filepath):
        """Resolve path and delete file if it exists"""
        if not filepath:
            return
        if not os.path.isabs(filepath):
            filepath = os.path.join(project_root, filepath)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"Deleted file: {filepath}")
            except Exception as e:
                print(f"Failed to delete {filepath}: {e}")

    safe_delete(task.get("file_path"))
    safe_delete(task.get("censored_file_path"))
    safe_delete(task.get("audio_path"))

    return {"message": "Task and files deleted successfully"}


@app.post("/upload-url", response_model=VideoProcessingResponse)
def upload_url(payload: UrlUploadRequest):
    """Download a video by URL via yt-dlp, then enqueue it through the same
    pipeline as direct uploads. Supports YouTube, Twitter, Vimeo, and ~1000
    other sites yt-dlp covers."""
    import yt_dlp

    url = (payload.url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    task_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Force the output to .mp4 so the rest of the pipeline (which assumes .mp4
    # for the censored-output path replacement) works without special-casing.
    out_template = os.path.join(UPLOAD_DIR, f"{timestamp}_{task_id}.%(ext)s")
    ydl_opts = {
        "outtmpl": out_template,
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        downloaded_path = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp4"
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Could not download video: {str(e)[:200]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"yt-dlp failure: {str(e)[:200]}")

    if not os.path.exists(downloaded_path):
        # Fallback: yt-dlp sometimes keeps the original ext when no merge is needed
        for cand_ext in ("webm", "mkv", "mov"):
            cand = os.path.join(UPLOAD_DIR, f"{timestamp}_{task_id}.{cand_ext}")
            if os.path.exists(cand):
                downloaded_path = cand
                break
        else:
            raise HTTPException(status_code=500, detail="Download finished but file not found.")

    relative_file_path = os.path.relpath(downloaded_path, _PROJECT_ROOT).replace("\\", "/")
    title = info.get("title") or os.path.basename(downloaded_path)

    task = VideoProcessingTask(
        task_id=task_id,
        filename=title,
        file_path=relative_file_path,
        uploaded_at=datetime.now().isoformat(),
        status="pending",
    )

    es = get_es_client()
    es.create_task(task.model_dump())

    client = get_rabbitmq_client()
    client.publish_message(RABBITMQ_QUEUE, task.model_dump())
    client.publish_message(AUDIO_EVENT_QUEUE, task.model_dump())
    client.publish_message(VISION_QUEUE, task.model_dump())
    client.close()

    return VideoProcessingResponse(
        task_id=task_id,
        filename=title,
        status="queued",
        message="Video downloaded and queued for processing",
    )


@app.post("/upload-video", response_model=VideoProcessingResponse)
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload a video file for processing

    The video will be:
    1. Saved to disk
    2. Added to RabbitMQ queue for processing by AI workers
    3. Return a task_id for tracking
    4. Clean up old files in the background
    """
    background_tasks.add_task(cleanup_old_files)
    allowed_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}")

    task_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{task_id}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    # Store path relative to project root with forward slashes so workers and the
    # frontend URL both resolve it consistently regardless of OS path separators.
    relative_file_path = os.path.relpath(file_path, _PROJECT_ROOT).replace("\\", "/")

    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        task = VideoProcessingTask(
            task_id=task_id, filename=file.filename,
            file_path=relative_file_path, uploaded_at=datetime.now().isoformat(),
            status="pending"
        )

        # Create the ES document FIRST so workers can update its status the
        # instant they pick up the queue message. Publishing before create_task
        # races the workers and produces document_missing_exception 404s.
        es = get_es_client()
        es.create_task(task.model_dump())

        client = get_rabbitmq_client()
        client.publish_message(RABBITMQ_QUEUE, task.model_dump())
        client.publish_message(AUDIO_EVENT_QUEUE, task.model_dump())
        client.publish_message(VISION_QUEUE, task.model_dump())
        client.close()

        return VideoProcessingResponse(
            task_id=task_id, filename=file.filename,
            status="queued", message="Video uploaded successfully and queued for processing"
        )

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.on_event("shutdown")
def shutdown_event():
    """Close connections on shutdown"""
    global rabbitmq_client, es_client
    if rabbitmq_client:
        rabbitmq_client.close()
    if es_client:
        es_client.close()


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
