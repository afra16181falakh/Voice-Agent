// Backend base URLs -- overridable via env so the same build can point at
// localhost for normal dev or a tunnel (ngrok etc.) URL when sharing a
// running instance with someone off this machine.
//
// Default (no env override): API_BASE is '' (relative) and WS_BASE derives
// from the page's own origin -- both routed through Vite's dev-server
// proxy (see vite.config.ts) to the local backend. This means a single
// tunnel exposing only this dev server is enough for a fully working
// remote demo; the backend is never directly reachable from outside this
// machine. Set VITE_API_BASE/VITE_WS_BASE explicitly to bypass the proxy
// and hit a backend directly (e.g. a separately tunneled/deployed one).
export const API_BASE = import.meta.env.VITE_API_BASE ?? '';
export const WS_BASE =
  import.meta.env.VITE_WS_BASE ??
  `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
