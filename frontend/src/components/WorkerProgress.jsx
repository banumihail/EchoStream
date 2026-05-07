import React from 'react';

const WORKERS = [
  { key: 'asr', name: 'Whisper ASR', icon: '🎤' },
  { key: 'ner', name: 'BERT NER', icon: '🧠' },
  { key: 'audio_event', name: 'Audio AST', icon: '🔊' },
  { key: 'vision', name: 'DETR Vision', icon: '👁️' },
  { key: 'censor', name: 'Censor FFmpeg', icon: '🛡️' },
];

const WorkerProgress = ({ taskData }) => {
  if (!taskData) return null;

  return (
    <div className="worker-progress">
      {WORKERS.map(({ key, name, icon }) => {
        const status = taskData[`${key}_status`] || 'pending';
        // Hide censor chip if idle
        if (key === 'censor' && status === 'idle') return null;
        return (
          <div key={key} className={`worker-chip ${status}`}>
            <div className={`worker-dot ${status}`} />
            <div className="worker-info">
              <span className="worker-name">{icon} {name}</span>
              <span className="worker-status-text">
                {status === 'done' ? '✓ Complete' :
                 status === 'processing' ? 'Running...' :
                 status === 'error' ? '✗ Failed' :
                 status === 'pending' ? 'Queued' : status}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default WorkerProgress;
