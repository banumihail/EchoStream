import React, { useEffect, useRef, useState, useMemo } from 'react';

const formatTime = (sec) => {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
};

const PHRASE_END = /[.!?]"?$/;
const PHRASE_PAUSE = /[,;:]$/;
const MAX_WORDS_PER_PHRASE = 14;

// Group word-level chunks into readable "phrase" rows: break on sentence-end
// punctuation, soft-break on commas/semicolons, and hard-cap word count.
const groupIntoPhrases = (words) => {
  const phrases = [];
  let current = [];
  for (const w of words) {
    current.push(w);
    const trimmed = w.text.trim();
    const isHardEnd = PHRASE_END.test(trimmed);
    const isSoftEnd = PHRASE_PAUSE.test(trimmed) && current.length >= 8;
    const isLong = current.length >= MAX_WORDS_PER_PHRASE;
    if (isHardEnd || isSoftEnd || isLong) {
      phrases.push(current);
      current = [];
    }
  }
  if (current.length) phrases.push(current);
  return phrases;
};

const InteractiveTranscript = ({ chunks, videoRef, fallbackText }) => {
  const [activeIndex, setActiveIndex] = useState(-1);
  const [search, setSearch] = useState('');
  const phraseRefs = useRef([]);

  const validChunks = useMemo(
    () => (chunks || []).filter(
      c => c && c.text && Array.isArray(c.timestamp) && c.timestamp[0] !== null && c.timestamp[0] !== undefined
    ),
    [chunks]
  );

  // Detect word-level vs sentence-level data. Word-level chunks average ~1
  // token; sentence-level average many. Old tasks indexed before the
  // return_timestamps="word" switch will still render correctly.
  const isWordLevel = useMemo(() => {
    if (validChunks.length < 4) return false;
    const sample = validChunks.slice(0, 20);
    const avg = sample.reduce((sum, c) => sum + c.text.trim().split(/\s+/).length, 0) / sample.length;
    return avg <= 1.6;
  }, [validChunks]);

  // Build "rows" — each row is a clickable phrase or a sentence-chunk
  const rows = useMemo(() => {
    if (validChunks.length === 0) return [];
    if (!isWordLevel) {
      return validChunks.map((c, i) => ({
        start: c.timestamp[0],
        end: c.timestamp[1],
        words: [{ text: c.text.trim(), start: c.timestamp[0], end: c.timestamp[1], wordIndex: i }],
        text: c.text.trim(),
      }));
    }
    const indexed = validChunks.map((c, i) => ({
      text: c.text,
      start: c.timestamp[0],
      end: c.timestamp[1] ?? c.timestamp[0],
      wordIndex: i,
    }));
    const phrases = groupIntoPhrases(indexed);
    return phrases.map(words => ({
      start: words[0].start,
      end: words[words.length - 1].end,
      words,
      text: words.map(w => w.text).join('').trim(),
    }));
  }, [validChunks, isWordLevel]);

  // Track active word AND active row off the video's currentTime
  useEffect(() => {
    const video = videoRef?.current;
    if (!video || rows.length === 0) return;

    const onTimeUpdate = () => {
      const t = video.currentTime;
      let foundRow = -1;
      let foundWord = -1;
      for (let r = 0; r < rows.length; r++) {
        const row = rows[r];
        if (t < row.start) break;
        const safeEnd = row.end ?? (rows[r + 1]?.start ?? row.start + 5);
        if (t < safeEnd) {
          foundRow = r;
          for (let w = 0; w < row.words.length; w++) {
            const wd = row.words[w];
            const wEnd = wd.end ?? (row.words[w + 1]?.start ?? wd.start + 0.5);
            if (t >= wd.start && t < wEnd) { foundWord = wd.wordIndex; break; }
          }
          break;
        }
      }
      // Highlight the current line, but do NOT auto-scroll the page to follow it.
      setActiveIndex(foundRow);
      setActiveWord(foundWord);
    };

    video.addEventListener('timeupdate', onTimeUpdate);
    return () => video.removeEventListener('timeupdate', onTimeUpdate);
  }, [rows, videoRef]);

  const [activeWord, setActiveWord] = useState(-1);

  const seekTo = (start) => {
    const video = videoRef?.current;
    if (!video || start === null || start === undefined) return;
    video.currentTime = start;
    video.play().catch(() => { /* autoplay blocked — ignore */ });
  };

  const copyAll = async () => {
    const text = rows.length > 0 ? rows.map(r => r.text).join(' ') : (fallbackText || '');
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard blocked */ }
  };

  if (rows.length === 0) {
    return (
      <div className="text-transcript">
        {fallbackText || <span className="pulse-text" style={{ color: 'var(--text-muted)' }}>Waiting for Whisper ASR...</span>}
      </div>
    );
  }

  const q = search.trim().toLowerCase();
  const matchSet = q
    ? new Set(rows.map((r, i) => r.text.toLowerCase().includes(q) ? i : -1).filter(i => i >= 0))
    : null;

  return (
    <div className="interactive-transcript">
      <div className="transcript-toolbar">
        <input
          type="text"
          className="transcript-search"
          placeholder="Search transcript..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button className="transcript-copy" onClick={copyAll} title="Copy full transcript">
          Copy
        </button>
      </div>

      <div className="transcript-chunks">
        {rows.map((row, i) => {
          if (matchSet && !matchSet.has(i)) return null;
          const isActiveRow = i === activeIndex;
          return (
            <div
              key={i}
              ref={(el) => { phraseRefs.current[i] = el; }}
              className={`transcript-chunk${isActiveRow ? ' active' : ''}`}
            >
              <span
                className="transcript-time"
                onClick={() => seekTo(row.start)}
                title={`Jump to ${formatTime(row.start)}`}
              >
                {formatTime(row.start)}
              </span>
              <span className="transcript-text">
                {row.words.map((w) => (
                  <span
                    key={w.wordIndex}
                    className={`transcript-word${w.wordIndex === activeWord ? ' active-word' : ''}`}
                    onClick={() => seekTo(w.start)}
                    title={`${formatTime(w.start)}`}
                  >
                    {w.text}
                  </span>
                ))}
              </span>
            </div>
          );
        })}
        {matchSet && matchSet.size === 0 && (
          <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.9rem' }}>
            No matches for "{search}".
          </p>
        )}
      </div>
    </div>
  );
};

export default InteractiveTranscript;
