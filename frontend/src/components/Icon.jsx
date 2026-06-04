import React from 'react';

// Bespoke evidence-room icon set. Stroke uses currentColor so icons take
// the surrounding text colour (bone, or acid where the parent sets it).
const PATHS = {
  // capability icons (from the approved landing mockup)
  transcript: <path d="M4 7h16M4 12h10M4 17h13" />,
  audio: <><path d="M12 3v18" /><path d="M7 8v8M17 8v8M3 11v2M21 11v2" /></>,
  identity: <><circle cx="9" cy="9" r="5" /><path d="M9 14c-3 0-6 2-6 5M14 12l6 6M20 12l-6 6" /></>,
  pii: <><path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z" /><path d="M9 12l2 2 4-4" /></>,
  // UI glyphs
  alert: <><path d="M12 3 2 20h20L12 3z" /><path d="M12 10v4" /><path d="M12 17.5h.01" /></>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5 21 21" /></>,
  upload: <><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 18v2h16v-2" /></>,
};

export default function Icon({ name, size = 20, className = '', style = {}, strokeWidth = 1.5 }) {
  const path = PATHS[name];
  if (!path) return null;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      {path}
    </svg>
  );
}
