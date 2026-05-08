import React, { useState, useRef } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const UploadDashboard = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState('');
  const [url, setUrl] = useState('');
  const fileInputRef = useRef(null);

  const processFile = async (file) => {
    if (!file) return;
    const validExts = ['video/mp4', 'video/avi', 'video/quicktime', 'video/x-matroska', 'video/webm'];
    if (!validExts.includes(file.type)) {
      setError('Please upload a valid video file (.mp4, .avi, .mov, .mkv, .webm)');
      return;
    }
    setUploading(true);
    setError(null);
    setProgress('Uploading to server...');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_URL}/upload-video`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) throw new Error(`Upload failed (${response.status})`);
      setProgress('Queuing AI workers...');
      const data = await response.json();
      onUploadSuccess(data.task_id);
    } catch (err) {
      console.error(err);
      setError('Upload failed. Is the API server running?');
    } finally {
      setUploading(false);
      setProgress('');
    }
  };

  const submitUrl = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    if (!/^https?:\/\//i.test(trimmed)) {
      setError('URL must start with http:// or https://');
      return;
    }
    setUploading(true);
    setError(null);
    setProgress('Downloading video from URL...');
    try {
      const res = await fetch(`${API_URL}/upload-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Upload failed (${res.status})`);
      }
      setProgress('Queuing AI workers...');
      const data = await res.json();
      onUploadSuccess(data.task_id);
    } catch (err) {
      console.error(err);
      setError(err.message || 'Could not download video from URL.');
    } finally {
      setUploading(false);
      setProgress('');
    }
  };

  return (
    <div className="fade-in" style={{ maxWidth: 640, margin: '60px auto 0' }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ fontSize: '2.4rem', fontWeight: 700, marginBottom: 8 }}>
          <span className="gradient-text">AI Video Moderation</span>
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '1.05rem' }}>
          Upload a video to analyze speech, detect PII, classify audio, and identify objects.
        </p>
      </div>

      <div className="glass-panel">
        <div
          className={`upload-zone ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
          onDrop={(e) => {
            e.preventDefault(); setIsDragging(false);
            if (e.dataTransfer.files?.length) processFile(e.dataTransfer.files[0]);
          }}
          onClick={() => !uploading && fileInputRef.current.click()}
        >
          <div className="upload-icon">{uploading ? '⏳' : '📥'}</div>
          <h3 style={{ marginBottom: 8, position: 'relative' }}>
            {uploading ? progress || 'Processing...' : 'Drag & Drop your video here'}
          </h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', position: 'relative' }}>
            {uploading ? 'This may take a moment' : 'Or click to browse — MP4, AVI, MOV, MKV, WebM'}
          </p>
          {uploading && <div className="spinner" style={{ marginTop: 16, position: 'relative' }} />}
          <input
            type="file" ref={fileInputRef} className="file-input"
            accept="video/mp4,video/avi,video/quicktime,video/x-matroska,video/webm"
            onChange={(e) => e.target.files?.length && processFile(e.target.files[0])}
            disabled={uploading}
          />
        </div>

        {/* URL submit — paste a link from YouTube, Twitter, Vimeo, etc. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 16 }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>or paste URL</span>
          <input
            type="text"
            className="url-input"
            placeholder="https://youtube.com/watch?v=..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !uploading) submitUrl(); }}
            disabled={uploading}
          />
          <button
            className="btn btn-outline"
            onClick={submitUrl}
            disabled={uploading || !url.trim()}
          >
            Fetch
          </button>
        </div>

        {error && (
          <div className="error-banner" style={{ marginTop: 16 }}>
            <span className="error-icon">⚠️</span>
            <p>{error}</p>
            <button className="btn btn-outline btn-sm" onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}
      </div>

      <div style={{ textAlign: 'center', marginTop: 24, color: 'var(--text-dim)', fontSize: '0.82rem' }}>
        Powered by Whisper · BERT · AST · DETR · FFmpeg
      </div>
    </div>
  );
};

export default UploadDashboard;
