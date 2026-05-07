import React from 'react';

const Navbar = ({ currentView, onNavigate }) => {
  return (
    <nav className="navbar">
      <a className="navbar-brand" href="#" onClick={(e) => { e.preventDefault(); onNavigate('upload'); }}>
        <span className="logo-icon">🔊</span>
        <span className="gradient-text">EchoStream</span>
        <span style={{ fontWeight: 400, fontSize: '0.85rem', color: 'var(--text-muted)' }}>AI</span>
      </a>
      <div className="navbar-links">
        <button
          className={`nav-link ${currentView === 'upload' ? 'active' : ''}`}
          onClick={() => onNavigate('upload')}
        >
          Upload
        </button>
        <button
          className={`nav-link ${currentView === 'history' ? 'active' : ''}`}
          onClick={() => onNavigate('history')}
        >
          History
        </button>
      </div>
    </nav>
  );
};

export default Navbar;
