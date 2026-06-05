import React from 'react';
import Icon from './Icon';

const TILES = [
  { icon: 'transcript', title: 'Word-level transcript', body: 'Clickable, searchable, time-synced to the video.' },
  { icon: 'audio', title: 'Audio redaction', body: 'Beep, muffle or silence sensitive speech.' },
  { icon: 'identity', title: 'Identity-aware blur', body: 'Blur one person across frames — or everyone else.' },
  { icon: 'pii', title: 'PII detection', body: "Names, places, orgs flagged the moment they're spoken." },
];

export default function LandingPage({ onSignIn, onGetStarted }) {
  return (
    <div className="landing fade-in">
      <nav className="landing-nav">
        <span className="wordmark">EchoStream</span>
        <div className="landing-nav-actions">
          <button className="btn btn-ghost" onClick={onSignIn}>Sign in</button>
          <button className="btn btn-primary" onClick={onGetStarted}>Get started</button>
        </div>
      </nav>

      <header className="landing-hero">
        <div className="landing-eyebrow">Upload · Detect · Redact</div>
        <h1 className="landing-title">Privacy redaction, done by the pipeline — not by hand.</h1>
        <p className="landing-sub">
          Five models analyse every clip in parallel, then an active-censorship stage physically
          blurs faces and mutes sensitive audio.
        </p>
      </header>

      <section className="landing-tiles">
        {TILES.map(t => (
          <div className="landing-tile" key={t.icon}>
            <Icon name={t.icon} size={22} className="tile-ic" />
            <h4>{t.title}</h4>
            <p>{t.body}</p>
          </div>
        ))}
      </section>

      <div className="landing-models">WHISPER · BERT · DETR · AST · YuNet+SFace</div>
    </div>
  );
}
