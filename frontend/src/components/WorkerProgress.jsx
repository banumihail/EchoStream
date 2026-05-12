import React from 'react';

const WORKERS = [
  { key: 'asr',         name: 'Whisper ASR',     short: 'Speech' },
  { key: 'ner',         name: 'BERT NER',        short: 'Entities' },
  { key: 'audio_event', name: 'AST Audio',       short: 'Soundscape' },
  { key: 'vision',      name: 'DETR Vision',     short: 'Objects' },
  { key: 'censor',      name: 'FFmpeg Redact',   short: 'Render' },
];

const STATUS_LABEL = {
  done:       'Complete',
  processing: 'Running',
  error:      'Failed',
  pending:    'Queued',
  idle:       'Idle',
};

const STATUS_PROGRESS = {
  done:       100,
  processing: 65,
  error:      100,
  pending:    0,
  idle:       0,
};

const WorkerProgress = ({ taskData }) => {
  if (!taskData) return null;

  return (
    <div className="worker-rail">
      {WORKERS.map(({ key, name, short }, idx) => {
        const status = taskData[`${key}_status`] || 'pending';
        if (key === 'censor' && status === 'idle') return null;

        const label = STATUS_LABEL[status] || status;
        const progress = STATUS_PROGRESS[status] ?? 0;

        return (
          <div key={key} className={`worker-cell ${status}`}>
            <span className="worker-idx">PID · 0{idx + 1}</span>
            <span className="worker-label">{name}</span>
            <div className="worker-status">
              <span className={`worker-dot ${status}`} />
              <span>{short} — {label}</span>
            </div>
            {progress > 0 && status !== 'error' && (
              <span
                className="worker-bar"
                style={{
                  width: `${progress}%`,
                  background: status === 'done' ? 'var(--acid)' : 'var(--cool)',
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
};

export default WorkerProgress;
