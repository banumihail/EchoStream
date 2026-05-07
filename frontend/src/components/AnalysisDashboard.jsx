import React, { useState, useEffect } from 'react';
import WorkerProgress from './WorkerProgress';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const AnalysisDashboard = ({ taskId, onReset }) => {
  const [taskData, setTaskData] = useState(null);
  const [error, setError] = useState(null);
  const [isCensoring, setIsCensoring] = useState(false);
  
  // Configuration State
  const [showConfig, setShowConfig] = useState(false);
  const [censorAudio, setCensorAudio] = useState(true);
  const [blurObjects, setBlurObjects] = useState(['person']);

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
      await fetch(`${API_URL}/tasks/${taskId}/censor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ censor_audio: censorAudio, blur_objects: blurObjects })
      });
    } catch (err) {
      console.error(err);
      setIsCensoring(false);
    }
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
              <div style={{ flex: 1, minWidth: '250px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                  <input 
                    type="checkbox" 
                    checked={censorAudio} 
                    onChange={(e) => setCensorAudio(e.target.checked)}
                    style={{ width: 18, height: 18 }}
                  />
                  <span>
                    <strong>Mute PII Audio</strong>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Mute detected entities like PER, LOC, ORG</div>
                  </span>
                </label>
              </div>
              
              {/* Vision Settings */}
              <div style={{ flex: 2, minWidth: '300px' }}>
                <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                  <strong style={{ display: 'block', marginBottom: 8 }}>Select Objects to Blur:</strong>
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
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={() => setShowConfig(false)}>Cancel</button>
              <button className="btn btn-danger" onClick={handleCensor}>Start Censorship</button>
            </div>
          </div>
        )}
      </div>

      {/* Worker Progress Chips */}
      <WorkerProgress taskData={taskData} />

      {/* Video Section */}
      {(originalUrl || censoredUrl) && (
        <div className="video-section">
          {hasCensored ? (
            <div className="video-comparison">
              <div className="video-pane glass-panel" style={{ padding: 12 }}>
                <span className="video-label original">Original</span>
                <video controls src={originalUrl} />
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
                <video controls src={originalUrl} style={{ width: '100%', borderRadius: 'var(--radius-md)', background: '#000' }} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Analysis Grid */}
      <div className="dashboard-grid">
        {/* Transcription */}
        <div className="dashboard-card glass-panel">
          <div className="card-header">
            <span className="card-icon">🎤</span>
            <h3>Speech Transcript</h3>
          </div>
          {taskData.transcript ? (
            <div className="text-transcript">{taskData.transcript}</div>
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Waiting for Whisper ASR...
            </p>
          )}
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

