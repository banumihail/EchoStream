import React, { useEffect, useState } from 'react';

const formatClock = (d) => {
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

const Navbar = ({ currentView, onNavigate, username, onLogout }) => {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <nav className="masthead">
      <div className="masthead-inner">
        <button
          className="masthead-brand"
          onClick={() => onNavigate('upload')}
          aria-label="EchoStream home"
        >
          <span className="wordmark">Echo<em>Stream</em></span>
          <span className="stamp">Forensic / v0.1</span>
        </button>

        <div className="ticker" aria-hidden="true">
          <span className="ticker-dot" />
          <span>Console Live</span>
          <span className="ticker-sep">//</span>
          <span className="tnum">{formatClock(now)}</span>
          <span className="ticker-sep">//</span>
          <span>Whisper · BERT · AST · DETR · FFmpeg</span>
          <span className="ticker-sep">//</span>
          <span>Identity-Aware Redaction Online</span>
        </div>

        <div className="masthead-nav">
          <button
            className={`nav-link ${currentView === 'upload' ? 'active' : ''}`}
            onClick={() => onNavigate('upload')}
          >
            Intake
          </button>
          <button
            className={`nav-link ${currentView === 'history' ? 'active' : ''}`}
            onClick={() => onNavigate('history')}
          >
            Dossier
          </button>
          {username && (
            <>
              <span className="nav-user" title="Signed in as">{username}</span>
              <button className="nav-link" onClick={onLogout} title="Sign out">
                Sign out
              </button>
            </>
          )}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
