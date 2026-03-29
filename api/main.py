from fastapi import FastAPI, UploadFile, File, HTTPException
from datetime import datetime
import uvicorn
import uuid
import os
import sys

# Add parent directory to path to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.rabbitmq_client import RabbitMQClient
from shared.schemas import VideoProcessingTask, VideoProcessingResponse

app = FastAPI(title="EchoStream API")

# Configuration
UPLOAD_DIR = "uploads"
RABBITMQ_QUEUE = "video_processing_queue"

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize RabbitMQ client (will connect on first upload)
rabbitmq_client = None


def get_rabbitmq_client():
    """Lazy initialization of RabbitMQ client"""
    global rabbitmq_client
    if rabbitmq_client is None:
        rabbitmq_client = RabbitMQClient()
        rabbitmq_client.connect()
        rabbitmq_client.declare_queue(RABBITMQ_QUEUE)
    return rabbitmq_client


@app.get("/")
def read_root():
    return {
        "message": "EchoStream API is online!",
        "version": "1.0",
        "endpoints": {
            "upload": "/upload-video",
            "docs": "/docs"
        }
    }


@app.post("/upload-video", response_model=VideoProcessingResponse)
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a video file for processing

    The video will be:
    1. Saved to disk
    2. Added to RabbitMQ queue for processing by AI workers
    3. Return a task_id for tracking
    """
    # Validate file type
    allowed_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Generate unique task ID and filename
    task_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{task_id}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    try:
        # Save file to disk
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Create task message
        task = VideoProcessingTask(
            task_id=task_id,
            filename=file.filename,
            file_path=file_path,
            uploaded_at=datetime.now().isoformat(),
            status="pending"
        )

        # Publish to RabbitMQ
        client = get_rabbitmq_client()
        client.publish_message(RABBITMQ_QUEUE, task.model_dump())

        return VideoProcessingResponse(
            task_id=task_id,
            filename=file.filename,
            status="queued",
            message="Video uploaded successfully and queued for processing"
        )

    except Exception as e:
        # Clean up file if something went wrong
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.on_event("shutdown")
def shutdown_event():
    """Close RabbitMQ connection on shutdown"""
    global rabbitmq_client
    if rabbitmq_client:
        rabbitmq_client.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
