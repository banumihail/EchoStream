import React, { useState, useEffect } from 'react';
import { authFetch } from '../lib/auth';

const TaskHistory = ({ onSelectTask }) => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchTasks = async () => {
    try {
      setLoading(true);
      const res = await authFetch('/tasks');
      if (!res.ok) throw new Error('Failed to fetch tasks');
      const data = await res.json();
      setTasks(data);
      setError(null);
    } catch (err) {
      setError('Could not load task history. Is the API running?');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e, taskId) => {
    e.stopPropagation();
    if (!window.confirm('Delete this case file and all of its assets?')) return;
    try {
      const res = await authFetch(`/tasks/${taskId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete task');
      setTasks(prev => prev.filter(t => t.task_id !== taskId));
    } catch (err) {
      alert(err.message);
    }
  };

  useEffect(() => { fetchTasks(); }, []);

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const d = new Date(dateStr);
      const date = d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' }).toUpperCase();
      const time = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
      return `${date} · ${time}`;
    } catch { return dateStr; }
  };

  return (
    <div className="fade-in">
      <div className="section-head">
        <span className="section-num">02 — Dossier</span>
        <h2 className="section-title">
          Case <em>archive</em>
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="section-meta">
            {loading ? '— loading' : `${tasks.length} ${tasks.length === 1 ? 'case' : 'cases'}`}
          </span>
          <button className="btn btn-outline btn-sm" onClick={fetchTasks}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-banner-tag">Net</span>
          <p>{error}</p>
          <button className="btn btn-ghost btn-sm" onClick={fetchTasks}>Retry</button>
        </div>
      )}

      {loading ? (
        <div className="empty-state">
          <div className="spinner spinner-lg" style={{ margin: '0 auto 16px' }} />
          <p>Pulling archive</p>
        </div>
      ) : tasks.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-num">00</div>
          <h3>Empty archive</h3>
          <p>Submit a video at intake to open the first case</p>
        </div>
      ) : (
        <div className="dossier-list">
          {tasks.map((task, i) => (
            <div
              key={task.task_id}
              className="dossier-row"
              onClick={() => onSelectTask(task.task_id)}
            >
              <span className="dossier-idx">
                {String(tasks.length - i).padStart(3, '0')}
              </span>
              <span className="dossier-name">{task.filename || 'Untitled'}</span>
              <span className={`badge ${task.status}`}>
                {task.status}
              </span>
              <span className="dossier-date">{formatDate(task.updated_at)}</span>
              <button
                className="dossier-delete"
                onClick={(e) => handleDelete(e, task.task_id)}
                title="Delete case"
                aria-label="Delete case"
              >
                ×
              </button>
              <span className="dossier-arrow">→</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TaskHistory;
