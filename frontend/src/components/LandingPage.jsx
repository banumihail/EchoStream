import React from 'react';
import Icon from './Icon';

const TILES = [
  { icon: 'transcript', title: 'Word-level transcript', body: 'Clickable, searchable, time-synced to the video.' },
  { icon: 'audio', title: 'Audio redaction', body: 'Beep, muffle or silence sensitive speech.' },
  { icon: 'identity', title: 'Identity-aware blur', body: 'Blur one person across frames — or everyone else.' },
  { icon: 'pii', title: 'PII detection', body: "Names, places, orgs flagged the moment they're spoken." },
];

// Equalizer bars for the ambient layer — count is decorative.
const EQ_BARS = Array.from({ length: 26 });

export default function LandingPage({ onSignIn, onGetStarted }) {
  return (
    <div className="landing fade-in">
      <div className="landing-ambient" aria-hidden="true">
        <div className="landing-ambient-glow" />
        <div className="landing-ambient-scan" />
        <div className="landing-eq">
          {EQ_BARS.map((_, i) => (
            <span
              key={i}
              style={{
                animationDelay: `${(i % 7) * 0.18 + (i % 3) * 0.08}s`,
                animationDuration: `${2.8 + (i % 5) * 0.45}s`,
              }}
            />
          ))}
        </div>
      </div>

      <nav className="landing-nav">
        <span className="wordmark">Echo<em>Stream</em></span>
        <div className="landing-nav-actions">
          <button className="btn btn-ghost" onClick={onSignIn}>Sign in</button>
          <button className="btn btn-primary" onClick={onGetStarted}>Get started</button>
        </div>
      </nav>

      <header className="landing-hero">
        <div className="landing-hero-text">
          <div className="landing-eyebrow lm-r lm-d1">
            Upload · Detect · Redact<span className="lm-cursor" />
          </div>
          <h1 className="landing-title lm-r lm-d2">Privacy redaction, done by the pipeline — not by hand.</h1>
          <p className="landing-sub lm-r lm-d3">
            Five models analyse every clip in parallel, then an active-censorship stage physically
            blurs faces and mutes sensitive audio.
          </p>
        </div>
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
