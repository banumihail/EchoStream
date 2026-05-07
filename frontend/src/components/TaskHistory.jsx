import React, { useState, useEffect } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const TaskHistory = ({ onSelectTask }) => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchTasks = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/tasks`);
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
    e.stopPropagation(); // Prevent opening the task
    if (!window.confirm('Are you sure you want to delete this task and its files?')) return;
    
    try {
      const res = await fetch(`${API_URL}/tasks/${taskId}`, { method: 'DELETE' });
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
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return dateStr; }
  };

  return (
    <div className="fade-in">
      <div className="history-header">
        <h2><span className="gradient-text">Task History</span></h2>
        <button className="btn btn-outline btn-sm" onClick={fetchTasks}>
          🔄 Refresh
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠️</span>
          <p>{error}</p>
          <button className="btn btn-outline btn-sm" onClick={fetchTasks}>Retry</button>
        </div>
      )}

      {loading ? (
        <div className="empty-state">
          <div className="spinner" style={{ margin: '0 auto 16px' }} />
          <p>Loading tasks...</p>
        </div>
      ) : tasks.length === 0 ? (
        <div className="glass-panel empty-state">
          <div className="empty-icon">📭</div>
          <h3 style={{ marginBottom: 8 }}>No tasks yet</h3>
          <p>Upload a video to get started with AI analysis.</p>
        </div>
      ) : (
        <div className="task-list">
          {tasks.map((task) => (
            <div
              key={task.task_id}
              className="glass-panel task-row"
              onClick={() => onSelectTask(task.task_id)}
            >
              <div className="task-row-name">
                🎬 {task.filename || 'Untitled'}
              </div>
              <span className={`badge ${task.status}`}>
                {task.status?.toUpperCase()}
              </span>
              <span className="task-row-date">
                {formatDate(task.updated_at)}
              </span>
              <button 
                className="btn btn-outline btn-sm" 
                style={{ marginLeft: '12px', padding: '4px 8px', color: '#ff4d4f', borderColor: 'transparent' }}
                onClick={(e) => handleDelete(e, task.task_id)}
                title="Delete Task"
              >
                🗑️
              </button>
              <span style={{ color: 'var(--text-dim)', fontSize: '0.9rem', marginLeft: '12px' }}>→</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TaskHistory;
