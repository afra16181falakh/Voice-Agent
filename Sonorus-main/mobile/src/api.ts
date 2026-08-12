import { File, Paths } from 'expo-file-system';
import { API_BASE } from './config';
import { authHeader } from './auth';

export interface LoanCustomer {
  customer_id: string;
  name: string;
  loan_type: string;
  status: string;
}

export async function fetchLoanCustomers(): Promise<LoanCustomer[]> {
  const res = await fetch(`${API_BASE}/api/loan-customers`);
  return res.json();
}

export async function fetchOverview(): Promise<{ total_conversations?: number }> {
  const res = await fetch(`${API_BASE}/api/telemetry/overview`);
  return res.json();
}

export interface SessionStart {
  session_id: string;
  opening_text: string;
  opening_audio_b64: string | null;
}

export async function createMobileSession(callType?: string, customerId?: string): Promise<SessionStart> {
  const res = await fetch(`${API_BASE}/api/mobile/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeader()) },
    body: JSON.stringify({ call_type: callType ?? null, customer_id: customerId ?? null }),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.status}`);
  return res.json();
}

export interface TurnResult {
  transcript: string;
  reply_text: string;
  reply_audio_b64: string | null;
}

export async function sendTurn(sessionId: string, recordingUri: string, mimeType: string): Promise<TurnResult> {
  const form = new FormData();
  form.append('session_id', sessionId);
  // @ts-expect-error React Native FormData file shape differs from the DOM one
  form.append('audio', { uri: recordingUri, name: 'turn.m4a', type: mimeType });

  const res = await fetch(`${API_BASE}/api/mobile/turn`, { method: 'POST', body: form, headers: await authHeader() });
  if (!res.ok) throw new Error(`Turn failed: ${res.status}`);
  return res.json();
}

export interface CallHistoryEntry {
  session_id: string;
  call_type: string | null;
  customer_name: string | null;
  transcript: { role: 'user' | 'agent'; text: string }[];
  started_at: string;
  ended_at: string | null;
}

export async function fetchCallHistory(): Promise<CallHistoryEntry[]> {
  const res = await fetch(`${API_BASE}/api/mobile/history`, { headers: await authHeader() });
  if (!res.ok) throw new Error(`Failed to load history: ${res.status}`);
  return res.json();
}

export interface KnowledgeDoc {
  id: string;
  doc_id: string;
  title: string;
  category: string | null;
  content: string;
}

export async function fetchKnowledgeDocuments(): Promise<KnowledgeDoc[]> {
  const res = await fetch(`${API_BASE}/api/knowledge/documents`);
  if (!res.ok) throw new Error(`Failed to load knowledge base: ${res.status}`);
  return res.json();
}

export interface TelemetryOverview {
  total_conversations: number;
  active_sessions: number;
  daily_users: number;
  weekly_users: number;
  avg_session_duration_s: number;
  avg_response_latency_ms: number;
  success_rate: number;
  system_status: string;
}

export async function fetchTelemetryOverview(): Promise<TelemetryOverview> {
  const res = await fetch(`${API_BASE}/api/telemetry/overview`);
  if (!res.ok) throw new Error(`Failed to load telemetry: ${res.status}`);
  return res.json();
}

export async function endMobileSession(sessionId: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/mobile/sessions/${sessionId}`, { method: 'DELETE', headers: await authHeader() });
  } catch { /* best-effort */ }
}

/** Writes a base64 WAV payload to a temp file and returns its local URI,
 * ready to hand to expo-audio's createAudioPlayer. */
export async function base64WavToLocalUri(b64: string): Promise<string> {
  const file = new File(Paths.cache, `reply-${Date.now()}.wav`);
  file.create();
  file.write(b64, { encoding: 'base64' });
  return file.uri;
}
