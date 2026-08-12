import React, { useState } from 'react';

interface LiveDemoWidgetProps {
  onEnterConsole: (mode: 'companion' | 'loan_reminder') => void;
}

interface OrbitIcon {
  label: string;
  icon: React.ReactNode;
}

const ICONS = {
  memory: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" /></svg>
  ),
  heart: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 21s-7-4.35-9.5-8.5C.8 8.7 2.6 5 6.2 5c2 0 3.3 1 4.8 2.7C12.5 6 13.8 5 15.8 5c3.6 0 5.4 3.7 3.7 7.5C19 16.65 12 21 12 21z" /></svg>
  ),
  globe: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z" /></svg>
  ),
  doc: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 2h9l5 5v15H6z" /><path d="M14 2v6h6M9 13h6M9 17h6" /></svg>
  ),
  handoff: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="8" cy="8" r="3.2" /><path d="M2 21v-1.4A5.6 5.6 0 0 1 7.6 14h1a5.6 5.6 0 0 1 4.4 2.1M15 8l3 3-3 3M18 11h-6" /></svg>
  ),
  phoneOut: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M15 3h6v6M21 3l-7 7" /><path d="M4 5c0 8.3 6.7 15 15 15l1-4-5-2-1.5 1.5A11.4 11.4 0 0 1 9 11l1.5-1.5-2-5-4 .5z" /></svg>
  ),
  calendar: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4.5" width="18" height="16" rx="2" /><path d="M3 9.5h18M8 2.5v4M16 2.5v4" /></svg>
  ),
  shield: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 2 4 5v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5z" /></svg>
  ),
  db: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></svg>
  ),
};

const MODES: Record<'companion' | 'loan_reminder', {
  label: string;
  tagline: string;
  prompt: string;
  icons: OrbitIcon[];
}> = {
  companion: {
    label: 'Personal Companion',
    tagline: 'Sonorus is listening. Say hello, or say what\'s on your mind.',
    prompt: 'Say something to Sonorus',
    icons: [
      { label: 'Memory', icon: ICONS.memory },
      { label: 'Emotion-aware', icon: ICONS.heart },
      { label: 'Bilingual', icon: ICONS.globe },
      { label: 'Live transcript', icon: ICONS.doc },
      { label: 'Human hand-off', icon: ICONS.handoff },
    ],
  },
  loan_reminder: {
    label: 'Loan Reminder Call',
    tagline: 'Sonorus calls first — grounded in the real account it\'s calling about.',
    prompt: 'Sonorus speaks first on this call',
    icons: [
      { label: 'Speaks first', icon: ICONS.phoneOut },
      { label: 'Payment plans', icon: ICONS.calendar },
      { label: 'Hardship-aware', icon: ICONS.shield },
      { label: 'Human hand-off', icon: ICONS.handoff },
      { label: 'Real account data', icon: ICONS.db },
    ],
  },
};

export default function LiveDemoWidget({ onEnterConsole }: LiveDemoWidgetProps) {
  const [activeMode, setActiveMode] = useState<'companion' | 'loan_reminder'>('companion');
  const mode = MODES[activeMode];
  const n = mode.icons.length;

  return (
    <div className="lp-widget">
      <div className="lp-widget-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeMode === 'companion'}
          className={`lp-widget-tab ${activeMode === 'companion' ? 'lp-widget-tab-active' : ''}`}
          onClick={() => setActiveMode('companion')}
        >
          Personal Companion
          <span className="lp-widget-tab-dot" />
        </button>
        <button
          role="tab"
          aria-selected={activeMode === 'loan_reminder'}
          className={`lp-widget-tab ${activeMode === 'loan_reminder' ? 'lp-widget-tab-active' : ''}`}
          onClick={() => setActiveMode('loan_reminder')}
        >
          Loan Reminder Call
          <span className="lp-widget-tab-dot" />
        </button>
      </div>

      <div className="lp-widget-body">
        <div className="lp-orbit-wrap">
          <div className="lp-orbit-ring" />
          {mode.icons.map((item, i) => {
            const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
            const radius = 46; // percent of container
            const x = 50 + radius * Math.cos(angle);
            const y = 50 + radius * Math.sin(angle);
            return (
              <div key={item.label} className="lp-orbit-item" style={{ left: `${x}%`, top: `${y}%` }}>
                <span className="lp-orbit-icon">{item.icon}</span>
                <span className="lp-orbit-label">{item.label}</span>
              </div>
            );
          })}

          <button className="lp-orb-btn" onClick={() => onEnterConsole(activeMode)}>
            <span className="lp-orb-core" />
            <span className="lp-orb-accent" />
            <span className="lp-orb-badge">
              <span className="lp-orb-badge-check">✓</span>
              {n} capabilities · {mode.label}
            </span>
          </button>
          <button className="lp-orbit-caption" onClick={() => onEnterConsole(activeMode)}>
            Tap to talk to Sonorus
          </button>
        </div>

        <div className="lp-convo-card">
          <div className="lp-convo-header">
            <div>
              <span className="lp-convo-eyebrow">Connected</span>
              <h3>Conversation</h3>
            </div>
            <span className="lp-convo-dot" />
          </div>

          <div className="lp-convo-body">
            <div className="lp-convo-mic">
              <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor"><rect x="9" y="2" width="6" height="11" rx="3" /><path d="M19 10c0 3.5-2.5 6.4-5.8 6.9V20h2.3c.6 0 1 .4 1 1s-.4 1-1 1H8.5c-.6 0-1-.4-1-1s.4-1 1-1h2.3v-3.1C7.5 16.4 5 13.5 5 10c0-.6.4-1 1-1s1 .4 1 1c0 2.8 2.2 5 5 5s5-2.2 5-5c0-.6.4-1 1-1s1 .4 1 1z" /></svg>
            </div>
            <h4>{mode.prompt}</h4>
            <p>{mode.tagline}</p>

            <div className="lp-convo-wave">
              <span /><span /><span /><span /><span />
            </div>

            <button className="lp-btn lp-btn-primary lp-btn-sm" onClick={() => onEnterConsole(activeMode)}>
              Talk to Sonorus now
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
