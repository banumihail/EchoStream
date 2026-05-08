import React, { useState, useEffect, useRef } from 'react';
import WorkerProgress from './WorkerProgress';
import InteractiveTranscript from './InteractiveTranscript';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const AnalysisDashboard = ({ taskId, onReset }) => {
  const [taskData, setTaskData] = useState(null);
  const [error, setError] = useState(null);
  const [isCensoring, setIsCensoring] = useState(false);
  
  // Configuration State
  const [showConfig, setShowConfig] = useState(false);
  const [censorAudio, setCensorAudio] = useState(true);
  const [blurObjects, setBlurObjects] = useState(['person']);
  const [videoMode, setVideoMode] = useState('blur');     // box | blur | pixelate
  const [audioMode, setAudioMode] = useState('beep');     // silence | beep | muffle
  const [faceMode, setFaceMode] = useState('selected');   // selected | others
  // Each entry: { id, file, name, preview }
  const [references, setReferences] = useState([]);

  // Ref to the original video element so the interactive transcript can seek it
  const originalVideoRef = useRef(null);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const res = await fetch(`${API_URL}/tasks/${taskId}`);
        if (!res.ok) throw new Error('Could not fetch task data');
        const data = await res.json();
        if (active) {
          setTaskData(data);
          setError(null);
          if (data.status === 'censored') setIsCensoring(false);
          
          // Auto-select objects if they were detected
          if (data.vision_analysis && data.vision_analysis.summary && blurObjects.length === 1 && blurObjects[0] === 'person') {
              const detectedLabels = data.vision_analysis.summary.map(s => s.label);
              if (detectedLabels.includes('person')) {
                 setBlurObjects(['person']);
              } else if (detectedLabels.length > 0) {
                 setBlurObjects([]); // Or default to something else
              }
          }
        }
      } catch (err) {
        if (active) setError('Connection to API lost. Retrying...');
      }
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => { active = false; clearInterval(interval); };
  }, [taskId]);

  const handleCensor = async () => {
    setIsCensoring(true);
    setShowConfig(false);
    try {
      const fd = new FormData();
      fd.append('censor_audio', String(censorAudio));
      fd.append('blur_objects', blurObjects.join(','));
      fd.append('video_mode', videoMode);
      fd.append('audio_mode', audioMode);
      fd.append('face_mode', faceMode);
      // Names array kept in lockstep with files
      fd.append('reference_names', references.map(r => r.name || '').join(','));
      for (const ref of references) fd.append('reference_faces', ref.file);
      await fetch(`${API_URL}/tasks/${taskId}/censor`, { method: 'POST', body: fd });
    } catch (err) {
      console.error(err);
      setIsCensoring(false);
    }
  };

  const addReference = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    files.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        setReferences((prev) => [...prev, {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          file,
          name: '',
          preview: ev.target.result,
        }]);
      };
      reader.readAsDataURL(file);
    });
    // reset input so the same file can be re-added later
    e.target.value = '';
  };

  const removeReference = (id) => {
    setReferences((prev) => prev.filter(r => r.id !== id));
  };

  const renameReference = (id, name) => {
    setReferences((prev) => prev.map(r => r.id === id ? { ...r, name } : r));
  };

  const toggleBlurObject = (label) => {
    setBlurObjects(prev => 
      prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]
    );
  };

  if (!taskData) {
    return (
      <div className="glass-panel fade-in" style={{ textAlign: 'center', padding: '60px 24px' }}>
        <div className="spinner" style={{ margin: '0 auto 20px' }} />
        <h2 className="pulse-text" style={{ marginBottom: 8 }}>Syncing with AI Engines...</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Task: {taskId.slice(0, 8)}...</p>
      </div>
    );
  }

  // Can censor if it has PII or if there are objects we can blur
  const hasObjects = taskData.vision_analysis?.summary?.length > 0;
  const canCensor = taskData.has_pii || hasObjects;
  const showCensorBtn = !isCensoring && canCensor &&
    ['completed', 'analyzing'].includes(taskData.status);
    
  const hasCensored = taskData.status === 'censored' && taskData.censored_file_path;
  const originalUrl = taskData.file_path ? `${API_URL}/${taskData.file_path}` : null;
  const censoredUrl = hasCensored ? `${API_URL}/${taskData.censored_file_path}` : null;

  const detectedObjects = taskData.vision_analysis?.summary || [];

  return (
    <div className="fade-in">
      {/* Error Banner */}
      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠️</span>
          <p>{error}</p>
        </div>
      )}

      {/* Status Header */}
      <div className="glass-panel" style={{ marginBottom: 20 }}>
        <div className="status-header">
          <div className="status-header-left">
            <h2>🎬 <span style={{ color: 'var(--accent-secondary)' }}>{taskData.filename}</span></h2>
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <span className={`badge ${taskData.status}`}>{taskData.status?.toUpperCase()}</span>
              {taskData.has_pii && <span className="badge pii">⚠ PII DETECTED</span>}
            </div>
          </div>
          <div className="status-header-right">
            {showCensorBtn && !showConfig && (
              <button className="btn btn-danger" onClick={() => setShowConfig(true)}>
                🛡️ Configure Censorship
              </button>
            )}
            {(isCensoring || taskData.status === 'censoring') && (
              <button className="btn btn-outline" disabled>
                <div className="spinner" /> Rendering...
              </button>
            )}
            <button className="btn btn-outline" onClick={onReset}>
              ✚ New Video
            </button>
          </div>
        </div>
        
        {/* Configuration Panel */}
        {showConfig && (
          <div className="fade-in" style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--glass-border)' }}>
            <h3 style={{ marginBottom: 12, fontSize: '1.1rem' }}>Censorship Settings</h3>
            
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 20 }}>
              {/* Audio Settings */}
              <div style={{ flex: 1, minWidth: '250px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                  <input
                    type="checkbox"
                    checked={censorAudio}
                    onChange={(e) => setCensorAudio(e.target.checked)}
                    style={{ width: 18, height: 18 }}
                  />
                  <span>
                    <strong>Censor PII Audio</strong>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Targets PER, LOC, ORG</div>
                  </span>
                </label>
                <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', opacity: censorAudio ? 1 : 0.5 }}>
                  <strong style={{ display: 'block', marginBottom: 6, fontSize: '0.9rem' }}>Audio style</strong>
                  <select
                    className="censor-select"
                    value={audioMode}
                    onChange={(e) => setAudioMode(e.target.value)}
                    disabled={!censorAudio}
                  >
                    <option value="beep">Beep (1 kHz tone)</option>
                    <option value="muffle">Muffle (low-pass)</option>
                    <option value="silence">Silence</option>
                  </select>
                </div>
              </div>

              {/* Vision Settings */}
              <div style={{ flex: 2, minWidth: '300px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                  <strong style={{ display: 'block', marginBottom: 8 }}>Select Objects to Censor:</strong>
                  {detectedObjects.length > 0 ? (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                      {detectedObjects.map(obj => (
                        <label key={obj.label} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={blurObjects.includes(obj.label)}
                            onChange={() => toggleBlurObject(obj.label)}
                          />
                          <span style={{ fontSize: '0.9rem' }}>{obj.label} ({obj.count})</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No objects detected yet.</span>
                  )}
                </div>
                <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', opacity: blurObjects.length ? 1 : 0.5 }}>
                  <strong style={{ display: 'block', marginBottom: 6, fontSize: '0.9rem' }}>Video style</strong>
                  <select
                    className="censor-select"
                    value={videoMode}
                    onChange={(e) => setVideoMode(e.target.value)}
                    disabled={!blurObjects.length}
                  >
                    <option value="blur">Gaussian blur</option>
                    <option value="pixelate">Pixelate (mosaic)</option>
                    <option value="box">Black box</option>
                  </select>
                </div>
              </div>
            </div>
            
            {/* Identity-targeted blur */}
            <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', marginBottom: 16 }}>
              <strong style={{ display: 'block', marginBottom: 6, fontSize: '0.95rem' }}>
                Identity-targeted blur <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '0.8rem' }}>(optional)</span>
              </strong>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0 0 10px' }}>
                Add reference photos and pick a mode. Per-frame face detection follows movement automatically.
              </p>

              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input type="radio" name="faceMode" value="selected" checked={faceMode === 'selected'} onChange={() => setFaceMode('selected')} />
                  <span style={{ fontSize: '0.88rem' }}>Blur these people</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input type="radio" name="faceMode" value="others" checked={faceMode === 'others'} onChange={() => setFaceMode('others')} />
                  <span style={{ fontSize: '0.88rem' }}>Blur everyone else</span>
                </label>
              </div>

              {references.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 10 }}>
                  {references.map((r) => (
                    <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--glass-border)', borderRadius: 8 }}>
                      <img src={r.preview} alt="" style={{ width: 44, height: 44, objectFit: 'cover', borderRadius: 6 }} />
                      <input
                        className="censor-select"
                        type="text"
                        placeholder="Name (optional)"
                        value={r.name}
                        onChange={(e) => renameReference(r.id, e.target.value)}
                        style={{ width: 120, padding: '4px 8px', fontSize: '0.82rem' }}
                      />
                      <button className="btn btn-outline" style={{ padding: '4px 10px', fontSize: '0.72rem' }} onClick={() => removeReference(r.id)}>
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <label className="btn btn-outline" style={{ cursor: 'pointer', display: 'inline-block' }}>
                + Add reference photo
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  onChange={addReference}
                  style={{ display: 'none' }}
                />
              </label>

              {faceMode === 'others' && references.length === 0 && (
                <p style={{ fontSize: '0.8rem', color: 'var(--accent-secondary)', marginTop: 8 }}>
                  No references — every detected face will be blurred (full anonymization).
                </p>
              )}
            </div>

            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={() => setShowConfig(false)}>Cancel</button>
              <button className="btn btn-danger" onClick={handleCensor}>
                {(references.length > 0 || faceMode === 'others') ? 'Start Face-Tracked Censorship' : 'Start Censorship'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Worker Progress Chips */}
      <WorkerProgress taskData={taskData} />

      {/* Face blur stats — shown after a face-tracked censorship completes */}
      {taskData.face_blur_stats?.length > 0 && (
        <div className="glass-panel" style={{ marginBottom: 20, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: '1.1rem' }}>👤</span>
            <strong>Identity-aware redaction stats</strong>
            <span style={{ marginLeft: 'auto', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Mode: {taskData.face_blur_mode === 'others' ? 'Blur everyone else' : 'Blur selected'}
            </span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            {taskData.face_blur_stats.map((s, i) => (
              <div key={i} style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.04)', borderRadius: 6, border: '1px solid var(--glass-border)', minWidth: 180 }}>
                <div style={{ fontWeight: 600, fontSize: '0.92rem' }}>{s.name}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Blurred in <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>{s.matched_frames}</span> frames
                  {s.peak_similarity != null && (
                    <span> · peak sim {s.peak_similarity}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Video Section */}
      {(originalUrl || censoredUrl) && (
        <div className="video-section">
          {hasCensored ? (
            <div className="video-comparison">
              <div className="video-pane glass-panel" style={{ padding: 12 }}>
                <span className="video-label original">Original</span>
                <video ref={originalVideoRef} controls src={originalUrl} />
              </div>
              <div className="video-pane glass-panel" style={{ padding: 12 }}>
                <span className="video-label censored">✓ Censored</span>
                <video controls src={censoredUrl} />
              </div>
            </div>
          ) : originalUrl && (
            <div className="glass-panel" style={{ padding: 12, marginBottom: 24 }}>
              <div className="video-pane">
                <span className="video-label original">Original Upload</span>
                <video ref={originalVideoRef} controls src={originalUrl} style={{ width: '100%', borderRadius: 'var(--radius-md)', background: '#000' }} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Analysis Grid */}
      <div className="dashboard-grid">
        {/* Transcription */}
        <div className="dashboard-card glass-panel transcript-card">
          <div className="card-header">
            <span className="card-icon">🎤</span>
            <h3>Speech Transcript</h3>
          </div>
          <InteractiveTranscript
            chunks={taskData.transcription_metadata?.chunks}
            videoRef={originalVideoRef}
            fallbackText={taskData.transcript}
          />
        </div>

        {/* NER */}
        <div className="dashboard-card glass-panel">
          <div className="card-header">
            <span className="card-icon">🧠</span>
            <h3>Named Entities (BERT)</h3>
          </div>
          {taskData.ner_analysis ? (
            taskData.ner_analysis.flagged_entities?.length > 0 ? (
              <div>
                <p style={{ color: 'var(--danger)', marginBottom: 10, fontSize: '0.9rem' }}>
                  Sensitive data identified:
                </p>
                {taskData.ner_analysis.flagged_entities.map((e, i) => (
                  <span key={i} className="tag tag-danger">
                    {e.type}: {e.text} ({Math.round(e.score * 100)}%)
                  </span>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--success)', fontSize: '0.9rem' }}>✅ No sensitive PII detected.</p>
            )
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Analyzing transcript for PII...
            </p>
          )}
        </div>

        {/* Audio Events */}
        <div className="dashboard-card glass-panel">
          <div className="card-header">
            <span className="card-icon">🔊</span>
            <h3>Audio Environment (AST)</h3>
          </div>
          {taskData.audio_event_analysis ? (
            <div>
              {taskData.audio_event_analysis.events.slice(0, 5).map((ev, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 0', borderBottom: i < 4 ? '1px solid var(--glass-border)' : 'none'
                }}>
                  <span style={{ fontSize: '0.9rem' }}>{ev.label}</span>
                  <span style={{
                    color: 'var(--accent-primary)', fontWeight: 600, fontSize: '0.85rem'
                  }}>{Math.round(ev.score * 100)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Running spectrogram analysis...
            </p>
          )}
        </div>

        {/* Vision */}
        <div className="dashboard-card glass-panel">
          <div className="card-header">
            <span className="card-icon">👁️</span>
            <h3>Visual Objects (DETR)</h3>
          </div>
          {taskData.vision_analysis ? (
            taskData.vision_analysis.summary?.length > 0 ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {taskData.vision_analysis.summary.map((obj, i) => (
                  <span key={i} className="tag">
                    {obj.label} <span style={{ opacity: 0.5 }}>×{obj.count}</span>
                  </span>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: '0.9rem' }}>No high-confidence objects detected.</p>
            )
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Extracting and grading frames...
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default AnalysisDashboard;

