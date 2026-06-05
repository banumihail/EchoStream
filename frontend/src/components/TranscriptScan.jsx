import React from 'react';

// Looping "live transcript redaction" visual for the landing hero: sensitive
// entities get black redaction bars wiped over them in sequence, mirroring the
// real demo clip. Pure CSS motion (.tscan / .redact in index.css); decorative,
// so aria-hidden.
export default function TranscriptScan() {
  return (
    <div className="tscan" aria-hidden="true">
      <div className="tscan-head">
        <span>TRANSCRIPT · WHISPER</span>
        <span className="tscan-flag">3 PII</span>
      </div>
      <div className="tscan-body">
        <div className="tscan-scan" />
        <p className="tscan-line">&ldquo;Hello, my name is <span className="redact r1">Kamil Hibibhibab</span>,</p>
        <p className="tscan-line">I&rsquo;m calling from <span className="redact r2">Microsoft Corporation</span>.</p>
        <p className="tscan-line">Wire the gift-card PINs to</p>
        <p className="tscan-line"><span className="redact r3">Bucharest</span> before noon.&rdquo;</p>
      </div>
      <div className="tscan-foot">
        <i />redacting sensitive entities&hellip;
      </div>
    </div>
  );
}
