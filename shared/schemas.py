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


class VideoProcessingResponse(BaseModel):
    """Response schema for video upload endpoint"""
    task_id: str
    filename: str
    status: str
    message: str
