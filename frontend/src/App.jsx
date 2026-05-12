import React, { useState, useEffect } from 'react';
import './index.css';
import Navbar from './components/Navbar';
import UploadDashboard from './components/UploadDashboard';
import AnalysisDashboard from './components/AnalysisDashboard';
import TaskHistory from './components/TaskHistory';
import Login from './components/Login';
import { isTokenLikelyValid, getUsername, clearSession } from './lib/auth';

function App() {
  const [authedUser, setAuthedUser] = useState(() => (isTokenLikelyValid() ? getUsername() : null));
  const [currentView, setCurrentView] = useState('upload'); // 'upload' | 'analysis' | 'history'
  const [taskId, setTaskId] = useState(null);

  useEffect(() => {
    const onExpired = () => setAuthedUser(null);
    window.addEventListener('echostream:auth-expired', onExpired);
    return () => window.removeEventListener('echostream:auth-expired', onExpired);
  }, []);

  const handleLogout = () => {
    clearSession();
    setAuthedUser(null);
    setTaskId(null);
    setCurrentView('upload');
  };

  const handleUploadSuccess = (id) => {
    setTaskId(id);
    setCurrentView('analysis');
  };

  const handleSelectTask = (id) => {
    setTaskId(id);
    setCurrentView('analysis');
  };

  const handleReset = () => {
    setTaskId(null);
    setCurrentView('upload');
  };

  const handleNavigate = (view) => {
    if (view === 'upload') {
      setTaskId(null);
    }
    setCurrentView(view);
  };

  if (!authedUser) {
    return (
      <div className="app-shell">
        <div className="page-content">
          <Login onLoggedIn={(u) => setAuthedUser(u)} />
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Navbar currentView={currentView} onNavigate={handleNavigate} username={authedUser} onLogout={handleLogout} />
      <div className="page-content">
        {currentView === 'upload' && (
          <UploadDashboard onUploadSuccess={handleUploadSuccess} />
        )}
        {currentView === 'analysis' && taskId && (
          <AnalysisDashboard taskId={taskId} onReset={handleReset} />
        )}
        {currentView === 'history' && (
          <TaskHistory onSelectTask={handleSelectTask} />
        )}
      </div>
    </div>
  );
}

export default App;
