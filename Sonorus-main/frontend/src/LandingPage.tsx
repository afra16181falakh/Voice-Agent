import React, { useState } from 'react';
import './LandingPage.css';
import SoundOrb from './SoundOrb';
import Tilt from './Tilt';
import useReveal from './useReveal';
import LiveDemoWidget from './LiveDemoWidget';
import FeatureCollage from './FeatureCollage';
import DashboardPreview from './DashboardPreview';

interface LandingPageProps {
  onEnterConsole: (mode?: 'companion' | 'loan_reminder') => void;
  onOpenAdmin: () => void;
}

const NAV_LINKS = [
  { label: 'Home', href: '#top' },
  { label: 'Live demo', href: '#demo' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Modes', href: '#capabilities' },
  { label: 'FAQs', href: '#faqs' },
];

const MODE_COMPARISON = [
  {
    key: 'companion',
    title: 'Sonorus Companion',
    tag: 'YOUR EVERYDAY CONVERSATION',
    icon: 'headset',
    body: 'Inbound, warm, and emotionally aware — a conversation that remembers context and answers real questions, grounded in your own knowledge base.',
    features: [
      'English + Hindi, natural code-switching',
      'Emotion-aware, human-length replies',
      'Answers grounded in your knowledge base',
      'Live on-screen transcript',
      'Hands off to a human when it should',
    ],
  },
  {
    key: 'loan_reminder',
    title: 'Sonorus Outbound',
    tag: 'AUTOMATED OUTREACH',
    icon: 'phone',
    body: 'Sonorus places the call and speaks first — grounded in the real account it\'s calling about, from the opening line to the close.',
    features: [
      'Agent speaks first, no script-reading',
      'Grounded in the specific customer record',
      'Negotiates payment dates, not just states facts',
      'Never pressures — escalates hardship to a human',
      'Full transcript + outcome logged automatically',
    ],
  },
] as const;

const HOW_IT_WORKS = [
  {
    step: '01',
    title: 'Pick the scenario',
    body: 'A warm, personal conversation, a support call grounded in your knowledge base, or an outbound reminder call — each is a distinct mode with its own conversation design.',
  },
  {
    step: '02',
    title: 'The agent listens and responds',
    body: 'Speech is transcribed, reasoned over, and answered in natural, spoken-length sentences — not paragraphs read aloud.',
  },
  {
    step: '03',
    title: 'It escalates when it should',
    body: 'The moment a conversation needs a human — a dispute, real distress, an explicit ask — the agent hands off cleanly instead of guessing.',
  },
  {
    step: '04',
    title: 'You see everything',
    body: 'Live transcript, sentiment, and outcome are visible in real time, and logged for review afterward.',
  },
];

const FAQS = [
  {
    q: 'What languages does it support?',
    a: 'English and Hindi today, including natural code-switching between the two mid-conversation.',
  },
  {
    q: 'Can it call customers, or only take calls?',
    a: 'Both. Inbound sessions work like a normal conversational agent. Outbound sessions — like a payment reminder — have the agent speak first, grounded in the specific customer record it\'s calling about.',
  },
  {
    q: 'Does it just make things up if it doesn\'t know an answer?',
    a: 'No — for support questions, replies are grounded in retrieved content from your knowledge base. If nothing relevant is found, the agent says so rather than guessing.',
  },
  {
    q: 'What happens when a caller is upset or wants a human?',
    a: 'The agent recognizes financial hardship, disputes, and explicit requests for a person, and hands off to a human agent with the conversation context intact — it doesn\'t try to push through those moments on its own.',
  },
];

const TICKER_ITEMS = [
  'Personal Companion', 'Loan Reminder Call', 'English + Hindi', 'Live transcript',
  'Grounded answers', 'Human hand-off', 'Speaks first on outbound calls',
];

function Reveal({ children, className }: { children: React.ReactNode; className?: string }) {
  const { ref, visible } = useReveal<HTMLDivElement>();
  return (
    <div ref={ref} className={`lp-reveal ${visible ? 'lp-reveal-visible' : ''} ${className || ''}`}>
      {children}
    </div>
  );
}

export default function LandingPage({ onEnterConsole, onOpenAdmin }: LandingPageProps) {
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [convoCount, setConvoCount] = useState<number | null>(null);
  React.useEffect(() => {
    fetch('/api/telemetry/overview').then(r => r.json()).then(d => setConvoCount(d.total_conversations)).catch(() => {});
  }, []);

  return (
    <div className="lp-root" id="top">
      {/* Floating decorative 3D shapes + aurora gradient blobs -- pure CSS,
          no image assets, drift slowly behind the content. */}
      <div className="lp-aurora lp-aurora-1" aria-hidden="true" />
      <div className="lp-aurora lp-aurora-2" aria-hidden="true" />
      <div className="lp-aurora lp-aurora-3" aria-hidden="true" />
      <div className="lp-shape lp-shape-cube lp-shape-1" aria-hidden="true"><span /><span /><span /><span /><span /><span /></div>
      <div className="lp-shape lp-shape-cube lp-shape-2" aria-hidden="true"><span /><span /><span /><span /><span /><span /></div>
      <div className="lp-shape lp-shape-ring lp-shape-3" aria-hidden="true" />

      <nav className="lp-nav">
        <div className="lp-nav-inner">
          <div className="lp-logo">
            <span className="lp-logo-mark" aria-hidden="true">
              <span className="lp-logo-bar" />
              <span className="lp-logo-bar" />
              <span className="lp-logo-bar" />
            </span>
            <span className="lp-logo-word">Sonorus</span>
          </div>

          <div className="lp-nav-links">
            {NAV_LINKS.map(link => (
              <a key={link.label} href={link.href} className="lp-nav-link">{link.label}</a>
            ))}
          </div>

          <div className="lp-nav-actions">
            {convoCount !== null && (
              <span className="lp-nav-stat">{convoCount}<em>Conversations</em></span>
            )}
            <button className="lp-btn lp-btn-ghost" onClick={onOpenAdmin}>Admin</button>
            <button className="lp-btn lp-btn-primary" onClick={() => onEnterConsole()}>Talk to Sonorus</button>
          </div>
        </div>
      </nav>

      <header className="lp-hero">
        <div className="lp-hero-orb-wrap" aria-hidden="true">
          <SoundOrb />
        </div>

        <div className="lp-hero-feed" aria-hidden="true">
          <FeatureCollage />
        </div>

        <div className="lp-hero-inner">
          <span className="lp-eyebrow">Voice agent platform</span>
          <h1 className="lp-hero-title">
            Call centers have scripts.<br />
            Customers have patience.<br />
            And you? You got hold music instead.
          </h1>
          <p className="lp-hero-tagline">
            Meet Sonorus — a voice agent that actually talks like a person, remembers
            the conversation, and knows exactly when to bring in a human.
          </p>

          <div className="lp-hero-props">
            <div className="lp-hero-prop">
              <span className="lp-hero-prop-title">Natural.</span>
              <span className="lp-hero-prop-sub">Warm, spoken-length replies — not a script being read aloud.</span>
            </div>
            <div className="lp-hero-prop">
              <span className="lp-hero-prop-title">Fast.</span>
              <span className="lp-hero-prop-sub">A measurable, few-second pipeline — every stage inspectable, nothing a black box.</span>
            </div>
            <div className="lp-hero-prop">
              <span className="lp-hero-prop-title">Accountable.</span>
              <span className="lp-hero-prop-sub">Live transcripts and automatic hand-off to a human when it matters.</span>
            </div>
          </div>

          <div className="lp-hero-ctas">
            <button className="lp-btn lp-btn-primary lp-btn-lg" onClick={() => onEnterConsole()}>
              See Sonorus in action
            </button>
            <a className="lp-btn lp-btn-outline lp-btn-lg" href="#how-it-works">
              How it works
            </a>
          </div>
        </div>

        <div className="lp-hero-glow" aria-hidden="true" />
      </header>

      <section className="lp-section lp-demo" id="demo">
        <div className="lp-section-inner">
          <Reveal>
            <span className="lp-eyebrow">Live demo</span>
            <h2 className="lp-section-title">Two modes. Pick one, hear it live.</h2>
            <p className="lp-section-sub">
              Personal Companion and Loan Reminder Call are genuinely different conversations —
              switch between them below before you connect.
            </p>
          </Reveal>

          <Reveal>
            <LiveDemoWidget onEnterConsole={onEnterConsole} />
          </Reveal>

          <Reveal className="lp-transcript-excerpt-wrap">
            <p className="lp-transcript-excerpt-label">Real transcript excerpt — an actual loan reminder call, unedited</p>
            <Tilt max={3} className="lp-demo-card">
              <div className="lp-demo-card-header">
                <div className="lp-demo-status">
                  <span className="lp-demo-dot" />
                  Live session · Loan reminder call
                </div>
              </div>

              <div className="lp-demo-transcript">
                <div className="lp-demo-line lp-demo-line-agent">
                  <span className="lp-demo-speaker">Sonorus</span>
                  <p>Hi Anjali, this is a call about your Credit Card account — the payment of 3,200 rupees that was due on June 20th hasn't been received yet. Can you tell me a bit about what's going on with that?</p>
                </div>
                <div className="lp-demo-line lp-demo-line-user">
                  <span className="lp-demo-speaker">Customer</span>
                  <p>The thing is, I'm running low on cash right now and I can't afford to pay it.</p>
                </div>
                <div className="lp-demo-line lp-demo-line-agent">
                  <span className="lp-demo-speaker">Sonorus</span>
                  <p>That can be really tough — I can imagine it's stressful to be in a tight spot financially. Would you like to talk to someone who can help explore some options, maybe a payment plan that works better for your situation?</p>
                </div>
                <div className="lp-demo-line lp-demo-line-system">
                  <span className="lp-demo-speaker">System</span>
                  <p>Escalated to human relationship manager — reason: financial hardship, urgency: high</p>
                </div>
              </div>
            </Tilt>
          </Reveal>
        </div>
      </section>

      <section className="lp-section" id="capabilities">
        <div className="lp-section-inner">
          <Reveal>
            <span className="lp-eyebrow">Two distinct modes</span>
            <h2 className="lp-section-title">Not one blurry agent — two purpose-built ones.</h2>
            <p className="lp-section-sub">
              Personal Companion and Loan Reminder Call run on the same voice pipeline but with
              completely different conversation designs, so each one is actually good at its job.
            </p>
          </Reveal>

          <div className="lp-mode-compare">
            {MODE_COMPARISON.map((m, i) => (
              <Reveal key={m.key} className={`lp-reveal-delay-${i}`}>
                <Tilt max={4} className="lp-mode-card">
                  <span className="lp-mode-icon">
                    {m.icon === 'headset' ? (
                      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 13v-1a8 8 0 0 1 16 0v1" /><rect x="2.5" y="13" width="5" height="7" rx="2" /><rect x="16.5" y="13" width="5" height="7" rx="2" /><path d="M20 20v1a3 3 0 0 1-3 3h-3" /></svg>
                    ) : (
                      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M15 3h6v6M21 3l-7 7" /><path d="M4 5c0 8.3 6.7 15 15 15l1-4-5-2-1.5 1.5A11.4 11.4 0 0 1 9 11l1.5-1.5-2-5-4 .5z" /></svg>
                    )}
                  </span>
                  <span className="lp-mode-tag">{m.tag}</span>
                  <h3>{m.title}</h3>
                  <p className="lp-mode-body">{m.body}</p>
                  <ul className="lp-mode-features">
                    {m.features.map(f => (
                      <li key={f}><span className="lp-mode-check">✓</span>{f}</li>
                    ))}
                  </ul>
                  <button
                    className="lp-btn lp-btn-outline lp-btn-sm"
                    onClick={() => onEnterConsole(m.key as 'companion' | 'loan_reminder')}
                  >
                    Try {m.title}
                  </button>
                </Tilt>
              </Reveal>
            ))}
          </div>

          <Reveal>
            <p className="lp-mode-connector">
              Same voice engine underneath — different conversation design, different goal, one platform.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="lp-section lp-how" id="how-it-works">
        <div className="lp-section-inner">
          <Reveal>
            <span className="lp-eyebrow">How it works</span>
            <h2 className="lp-section-title">From first hello to clean hand-off.</h2>
          </Reveal>

          <div className="lp-how-grid">
            {HOW_IT_WORKS.map((step, i) => (
              <Reveal key={step.step} className={`lp-reveal-delay-${i % 4}`}>
                <div className="lp-how-card">
                  <span className="lp-how-step">{step.step}</span>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal className="lp-dash-wrap">
            <p className="lp-dash-caption">This is the real admin telemetry — live, not a mockup with invented numbers.</p>
            <DashboardPreview />
          </Reveal>
        </div>
      </section>

      <section className="lp-section lp-faqs" id="faqs">
        <div className="lp-section-inner lp-faqs-inner">
          <Reveal>
            <span className="lp-eyebrow">FAQs</span>
            <h2 className="lp-section-title">Good to know.</h2>
          </Reveal>

          <Reveal>
            <div className="lp-faq-list">
              {FAQS.map((item, i) => (
                <div className={`lp-faq-item ${openFaq === i ? 'lp-faq-open' : ''}`} key={item.q}>
                  <button className="lp-faq-question" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                    <span>{item.q}</span>
                    <span className="lp-faq-toggle" aria-hidden="true">{openFaq === i ? '−' : '+'}</span>
                  </button>
                  {openFaq === i && <p className="lp-faq-answer">{item.a}</p>}
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      <section className="lp-ticker-section">
        <div className="lp-ticker-track">
          {[...TICKER_ITEMS, ...TICKER_ITEMS].map((item, i) => (
            <span className="lp-ticker-item" key={i}>{item}</span>
          ))}
        </div>
      </section>

      <section className="lp-cta-band">
        <div className="lp-section-inner lp-cta-inner">
          <Reveal>
            <h2>Ready to hear it for yourself?</h2>
            <p>No setup, no script — just start talking.</p>
            <button className="lp-btn lp-btn-primary lp-btn-lg" onClick={() => onEnterConsole()}>
              Talk to Sonorus
            </button>
          </Reveal>
        </div>
      </section>

      <footer className="lp-footer">
        <div className="lp-section-inner lp-footer-inner">
          <div className="lp-logo">
            <span className="lp-logo-mark" aria-hidden="true">
              <span className="lp-logo-bar" />
              <span className="lp-logo-bar" />
              <span className="lp-logo-bar" />
            </span>
            <span className="lp-logo-word">Sonorus</span>
          </div>
          <p className="lp-footer-note">Sonorus Voice Agent Platform</p>
        </div>
      </footer>
    </div>
  );
}
