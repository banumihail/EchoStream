import React, { useState, useEffect, useRef } from 'react';
import WorkerProgress from './WorkerProgress';
import InteractiveTranscript from './InteractiveTranscript';
import { authFetch, API_URL } from '../lib/auth';

const formatDuration = (sec) => {
  if (!sec || sec <= 0) return null;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
};

const AnalysisDashboard = ({ taskId, onReset }) => {
  const [taskData, setTaskData] = useState(null);
  const [error, setError] = useState(null);
  const [isCensoring, setIsCensoring] = useState(false);

  const [showConfig, setShowConfig] = useState(false);
  const [censorAudio, setCensorAudio] = useState(true);
  const [blurObjects, setBlurObjects] = useState(['person']);
  const [videoMode, setVideoMode] = useState('blur');
  const [blurStrength, setBlurStrength] = useState(5);
  const [audioMode, setAudioMode] = useState('beep');
  const [faceMode, setFaceMode] = useState('selected');
  const [references, setReferences] = useState([]);

  const originalVideoRef = useRef(null);
  // Apply the default blur selection only ONCE, when vision results first
  // arrive -- so the recurring poll can never reset the user's choices.
  const defaultsApplied = useRef(false);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const res = await authFetch(`/tasks/${taskId}`);
        if (!res.ok) throw new Error('Could not fetch task data');
        const data = await res.json();
        if (active) {
          setTaskData(data);
          setError(null);
          if (data.status === 'censored') setIsCensoring(false);

          // One-time default: select "person" if detected, otherwise nothing.
          // Guarded by a ref (never by reading blurObjects), so it runs exactly
          // once and can never reset the user's later checkbox choices.
          if (!defaultsApplied.current && data.vision_analysis?.summary?.length) {
            defaultsApplied.current = true;
            const labels = data.vision_analysis.summary.map(s => s.label);
            setBlurObjects(labels.includes('person') ? ['person'] : []);
          }
        }
      } catch {
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
      fd.append('blur_strength', String(blurStrength));
      fd.append('audio_mode', audioMode);
      fd.append('face_mode', faceMode);
      fd.append('reference_names', references.map(r => r.name || '').join(','));
      for (const ref of references) fd.append('reference_faces', ref.file);
      await authFetch(`/tasks/${taskId}/censor`, { method: 'POST', body: fd });
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
    e.target.value = '';
  };

  const removeReference = (id) => setReferences((prev) => prev.filter(r => r.id !== id));
  const renameReference = (id, name) => setReferences((prev) => prev.map(r => r.id === id ? { ...r, name } : r));
  const toggleBlurObject = (label) =>
    setBlurObjects(prev => prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]);

  if (!taskData) {
    return (
      <div className="fade-in" style={{ textAlign: 'center', padding: '120px 24px' }}>
        <div className="numeral-huge" style={{ marginBottom: 20 }}>00</div>
        <div className="smallcaps smallcaps-acid pulse-text" style={{ marginBottom: 8 }}>
          Connecting to console
        </div>
        <p className="serif-italic" style={{ fontSize: 22, color: 'var(--bone-2)' }}>
          syncing case <span className="mono" style={{ color: 'var(--acid)' }}>{taskId.slice(0, 8)}</span>
        </p>
      </div>
    );
  }

  const hasObjects = taskData.vision_analysis?.summary?.length > 0;
  const canCensor = taskData.has_pii || hasObjects;
  const showCensorBtn = !isCensoring && canCensor && ['completed', 'analyzing'].includes(taskData.status);

  const hasCensored = taskData.status === 'censored' && taskData.censored_file_path;
  const originalUrl = taskData.file_path ? `${API_URL}/${taskData.file_path}` : null;
  const censoredUrl = hasCensored ? `${API_URL}/${taskData.censored_file_path}` : null;
  const detectedObjects = taskData.vision_analysis?.summary || [];
  // One strength slider governs BOTH object blur and identity-aware face blur
  // (the censor worker applies blur_strength to each). Show it whenever a blur
  // or pixelate effect is actually in play for objects or faces.
  const faceRedactionActive = references.length > 0 || faceMode === 'others';
  const blurMethodActive = videoMode === 'blur' || videoMode === 'pixelate';
  const showStrength = blurMethodActive && (blurObjects.length > 0 || faceRedactionActive);

  const dur = formatDuration(taskData.duration_seconds);

  return (
    <div className="fade-in">
      {error && (
        <div className="error-banner">
          <span className="error-banner-tag">Net</span>
          <p>{error}</p>
          <span />
        </div>
      )}

      {/* CASE HEADER */}
      <div className="case-header slate--marks">
        <div className="case-header-left">
          <div className="case-header-eyebrow">
            <span className="section-num">02 — Case</span>
            <span className="case-header-id">id · {taskId.slice(0, 12)}</span>
          </div>
          <h2 className="case-header-title">{taskData.filename}</h2>
          <div className="case-header-meta">
            <span className={`badge ${taskData.status}`}>{taskData.status}</span>
            {taskData.has_pii && <span className="badge pii">PII detected</span>}
            {taskData.processing_mode === 'long' && (
              <span
                className="badge long-mode"
                title="Long-form processing: Whisper-small + sparse vision sampling + audio-event timeline"
              >
                Long-form
              </span>
            )}
            {dur && <span className="badge duration">{dur}</span>}
          </div>
        </div>

        <div className="case-header-actions">
          {showCensorBtn && !showConfig && (
            <button className="btn btn-primary" onClick={() => setShowConfig(true)}>
              Configure redaction
            </button>
          )}
          {(isCensoring || taskData.status === 'censoring') && (
            <button className="btn btn-outline" disabled>
              <div className="spinner" /> Rendering
            </button>
          )}
          <button className="btn btn-ghost" onClick={onReset}>
            ← New case
          </button>
        </div>

        {/* CONFIG PANEL */}
        {showConfig && (
          <div className="config-block fade-in" style={{ gridColumn: '1 / -1' }}>
            <div className="section-head" style={{ marginBottom: 18, paddingBottom: 12 }}>
              <span className="section-num">02·a</span>
              <h3 className="section-title" style={{ fontSize: 22 }}>Redaction <em>parameters</em></h3>
              <span />
            </div>

            <div className="config-grid">
              {/* AUDIO */}
              <div className="config-card">
                <div className="config-card-title">
                  <span className="num">A —</span> Audio redaction
                </div>

                <label className="check-row">
                  <input
                    type="checkbox"
                    className="check"
                    checked={censorAudio}
                    onChange={(e) => setCensorAudio(e.target.checked)}
                  />
                  <span>
                    <strong>Mute PII speech</strong>
                    <span className="hint">Targets PER · LOC · ORG</span>
                  </span>
                </label>

                <div style={{ opacity: censorAudio ? 1 : 0.4, pointerEvents: censorAudio ? 'auto' : 'none' }}>
                  <span className="field-label">Method</span>
                  <select
                    className="select-input"
                    value={audioMode}
                    onChange={(e) => setAudioMode(e.target.value)}
                    disabled={!censorAudio}
                  >
                    <option value="beep">Beep — 1 kHz tone</option>
                    <option value="muffle">Muffle — low-pass</option>
                    <option value="silence">Silence</option>
                  </select>
                </div>
              </div>

              {/* VIDEO */}
              <div className="config-card">
                <div className="config-card-title">
                  <span className="num">B —</span> Visual redaction
                </div>

                <span className="field-label">Targets</span>
                {detectedObjects.length > 0 ? (
                  <div className="object-grid" style={{ marginBottom: 16 }}>
                    {detectedObjects.map(obj => (
                      <label key={obj.label} className="object-chip">
                        <input
                          type="checkbox"
                          className="check"
                          checked={blurObjects.includes(obj.label)}
                          onChange={() => toggleBlurObject(obj.label)}
                        />
                        <span>{obj.label}</span>
                        <span className="count">×{obj.count}</span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="smallcaps" style={{ marginBottom: 16 }}>No objects detected yet.</p>
                )}

                <div style={{ opacity: blurObjects.length ? 1 : 0.4 }}>
                  <span className="field-label">Method</span>
                  <select
                    className="select-input"
                    value={videoMode}
                    onChange={(e) => setVideoMode(e.target.value)}
                    disabled={!blurObjects.length}
                  >
                    <option value="blur">Gaussian blur</option>
                    <option value="pixelate">Mosaic / pixelate</option>
                    <option value="box">Solid black box</option>
                  </select>
                </div>
              </div>
            </div>

            {/* IDENTITY */}
            <div className="config-card" style={{ marginBottom: 0 }}>
              <div className="config-card-title">
                <span className="num">C —</span> Identity-aware face redaction
                <span style={{ marginLeft: 'auto', color: 'var(--bone-faint)', fontWeight: 400 }}>optional</span>
              </div>
              <p className="smallcaps" style={{ marginBottom: 16, lineHeight: 1.5, maxWidth: 540 }}>
                Add reference photos and pick a mode. Per-frame face detection follows movement automatically.
              </p>

              <div style={{ display: 'flex', gap: 24, marginBottom: 18, flexWrap: 'wrap' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="faceMode"
                    className="radio"
                    value="selected"
                    checked={faceMode === 'selected'}
                    onChange={() => setFaceMode('selected')}
                  />
                  <span style={{ fontSize: 13, color: 'var(--bone)' }}>Blur these people</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="faceMode"
                    className="radio"
                    value="others"
                    checked={faceMode === 'others'}
                    onChange={() => setFaceMode('others')}
                  />
                  <span style={{ fontSize: 13, color: 'var(--bone)' }}>Blur everyone else</span>
                </label>
              </div>

              {references.length > 0 && (
                <div className="reference-grid">
                  {references.map(r => (
                    <div key={r.id} className="reference-card">
                      <img src={r.preview} alt="" />
                      <input
                        type="text"
                        placeholder="Name (optional)"
                        value={r.name}
                        onChange={(e) => renameReference(r.id, e.target.value)}
                      />
                      <button className="reference-x" onClick={() => removeReference(r.id)} aria-label="Remove">
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <label className="btn btn-outline btn-sm" style={{ cursor: 'pointer' }}>
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
                <p className="smallcaps" style={{ color: 'var(--ember)', marginTop: 12 }}>
                  No references — every detected face will be blurred (full anonymization).
                </p>
              )}
            </div>

            {showStrength && (
              <div className="config-card" style={{ marginTop: 16, marginBottom: 0 }}>
                <div className="config-card-title">
                  <span className="num">D —</span> Blur strength
                  <span style={{ marginLeft: 'auto', color: 'var(--bone-faint)', fontWeight: 400, fontSize: 12 }}>
                    applies to objects + faces
                  </span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={10}
                  step={1}
                  value={blurStrength}
                  onChange={(e) => setBlurStrength(Number(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--acid)' }}
                />
                <div className="smallcaps" style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--bone-dim)' }}>
                  <span>Light</span><span>Strong</span>
                </div>
              </div>
            )}

            <p className="smallcaps" style={{ color: 'var(--bone-dim)', margin: '16px 0 10px', letterSpacing: '0.04em', lineHeight: 1.5 }}>
              Detection is not perfect — review the redacted output before sharing.
            </p>
            <div className="config-actions">
              <button className="btn btn-ghost" onClick={() => setShowConfig(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCensor}>
                {(references.length > 0 || faceMode === 'others')
                  ? 'Begin face-tracked render →'
                  : 'Begin render →'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* WORKERS */}
      <WorkerProgress taskData={taskData} />

      {/* FACE BLUR STATS */}
      {taskData.face_blur_stats?.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="section-head">
            <span className="section-num">02·c</span>
            <h3 className="section-title" style={{ fontSize: 22 }}>Identity ledger</h3>
            <span className="section-meta">
              Mode · {taskData.face_blur_mode === 'others' ? 'blur others' : 'blur selected'}
            </span>
          </div>
          <div className="fblur-stats">
            {taskData.face_blur_stats.map((s, i) => (
              <div key={i} className="fblur-stat">
                <div className="fblur-name">{s.name}</div>
                <div className="fblur-detail">
                  <strong>{s.matched_frames}</strong> frames matched
                  {s.peak_similarity != null && <> · peak <strong>{s.peak_similarity}</strong></>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* VIDEO */}
      {(originalUrl || censoredUrl) && (
        <div className="video-section">
          <div className="section-head">
            <span className="section-num">03 — Footage</span>
            <h3 className="section-title">
              {hasCensored ? <>Side-by-<em>side</em></> : <>Source <em>preview</em></>}
            </h3>
            <span className="section-meta">{hasCensored ? 'Original / Redacted' : 'Single feed'}</span>
          </div>

          {hasCensored ? (
            <div className="video-comparison">
              <div className="video-pane">
                <span className="video-stamp original">Original</span>
                <video ref={originalVideoRef} controls src={originalUrl} />
              </div>
              <div className="video-pane">
                <span className="video-stamp censored">Redacted</span>
                <video controls src={censoredUrl} />
              </div>
            </div>
          ) : originalUrl && (
            <div className="video-pane" style={{ maxWidth: 960 }}>
              <span className="video-stamp original">Source</span>
              <video ref={originalVideoRef} controls src={originalUrl} />
            </div>
          )}
        </div>
      )}

      {/* ANALYSIS */}
      <div className="section-head">
        <span className="section-num">04 — Findings</span>
        <h3 className="section-title">Analytical <em>read</em></h3>
        <span className="section-meta">Four parallel pipelines</span>
      </div>

      <p className="smallcaps" style={{ color: 'var(--bone-dim)', marginBottom: 20, letterSpacing: '0.04em', lineHeight: 1.5, maxWidth: 640 }}>
        Automated analysis — the models can miss or mislabel content and may report things that are not there. Review before acting on these results.
      </p>

      <div className="dashboard-grid">
        {/* Transcript */}
        <div className="dashboard-card slate transcript-card">
          <div className="card-head">
            <div className="card-head-left">
              <span className="card-num">04·1</span>
              <h3>Speech transcript</h3>
            </div>
            <span className="card-meta">Whisper</span>
          </div>
          <InteractiveTranscript
            chunks={taskData.transcription_metadata?.chunks}
            videoRef={originalVideoRef}
            fallbackText={taskData.transcript}
          />
        </div>

        {/* NER */}
        <div className="dashboard-card slate">
          <div className="card-head">
            <div className="card-head-left">
              <span className="card-num">04·2</span>
              <h3>Named entities</h3>
            </div>
            <span className="card-meta">BERT NER</span>
          </div>
          {taskData.ner_analysis ? (
            taskData.ner_analysis.flagged_entities?.length > 0 ? (
              <div>
                <p className="smallcaps" style={{ color: 'var(--alert)', marginBottom: 12 }}>
                  Sensitive data identified
                </p>
                <div>
                  {taskData.ner_analysis.flagged_entities.map((e, i) => (
                    <span key={i} className="tag-pii">
                      <span className="pii-type">{e.type}</span>
                      <span className="pii-text">{e.text}</span>
                      <span className="pii-score">{Math.round(e.score * 100)}%</span>
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <p className="serif-italic" style={{ fontSize: 18, color: 'var(--ok)' }}>
                Clean — no sensitive PII detected.
              </p>
            )
          ) : (
            <p className="pulse-text smallcaps">Analyzing transcript for PII...</p>
          )}
        </div>

        {/* Audio events */}
        <div className="dashboard-card slate">
          <div className="card-head">
            <div className="card-head-left">
              <span className="card-num">04·3</span>
              <h3>Audio environment</h3>
            </div>
            <span className="card-meta">AST</span>
          </div>
          {taskData.audio_event_analysis ? (
            <div>
              {taskData.audio_event_analysis.events.slice(0, 5).map((ev, i, arr) => (
                <div
                  key={i}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '24px 1fr auto',
                    gap: 14,
                    alignItems: 'baseline',
                    padding: '10px 0',
                    borderBottom: i < arr.length - 1 ? '1px solid var(--rule)' : 'none',
                  }}
                >
                  <span className="mono" style={{ fontSize: 10, color: 'var(--bone-faint)', letterSpacing: '0.14em' }}>
                    0{i + 1}
                  </span>
                  <span className="serif" style={{ fontSize: 16, color: 'var(--bone)', letterSpacing: '-0.01em' }}>
                    {ev.label}
                  </span>
                  <span className="mono tnum" style={{ fontSize: 12, color: 'var(--acid)', fontWeight: 600 }}>
                    {Math.round(ev.score * 100)}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="pulse-text smallcaps">Running spectrogram analysis...</p>
          )}
        </div>

        {/* Vision */}
        <div className="dashboard-card slate">
          <div className="card-head">
            <div className="card-head-left">
              <span className="card-num">04·4</span>
              <h3>Visual objects</h3>
            </div>
            <span className="card-meta">DETR</span>
          </div>
          {taskData.vision_analysis ? (
            taskData.vision_analysis.summary?.length > 0 ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {taskData.vision_analysis.summary.map((obj, i) => (
                  <span key={i} className="tag">
                    {obj.label} <span className="tag-count">×{obj.count}</span>
                  </span>
                ))}
              </div>
            ) : (
              <p className="serif-italic" style={{ fontSize: 18, color: 'var(--bone-2)' }}>
                No high-confidence objects detected.
              </p>
            )
          ) : (
            <p className="pulse-text smallcaps">Extracting and grading frames...</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default AnalysisDashboard;
