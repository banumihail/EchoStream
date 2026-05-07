import React, { useState } from 'react';
import './index.css';
import Navbar from './components/Navbar';
import UploadDashboard from './components/UploadDashboard';
import AnalysisDashboard from './components/AnalysisDashboard';
import TaskHistory from './components/TaskHistory';

function App() {
  const [currentView, setCurrentView] = useState('upload'); // 'upload' | 'analysis' | 'history'
  const [taskId, setTaskId] = useState(null);

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

  return (
    <div className="app-shell">
      <Navbar currentView={currentView} onNavigate={handleNavigate} />
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
