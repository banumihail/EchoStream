import React, { useState } from 'react';
import './index.css';
import UploadDashboard from './components/UploadDashboard';
import AnalysisDashboard from './components/AnalysisDashboard';

function App() {
  const [taskId, setTaskId] = useState(null);

  return (
    <div className="app-container">
      <header className="header">
        <h1><span className="gradient-text">EchoStream</span> AI</h1>
        <p>Advanced Video Content Moderation & Analysis</p>
      </header>

      <main>
        {!taskId ? (
          <UploadDashboard onUploadSuccess={(id) => setTaskId(id)} />
        ) : (
          <AnalysisDashboard taskId={taskId} onReset={() => setTaskId(null)} />
        )}
      </main>
    </div>
  );
}

export default App;
