import React, { useState, useRef } from 'react';
import { authFetch } from '../lib/auth';

const UploadDashboard = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState('');
  const [url, setUrl] = useState('');
  const [processingMode, setProcessingMode] = useState('auto');
  const fileInputRef = useRef(null);

  const processFile = async (file) => {
    if (!file) return;
    const validExts = ['video/mp4', 'video/avi', 'video/quicktime', 'video/x-matroska', 'video/webm'];
    if (!validExts.includes(file.type)) {
      setError('Unsupported format. Accepted: .mp4 .avi .mov .mkv .webm');
      return;
    }
    setUploading(true);
    setError(null);
    setProgress('Transferring to ingestion server...');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('processing_mode', processingMode);

    try {
      const response = await authFetch('/upload-video', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) throw new Error(`Upload failed (${response.status})`);
      setProgress('Dispatching workers...');
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
    setProgress('Pulling source from remote URL...');
    try {
      const res = await authFetch('/upload-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed, processing_mode: processingMode }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Upload failed (${res.status})`);
      }
      setProgress('Dispatching workers...');
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
    <div className="fade-in" style={{ maxWidth: 880, margin: '40px auto 0' }}>
      {/* Editorial header */}
      <div className="section-head" style={{ marginBottom: 36 }}>
        <span className="section-num">01 — Intake</span>
        <h1 className="section-title">
          New <em>case</em>
        </h1>
        <span className="section-meta">
          {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: '2-digit' }).toUpperCase()}
        </span>
      </div>

      {/* Editorial lede paragraph */}
      <p
        className="serif"
        style={{
          fontSize: 22,
          lineHeight: 1.4,
          color: 'var(--bone-2)',
          maxWidth: 640,
          marginBottom: 40,
          fontWeight: 300,
        }}
      >
        Drop a video here. We will transcribe its speech, surface
        sensitive entities, classify the soundscape, locate every visible
        object, and—if you want—<em style={{ color: 'var(--acid)', fontStyle: 'italic' }}>redact</em> what
        shouldn't be seen or heard.
      </p>

      <div className="intake">
        <div
          className={`dropzone ${isDragging ? 'dragging' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
          onDrop={(e) => {
            e.preventDefault(); setIsDragging(false);
            if (e.dataTransfer.files?.length) processFile(e.dataTransfer.files[0]);
          }}
          onClick={() => !uploading && fileInputRef.current.click()}
          role="button"
          tabIndex={0}
        >
          <span className="dropzone-mark tl" />
          <span className="dropzone-mark tr" />
          <span className="dropzone-mark bl" />
          <span className="dropzone-mark br" />

          <div className="dropzone-scope" aria-hidden="true">
            <span className="dropzone-scope-ring" />
            <span className="dropzone-scope-ring-inner" />
          </div>

          <div className="dropzone-title">
            {uploading ? (
              <span className="cursor-blink">{progress || 'Working'}</span>
            ) : (
              <>Drop source <em style={{ fontStyle: 'italic', color: 'var(--acid)' }}>here</em></>
            )}
          </div>
          <div className="dropzone-subtitle">
            {uploading ? 'Hold' : 'mp4 · mov · mkv · webm · avi   //   click to browse'}
          </div>

          {uploading && <div className="spinner spinner-lg" style={{ marginTop: 22 }} />}

          <input
            type="file"
            ref={fileInputRef}
            className="file-input"
            accept="video/mp4,video/avi,video/quicktime,video/x-matroska,video/webm"
            onChange={(e) => e.target.files?.length && processFile(e.target.files[0])}
            disabled={uploading}
          />
        </div>

        {/* Processing mode */}
        <div className="intake-row">
          <span className="smallcaps">Mode</span>
          <div className="mode-toggle" style={{ marginRight: 'auto' }}>
            {[
              { v: 'auto',  label: 'Auto',  hint: 'Detect from duration' },
              { v: 'short', label: 'Short', hint: 'Whisper-base · dense vision' },
              { v: 'long',  label: 'Long',  hint: 'Whisper-small · sparse vision · audio timeline' },
            ].map(opt => (
              <button
                key={opt.v}
                type="button"
                title={opt.hint}
                className={`mode-toggle-btn ${processingMode === opt.v ? 'active' : ''}`}
                onClick={() => setProcessingMode(opt.v)}
                disabled={uploading}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <span className="smallcaps" style={{ fontFamily: 'var(--mono)', color: 'var(--bone-faint)' }}>
            {processingMode === 'auto'  && '∿ adaptive'}
            {processingMode === 'short' && '< 5 min'}
            {processingMode === 'long'  && '> 5 min'}
          </span>
        </div>

        {/* URL ingest */}
        <div className="intake-row">
          <span className="smallcaps">Or URL</span>
          <input
            type="text"
            className="text-input"
            placeholder="https://youtube.com/watch?v=… or tiktok.com/@…/video/…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !uploading) submitUrl(); }}
            disabled={uploading}
          />
          <button
            className="btn btn-outline btn-sm"
            onClick={submitUrl}
            disabled={uploading || !url.trim()}
          >
            Pull →
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ marginTop: 24 }}>
          <span className="error-banner-tag">Err</span>
          <p>{error}</p>
          <button className="btn btn-ghost btn-sm" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* footer credit — tiny editorial colophon */}
      <div
        style={{
          marginTop: 60,
          paddingTop: 24,
          borderTop: '1px solid var(--rule)',
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          gap: 12,
        }}
      >
        {[
          { num: '01', name: 'Whisper', role: 'Speech transcription' },
          { num: '02', name: 'BERT',    role: 'Named-entity recognition' },
          { num: '03', name: 'AST',     role: 'Audio scene classification' },
          { num: '04', name: 'DETR',    role: 'Object & face detection' },
          { num: '05', name: 'FFmpeg',  role: 'Redaction render pipeline' },
        ].map(p => (
          <div key={p.num}>
            <div className="smallcaps" style={{ color: 'var(--acid)', marginBottom: 6 }}>{p.num}</div>
            <div className="serif" style={{ fontSize: 17, color: 'var(--bone)', marginBottom: 2, letterSpacing: '-0.01em' }}>
              {p.name}
            </div>
            <div className="smallcaps" style={{ fontSize: 9.5, letterSpacing: '0.16em' }}>
              {p.role}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default UploadDashboard;
