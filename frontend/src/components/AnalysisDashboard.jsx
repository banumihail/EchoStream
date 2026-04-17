import React, { useState, useEffect } from 'react';

const AnalysisDashboard = ({ taskId, onReset }) => {
  const [taskData, setTaskData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Poll API every 3 seconds
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`http://localhost:8000/tasks/${taskId}`);
        if (!response.ok) throw new Error("Could not fetch task data");
        const data = await response.json();
        setTaskData(data);
        
        // Optionally clear interval if completely done
        // if (data.status === 'completed' && data.vision_analysis && data.audio_event_analysis) clearInterval(interval);
      } catch (err) {
        console.error(err);
        setError("Connection to API lost.");
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [taskId]);

  if (!taskData) {
    return (
      <div className="glass-panel" style={{ textAlign: 'center', padding: '60px' }}>
        <h2 className="pulse-text">Syncing with AI Engines...</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '10px' }}>Task ID: {taskId}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="glass-panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ marginBottom: '8px' }}>File: <span style={{ color: 'var(--accent-secondary)' }}>{taskData.filename}</span></h2>
          <span className={`badge ${taskData.status}`}>{taskData.status.toUpperCase()}</span>
          {taskData.has_pii && <span style={{ marginLeft: '10px' }} className="badge tag-danger">PII DETECTED</span>}
        </div>
        <button className="btn-primary" onClick={onReset}>Analyze New Video</button>
      </div>

      <div className="dashboard-grid">
        
        {/* Transcription Panel */}
        <div className="dashboard-card glass-panel">
          <h3>Speech Transcript (Whisper)</h3>
          {taskData.transcript ? (
            <div className="text-transcript">
              {taskData.transcript}
            </div>
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)' }}>Waiting for speech recognition...</p>
          )}
        </div>

        {/* NER PII Panel */}
        <div className="dashboard-card glass-panel">
          <h3>Detected Entities (BERT)</h3>
          {taskData.ner_analysis ? (
            <div>
              {taskData.ner_analysis.flagged_entities.length > 0 ? (
                <div>
                  <p style={{ color: 'var(--danger)', marginBottom: '12px' }}>Sensitive Data Identified:</p>
                  {taskData.ner_analysis.flagged_entities.map((entity, idx) => (
                    <span key={idx} className="tag tag-danger">
                      {entity.type}: {entity.text} ({Math.round(entity.score * 100)}%)
                    </span>
                  ))}
                </div>
              ) : (
                <p style={{ color: 'var(--success)' }}>✅ No sensitive PII detected in speech.</p>
              )}
            </div>
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)' }}>Analyzing transcript for PII...</p>
          )}
        </div>

        {/* Audio Events Panel */}
        <div className="dashboard-card glass-panel">
          <h3>Audio Environment (AST)</h3>
          {taskData.audio_event_analysis ? (
            <div>
              <p style={{ marginBottom: '12px' }}>Acoustic Events Detected:</p>
              {taskData.audio_event_analysis.events.slice(0, 5).map((ev, idx) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', borderBottom: '1px solid var(--glass-border)', paddingBottom: '4px' }}>
                  <span>{ev.label}</span>
                  <span style={{ color: 'var(--accent-primary)' }}>{Math.round(ev.score * 100)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)' }}>Running spectogram analysis...</p>
          )}
        </div>

        {/* Vision Panel */}
        <div className="dashboard-card glass-panel">
          <h3>Visual Objects (DETR / ResNet)</h3>
          {taskData.vision_analysis ? (
            <div>
              <p style={{ marginBottom: '12px' }}>Objects tracked over time:</p>
              {taskData.vision_analysis.summary.length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                  {taskData.vision_analysis.summary.map((obj, idx) => (
                    <span key={idx} className="tag">
                      {obj.label} <span style={{ opacity: 0.6 }}>x{obj.count}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <p>No high-confidence objects detected.</p>
              )}
            </div>
          ) : (
            <p className="pulse-text" style={{ color: 'var(--text-muted)' }}>Extracting and grading frames...</p>
          )}
        </div>

      </div>
    </div>
  );
};

export default AnalysisDashboard;
