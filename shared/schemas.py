"""
Shared schemas for EchoStream
Used by both API and Workers to ensure consistent message format
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class VideoProcessingTask(BaseModel):
    """Schema for video processing tasks sent to RabbitMQ"""
    task_id: str
    filename: str
    file_path: str
    uploaded_at: str
    status: str = "pending"
    # 'short' (Whisper-base, dense vision sampling) vs 'long' (Whisper-small,
    # sparse vision sampling, multi-window audio events). Auto-detected from
    # video duration at upload time when the user picks "auto".
    processing_mode: str = "short"
    duration_seconds: Optional[float] = None
    # Resource owner — set by the API from the authenticated user's JWT subject.
    # Used to enforce per-user access control on /tasks/* endpoints.
    owner_username: Optional[str] = None


class VideoProcessingResponse(BaseModel):
    """Response schema for video upload endpoint"""
    task_id: str
    filename: str
    status: str
    message: str
