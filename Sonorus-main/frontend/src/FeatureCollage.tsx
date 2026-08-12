import React from 'react';

/**
 * Floating overlapping "product snapshot" cards -- the bento-collage style
 * asklena.ai uses on its how-it-works page. Every card here shows a real
 * Sonorus event (an actual transcript line, an actual escalation payload,
 * the real STT->LLM->TTS pipeline), not invented content, styled as small
 * floating notification cards with independent drift animation for
 * liveliness.
 */
export default function FeatureCollage() {
  return (
    <div className="lp-collage">
      <div className="lp-collage-card lp-collage-transcript lp-float-a">
        <div className="lp-collage-card-head">
          <span className="lp-collage-dot lp-collage-dot-green" />
          Live Transcript · Sent
        </div>
        <p className="lp-collage-card-title">Rohan Mehta · Personal Loan reminder</p>
        <p className="lp-collage-card-body">"Probably around the fifteenth — I'll try to get it sorted by then."</p>
      </div>

      <div className="lp-collage-card lp-collage-call lp-float-b">
        <div className="lp-collage-card-head">
          <span className="lp-collage-dot lp-collage-dot-blue" />
          Sonorus · Anjali Rao
          <span className="lp-collage-live">LIVE</span>
        </div>
        <p className="lp-collage-card-body">"That can be really tough — would you like to talk to someone about a payment plan?"</p>
        <div className="lp-collage-wave">
          <span /><span /><span /><span /><span /><span /><span />
        </div>
        <div className="lp-collage-chips">
          <span>STT ✓</span>
          <span>KB grounded</span>
          <span>0.58s</span>
        </div>
      </div>

      <div className="lp-collage-card lp-collage-escalate lp-float-c">
        <div className="lp-collage-card-head">
          <span className="lp-collage-dot lp-collage-dot-amber" />
          Escalation → Human Agent
        </div>
        <p className="lp-collage-card-title">reason: financial hardship</p>
        <p className="lp-collage-card-body">urgency: high · handed off with full context</p>
      </div>

      <div className="lp-collage-card lp-collage-pipeline lp-float-d">
        <div className="lp-collage-card-head">
          <span className="lp-collage-dot lp-collage-dot-blue" />
          Voice pipeline
        </div>
        <div className="lp-collage-pipeline-row">
          <span className="lp-collage-node">STT</span>
          <span className="lp-collage-edge" />
          <span className="lp-collage-node">LLM</span>
          <span className="lp-collage-edge" />
          <span className="lp-collage-node">TTS</span>
        </div>
        <p className="lp-collage-card-body">Each stage independently measurable — no single black box.</p>
      </div>

      <div className="lp-collage-card lp-collage-lang lp-float-e">
        <div className="lp-collage-card-head">
          <span className="lp-collage-dot lp-collage-dot-green" />
          Language
        </div>
        <p className="lp-collage-card-title">Hindi detected — switched live</p>
      </div>
    </div>
  );
}
