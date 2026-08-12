import React, { useEffect, useState } from 'react';
import { API_BASE } from './config';

const API = `${API_BASE}/api/telemetry`;

const SECTIONS = [
  'Overview', 'Live Sessions', 'Wellbeing', 'Stress', 'Conversation',
  'AI Performance', 'Voice Pipeline', 'Latency', 'Alerts', 'Audit Log',
] as const;
type Section = typeof SECTIONS[number];

const ENDPOINTS: Record<Section, string> = {
  'Overview': 'overview',
  'Live Sessions': 'live-sessions',
  'Wellbeing': 'wellbeing',
  'Stress': 'stress',
  'Conversation': 'conversation',
  'AI Performance': 'ai-performance',
  'Voice Pipeline': 'voice-pipeline',
  'Latency': 'latency',
  'Alerts': 'alerts',
  'Audit Log': 'audit-logs',
};

/**
 * A live-data dashboard preview -- every nav item fetches from the same
 * real admin telemetry API that powers the actual admin panel. If the
 * backend isn't reachable, it says so plainly instead of showing invented
 * numbers.
 */
export default function DashboardPreview() {
  const [active, setActive] = useState<Section>('Overview');
  const [data, setData] = useState<Record<string, any>>({});
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState<Set<string>>(new Set());

  useEffect(() => {
    const key = ENDPOINTS[active];
    if (data[key] !== undefined || loading.has(key)) return;
    setLoading(prev => new Set(prev).add(key));
    fetch(`${API}/${key}`)
      .then(r => r.json())
      .then(json => setData(prev => ({ ...prev, [key]: json })))
      .catch(() => setFailed(true))
      .finally(() => setLoading(prev => { const n = new Set(prev); n.delete(key); return n; }));
  }, [active]);

  const cur = data[ENDPOINTS[active]];
  const isLoading = loading.has(ENDPOINTS[active]);

  return (
    <div className="lp-dash-frame">
      <div className="lp-dash-chrome">
        <span className="lp-dash-dot lp-dash-dot-red" />
        <span className="lp-dash-dot lp-dash-dot-amber" />
        <span className="lp-dash-dot lp-dash-dot-green" />
        <span className="lp-dash-chrome-title">Sonorus · Admin Telemetry</span>
      </div>

      <div className="lp-dash-body">
        <aside className="lp-dash-sidebar">
          {SECTIONS.map(item => (
            <button
              key={item}
              className={`lp-dash-nav-item ${active === item ? 'lp-dash-nav-active' : ''}`}
              onClick={() => setActive(item)}
            >
              {item}
            </button>
          ))}
        </aside>

        <div className="lp-dash-main">
          <div className="lp-dash-workspace">
            <span className="lp-dash-workspace-label">WORKSPACE</span>
            <span className="lp-dash-workspace-name">Sonorus · {active}</span>
            <span className={`lp-dash-status-pill ${failed ? 'lp-dash-status-off' : 'lp-dash-status-live'}`}>
              {failed ? 'Offline' : 'Live'}
            </span>
          </div>

          {failed ? (
            <p className="lp-dash-fallback">Couldn't reach the live backend from here — this panel shows real numbers when Sonorus's server is running.</p>
          ) : isLoading || !cur ? (
            <p className="lp-dash-fallback">Loading live {active.toLowerCase()}…</p>
          ) : (
            <DashSection section={active} data={cur} />
          )}
        </div>
      </div>
    </div>
  );
}

function StatGrid({ items }: { items: { label: string; value: string }[] }) {
  return (
    <div className="lp-dash-stats">
      {items.map(i => (
        <div className="lp-dash-stat" key={i.label}>
          <span className="lp-dash-stat-label">{i.label}</span>
          <span className="lp-dash-stat-value">{i.value}</span>
        </div>
      ))}
    </div>
  );
}

function BarRows({ rows }: { rows: { label: string; value: number; max: number; suffix?: string }[] }) {
  return (
    <div className="lp-dash-bars">
      {rows.map(r => (
        <div className="lp-dash-bar-row" key={r.label}>
          <span className="lp-dash-bar-label">{r.label}</span>
          <div className="lp-dash-bar-track">
            <div className="lp-dash-bar-fill" style={{ width: `${Math.min(100, (r.value / r.max) * 100)}%` }} />
          </div>
          <span className="lp-dash-bar-value">{r.value}{r.suffix || ''}</span>
        </div>
      ))}
    </div>
  );
}

function DashSection({ section, data }: { section: Section; data: any }) {
  switch (section) {
    case 'Overview':
      return (
        <>
          <StatGrid items={[
            { label: 'Conversations', value: String(data.total_conversations) },
            { label: 'Success rate', value: `${data.success_rate.toFixed(1)}%` },
            { label: 'Avg latency', value: `${Math.round(data.avg_response_latency_ms)}ms` },
            { label: 'Weekly users', value: String(data.weekly_users) },
          ]} />
          <span className="lp-dash-section-label">System status: {data.system_status}</span>
        </>
      );

    case 'Live Sessions':
      return Array.isArray(data) && data.length > 0 ? (
        <div className="lp-dash-pipeline">
          {data.slice(0, 6).map((s: any, i: number) => (
            <div className="lp-dash-pipeline-row" key={i}>
              <span className="lp-dash-pipeline-name">{s.session_id?.slice(0, 8) || `Session ${i}`}</span>
              <span className="lp-dash-pipeline-badge lp-dash-badge-ok">{s.status || 'active'}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="lp-dash-fallback">No active sessions right now — real-time, not a placeholder. Sessions appear here the moment someone connects.</p>
      );

    case 'Wellbeing': {
      const dist = data.distribution || {};
      const entries = Object.entries(dist) as [string, number][];
      const max = Math.max(...entries.map(([, v]) => v), 1);
      return (
        <>
          <span className="lp-dash-section-label">Emotion distribution (all sessions)</span>
          <BarRows rows={entries.slice(0, 6).map(([k, v]) => ({ label: k, value: v, max }))} />
        </>
      );
    }

    case 'Stress': {
      const dist = data.distribution || {};
      const max = Math.max(dist.high || 0, dist.medium || 0, dist.low || 0, 1);
      return (
        <>
          <span className="lp-dash-section-label">Stress level distribution</span>
          <BarRows rows={[
            { label: 'High', value: dist.high || 0, max },
            { label: 'Medium', value: dist.medium || 0, max },
            { label: 'Low', value: dist.low || 0, max },
          ]} />
        </>
      );
    }

    case 'Conversation':
      return (
        <StatGrid items={[
          { label: 'Avg length', value: `${Math.round(data.avg_session_length_seconds || data.avg_length_seconds || 0)}s` },
          { label: 'Avg turns', value: String(data.avg_turns ?? '—') },
          { label: 'Completion rate', value: `${(data.completion_rate ?? 0).toFixed(1)}%` },
          { label: 'Abandonment', value: `${(data.abandonment_rate ?? 0).toFixed(1)}%` },
        ]} />
      );

    case 'AI Performance':
      return (
        <StatGrid items={[
          { label: 'STT confidence', value: `${Math.round((data.stt_confidence ?? 0) * 100)}%` },
          { label: 'Emotion confidence', value: `${Math.round((data.emotion_confidence ?? 0) * 100)}%` },
          { label: 'Memory retrieval', value: `${data.memory_retrieval_success ?? '—'}%` },
          { label: 'Response success', value: `${data.response_success_rate ?? '—'}%` },
        ]} />
      );

    case 'Voice Pipeline': {
      const rows = Object.entries(data) as [string, any][];
      return (
        <div className="lp-dash-pipeline">
          {rows.map(([name, stage]) => (
            <div key={name} className="lp-dash-pipeline-row">
              <span className="lp-dash-pipeline-name">{name}</span>
              <span className={`lp-dash-pipeline-badge ${stage.status === 'Operational' ? 'lp-dash-badge-ok' : 'lp-dash-badge-warn'}`}>
                {stage.status}
              </span>
              <span className="lp-dash-pipeline-latency">{stage.latency_ms.toFixed(1)}ms</span>
            </div>
          ))}
        </div>
      );
    }

    case 'Latency': {
      const rows = Object.entries(data) as [string, any][];
      return (
        <div className="lp-dash-pipeline">
          {rows.map(([name, stat]) => (
            <div key={name} className="lp-dash-pipeline-row">
              <span className="lp-dash-pipeline-name">{name}</span>
              <span className="lp-dash-pipeline-latency">avg {stat.avg.toFixed(0)}ms · p95 {stat.p95.toFixed(0)}ms</span>
            </div>
          ))}
        </div>
      );
    }

    case 'Alerts':
      return Array.isArray(data) && data.length > 0 ? (
        <div className="lp-dash-pipeline">
          {data.slice(0, 5).map((a: any, i: number) => (
            <div className="lp-dash-pipeline-row" key={i}>
              <span className={`lp-dash-pipeline-badge ${a.severity === 'Critical' ? 'lp-dash-badge-warn' : 'lp-dash-badge-ok'}`}>{a.severity}</span>
              <span className="lp-dash-pipeline-name" style={{ width: 'auto', flex: 1 }}>{a.title}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="lp-dash-fallback">No alerts right now.</p>
      );

    case 'Audit Log':
      return Array.isArray(data) && data.length > 0 ? (
        <div className="lp-dash-pipeline">
          {data.slice(0, 6).map((a: any, i: number) => (
            <div className="lp-dash-pipeline-row" key={i}>
              <span className="lp-dash-pipeline-name">{a.operator}</span>
              <span className="lp-dash-pipeline-latency">{a.action}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="lp-dash-fallback">No audit log entries yet.</p>
      );

    default:
      return null;
  }
}
