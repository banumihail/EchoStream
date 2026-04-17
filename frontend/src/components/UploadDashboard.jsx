import React, { useState, useRef } from 'react';

const UploadDashboard = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const processFile = async (file) => {
    if (!file) return;
    
    // Quick validation
    const validExts = ['video/mp4', 'video/avi', 'video/quicktime', 'video/x-matroska', 'video/webm'];
    if (!validExts.includes(file.type)) {
      setError("Please upload a valid video file (.mp4, .avi, .mov, .mkv, .webm)");
      return;
    }

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/upload-video', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed with status: ${response.status}`);
      }

      const data = await response.json();
      onUploadSuccess(data.task_id);
      
    } catch (err) {
      console.error(err);
      setError("An error occurred during upload. Is the API running?");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  };

  return (
    <div className="glass-panel" style={{ maxWidth: '600px', margin: '0 auto' }}>
      <div 
        className={`upload-zone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !uploading && fileInputRef.current.click()}
        style={{ borderColor: isDragging ? 'var(--accent-secondary)' : '' }}
      >
        <div className="upload-icon">
          {uploading ? '⏳' : '📥'}
        </div>
        <h3 style={{ marginBottom: '10px' }}>
          {uploading ? 'Uploading your video...' : 'Drag & Drop your video here'}
        </h3>
        <p style={{ color: 'var(--text-muted)' }}>
          {uploading ? 'Please wait, analyzing contents initially.' : 'Or click to browse files (MP4, AVI, MOV)'}
        </p>

        <input 
          type="file" 
          ref={fileInputRef} 
          className="file-input" 
          accept="video/mp4,video/avi,video/quicktime,video/x-matroska,video/webm"
          onChange={handleFileChange}
          disabled={uploading}
        />
      </div>

      {error && (
        <div style={{ marginTop: '20px', color: 'var(--danger)', textAlign: 'center', background: 'rgba(244, 63, 94, 0.1)', padding: '12px', borderRadius: '8px' }}>
          {error}
        </div>
      )}
    </div>
  );
};

export default UploadDashboard;
