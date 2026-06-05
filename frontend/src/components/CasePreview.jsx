import React from 'react';

// Looping "live case" demo visual for the landing hero. Pure CSS motion
// (see .case-preview / .cp-* in index.css); decorative, so aria-hidden.
// Entities mirror the real demo clip for authenticity.
export default function CasePreview() {
  return (
    <div className="case-preview" aria-hidden="true">
      <div className="cp-head">
        <span>CASE · 7BF71D3A</span>
        <span className="cp-redacted">● REDACTED</span>
      </div>
      <div className="cp-frame">
        <div className="cp-face" />
        <div className="cp-reticle" />
        <div className="cp-scan" />
        <div className="cp-rec"><i />REC</div>
        <span className="cp-tag">FACE BLURRED</span>
      </div>
      <div className="cp-ents">
        <div><span className="cp-k">PER</span>[ redacted ]</div>
        <div><span className="cp-k">ORG</span>Microsoft Corporation</div>
        <div><span className="cp-k">LOC</span>Bucharest</div>
      </div>
    </div>
  );
}
