import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import LandingPage from './LandingPage';
import { API_BASE, WS_BASE } from './config';

// Gemini Live output sample rate is typically 24000Hz
const OUT_SAMPLE_RATE = 24000;
const IN_SAMPLE_RATE = 16000;

interface SessionInfo {
  session_id: string;
  start_time: string;
  is_active: boolean;
}

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<string>('Offline');
  const [conversationState, setConversationState] = useState<'idle' | 'listening' | 'thinking' | 'speaking'>('idle');
  // Mirrors conversationState for the AudioWorklet's onmessage closure, which
  // is set up once and would otherwise only ever see the state at setup time.
  const conversationStateRef = useRef(conversationState);
  useEffect(() => {
    conversationStateRef.current = conversationState;
  }, [conversationState]);
  const [retryInfo, setRetryInfo] = useState<{ attempt: number; maxRetries: number } | null>(null);

  // Live on-screen transcript of the conversation -- one entry per user
  // utterance and per assistant reply, in the order the server sends them.
  interface TranscriptEntry { id: number; role: 'user' | 'assistant'; text: string; }
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const transcriptIdRef = useRef(0);
  const transcriptScrollerRef = useRef<HTMLDivElement | null>(null);
  const appendTranscriptEntry = (role: 'user' | 'assistant', text: string) => {
    if (!text.trim()) return;
    transcriptIdRef.current += 1;
    setTranscript(prev => [...prev, { id: transcriptIdRef.current, role, text }]);
  };
  useEffect(() => {
    const el = transcriptScrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [transcript]);

  // Outbound loan-reminder call testing -- the agent calls the customer
  // (not the other way around), so this is a distinct session mode from
  // the default inbound personal companion. Picked before connecting.
  interface LoanCustomer { customer_id: string; name: string; loan_type: string; status: string; }
  const [callMode, setCallMode] = useState<'companion' | 'loan_reminder'>('companion');
  const [loanCustomers, setLoanCustomers] = useState<LoanCustomer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  useEffect(() => {
    fetch(`${API_BASE}/api/loan-customers`)
      .then(res => res.json())
      .then((data: LoanCustomer[]) => {
        setLoanCustomers(data);
        if (data.length > 0) setSelectedCustomerId(data[0].customer_id);
      })
      .catch(() => { /* dropdown just stays empty if this fails */ });
  }, []);

  // Live mic level (0-1), for an always-visible on-screen meter — so it's
  // immediately obvious whether the browser is actually picking up any
  // sound at all, without needing DevTools. Directly answers "is my mic
  // even working right now" on sight, instead of after-the-fact log checks.
  const [micLevel, setMicLevel] = useState(0);
  const micLevelUpdateCounterRef = useRef(0);
  const updateMicLevelDisplay = (rms: number) => {
    // Throttle React state updates to ~10/sec (every 3rd ~32ms chunk) —
    // frequent enough to feel live, not so frequent it causes excess re-renders.
    micLevelUpdateCounterRef.current += 1;
    if (micLevelUpdateCounterRef.current % 3 !== 0) return;
    // RMS values in normal speech roughly land in 0-0.3; scale up for a
    // meter that visibly moves rather than sitting near-flat.
    setMicLevel(Math.min(1, rms * 4));
  };

  // Admin Dashboard and Authentication States
  const [view, setView] = useState<'landing' | 'agent' | 'admin'>('landing');
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [isAdminAuthenticated, setIsAdminAuthenticated] = useState(() => {
    return localStorage.getItem('admin_authenticated') === 'true';
  });
  const [adminUsername, setAdminUsername] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'wellbeing' | 'stress' | 'conversation' | 'pipeline' | 'privacy'>('overview');

  // Telemetry Metrics States
  const [overviewMetrics, setOverviewMetrics] = useState<any>(null);
  const [liveSessions, setLiveSessions] = useState<any[]>([]);
  const [wellbeingMetrics, setWellbeingMetrics] = useState<any>(null);
  const [stressMetrics, setStressMetrics] = useState<any>(null);
  const [conversationMetrics, setConversationMetrics] = useState<any>(null);
  const [aiPerformance, setAiPerformance] = useState<any>(null);
  const [voicePipeline, setVoicePipeline] = useState<any>(null);
  const [latencyMetrics, setLatencyMetrics] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);

  // Function to load all dashboard data from API
  const fetchDashboardData = async () => {
    try {
      const [overviewRes, liveRes, wellbeingRes, stressRes, convRes, aiRes, pipeRes, latRes, alertsRes, auditRes] = await Promise.all([
        fetch(`${API_BASE}/api/telemetry/overview`),
        fetch(`${API_BASE}/api/telemetry/live-sessions`),
        fetch(`${API_BASE}/api/telemetry/wellbeing`),
        fetch(`${API_BASE}/api/telemetry/stress`),
        fetch(`${API_BASE}/api/telemetry/conversation`),
        fetch(`${API_BASE}/api/telemetry/ai-performance`),
        fetch(`${API_BASE}/api/telemetry/voice-pipeline`),
        fetch(`${API_BASE}/api/telemetry/latency`),
        fetch(`${API_BASE}/api/telemetry/alerts`),
        fetch(`${API_BASE}/api/telemetry/audit-logs`),
      ]);

      if (overviewRes.ok) setOverviewMetrics(await overviewRes.json());
      if (liveRes.ok) setLiveSessions(await liveRes.json());
      if (wellbeingRes.ok) setWellbeingMetrics(await wellbeingRes.json());
      if (stressRes.ok) setStressMetrics(await stressRes.json());
      if (convRes.ok) setConversationMetrics(await convRes.json());
      if (aiRes.ok) setAiPerformance(await aiRes.json());
      if (pipeRes.ok) setVoicePipeline(await pipeRes.json());
      if (latRes.ok) setLatencyMetrics(await latRes.json());
      if (alertsRes.ok) setAlerts(await alertsRes.json());
      if (auditRes.ok) setAuditLogs(await auditRes.json());
    } catch (err) {
      console.warn("Failed to fetch telemetry metrics", err);
    }
  };

  // Poll dashboard data when in admin view
  useEffect(() => {
    if (view === 'admin' && isAdminAuthenticated) {
      fetchDashboardData();
      const interval = setInterval(fetchDashboardData, 4000);
      return () => clearInterval(interval);
    }
  }, [view, isAdminAuthenticated]);

  const handleAdminLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError('');
    try {
      const response = await fetch(`${API_BASE}/api/telemetry/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: adminUsername, password: adminPassword }),
      });
      if (!response.ok) {
        throw new Error('Invalid credentials');
      }
      localStorage.setItem('admin_authenticated', 'true');
      setIsAdminAuthenticated(true);
      setShowLoginModal(false);
      setView('admin');
      setAdminPassword('');
    } catch (err) {
      setLoginError('Invalid username or password');
    }
  };

  const handleAdminLogout = async () => {
    try {
      await fetch(`${API_BASE}/api/telemetry/audit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'logout', details: 'Administrator logged out' }),
      });
    } catch (_) {}
    localStorage.removeItem('admin_authenticated');
    setIsAdminAuthenticated(false);
    setView('agent');
  };



  // Web Audio elements — two separate contexts for clean rate isolation:
  // captureCtxRef: 16 kHz — mic capture, worklet encoding, PCM16 → WebSocket
  // playbackCtxRef: 24 kHz — Gemini audio output scheduling
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<AudioWorkletNode | ScriptProcessorNode | null>(null);

  // Synchronous double-invocation guard for initiateConsultation. React state
  // (status/isConnected) updates asynchronously/batched, so two rapid calls
  // can both read the old value and both pass a state-based guard before the
  // first update commits. Refs update immediately, closing that race.
  const isConnectingRef = useRef(false);

  // WebSocket reference
  const wsRef = useRef<WebSocket | null>(null);

  // Playback queue variables
  const nextPlayTimeRef = useRef<number>(0);





  // Interactive background canvas ref and effect
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = 0;
    let height = 0;

    let mouseX = -1000;
    let mouseY = -1000;

    const dpr = window.devicePixelRatio || 1;

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(dpr, dpr);
    };

    resize();
    window.addEventListener('resize', resize);

    const handleMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    };

    const handleMouseLeave = () => {
      mouseX = -1000;
      mouseY = -1000;
    };

    window.addEventListener('mousemove', handleMouseMove);
    document.body.addEventListener('mouseleave', handleMouseLeave);

    const dotSpacing = 32;
    const defaultRadius = 1.2;
    const hoverRadius = 180;

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      const cols = Math.ceil(width / dotSpacing);
      const rows = Math.ceil(height / dotSpacing);

      for (let c = 0; c < cols; c++) {
        for (let r = 0; r < rows; r++) {
          const x = c * dotSpacing + dotSpacing / 2;
          const y = r * dotSpacing + dotSpacing / 2;

          const dx = x - mouseX;
          const dy = y - mouseY;
          const dist = Math.sqrt(dx * dx + dy * dy);

          let radius = defaultRadius;
          let alpha = 0.08;

          if (dist < hoverRadius) {
            const factor = 1 - dist / hoverRadius;
            const easeFactor = factor * factor;
            radius = defaultRadius + (4.5 - defaultRadius) * easeFactor;
            alpha = 0.08 + (0.7 - 0.08) * easeFactor;
          }

          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(108, 92, 231, ${alpha})`;
          ctx.fill();
        }
      }

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', handleMouseMove);
      document.body.removeEventListener('mouseleave', handleMouseLeave);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      disconnectSession();
    };
  }, []);



  const initiateConsultation = async () => {
    // Synchronous ref check first — status/isConnected are React state and
    // don't update until the next render, so a rapid double-tap could pass
    // this check twice before 'Connecting...' actually commits. The ref
    // catches that immediately.
    if (isConnectingRef.current || status === 'Connecting...' || isConnected) return;
    isConnectingRef.current = true;
    try {
      setStatus('Connecting...');

      // 1. Create the PLAYBACK context at 24 kHz inside the user-gesture so
      //    the browser allows it immediately. Gemini outputs 24 kHz PCM16, so
      //    no resampling ever happens on the output path.
      const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
      const playbackCtx = new AudioCtxClass({ sampleRate: OUT_SAMPLE_RATE });
      playbackCtxRef.current = playbackCtx;
      nextPlayTimeRef.current = playbackCtx.currentTime;

      if (playbackCtx.state === 'suspended') {
        await playbackCtx.resume();
      }

      // 2. Create session via REST endpoint
      const sessionBody = callMode === 'loan_reminder' && selectedCustomerId
        ? { call_type: 'loan_reminder', customer_id: selectedCustomerId }
        : {};
      const response = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Failed to create session on server');
      }
      const data: SessionInfo = await response.json();
      setSession(data);

      // 3. Connect WebSocket
      connectWebSocket(data.session_id);
    } catch (err) {
      console.error(err);
      setStatus('Connection failed.');
      stopAudioRecording();
    } finally {
      isConnectingRef.current = false;
    }
  };

  const connectWebSocket = (sessionId: string) => {
    const wsUrl = `${WS_BASE}/ws/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    (window as any).ws = ws;

    ws.onopen = async () => {
      setIsConnected(true);
      setStatus('Consultant Connected');
      conversationStateRef.current = 'idle';
      setConversationState('idle');

      // Reset local-detection state for the new session. Without this,
      // starting a new conversation in the same tab (no full page reload)
      // carries over stale values — e.g. wasSpeakingRef left `true` from the
      // previous session's tail end could satisfy the "you just stopped
      // talking" condition on the very first moment of silence in the BRAND
      // NEW session, flipping to 'thinking' before you've said a word and
      // withholding all mic audio for the entire session.
      wasSpeakingRef.current = false;
      silenceStreakRef.current = 0;
      bargeInStreakRef.current = 0;
      micLevelUpdateCounterRef.current = 0;
      setMicLevel(0);

      // Initialize Audio
      await startAudioRecording();
    };

    ws.onmessage = async (event) => {
      if (typeof event.data === 'string') {
        try {
          const message = JSON.parse(event.data);

          if (message.type === 'reconnecting') {
            // Gemini receive loop is retrying — show progress on screen
            setRetryInfo({ attempt: message.attempt, maxRetries: message.max_retries });
            setStatus(`Reconnecting... (${message.attempt}/${message.max_retries})`);
            setConversationState('idle');
          } else if (message.type === 'turn_failed') {
            // Backend watchdog: Gemini never responded to that turn at all.
            // Reconnect already happened server-side — just surface it and
            // return to listening, no page reload needed.
            conversationStateRef.current = 'listening';
            setConversationState('listening');
            setStatus("Didn't go through — try again");
          } else if (message.type === 'state_transition') {
            // A state update means the connection recovered — clear retry indicator
            setRetryInfo(null);
            const state = message.state;
            if (state === 'listening') {
              setConversationState('listening');
              setStatus('Listening...');
            } else if (state === 'speaking') {
              setConversationState('speaking');
              setStatus('Responding...');
            } else if (state === 'idle') {
              setConversationState('idle');
              setStatus('Consultant Connected');
            } else if (state === 'interrupted') {
              stopAudioPlayback();
              setConversationState('listening');
              setStatus('Awaiting your voice...');
            }
          }
        } catch (e) {
          console.warn("Could not parse text message frame:", event.data);
        }
      } else {
        // Binary audio chunk received — connection is alive, clear retry indicator
        setRetryInfo(null);
        const buffer = await event.data.arrayBuffer();
        queueAudioChunk(buffer);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket Error:', err);
      setStatus('Link error encountered.');
    };

    ws.onclose = () => {
      setIsConnected(false);
      setSession(null);
      setRetryInfo(null);
      setStatus('Offline');
      setConversationState('idle');
      setMicLevel(0);
      stopAudioRecording();
    };
  };

  const startAudioRecording = async () => {
    // Guard against building a second, independent mic pipeline. Without
    // this, a double-invocation (React StrictMode double-invoking effects/
    // callbacks in dev, or a rapid double-tap racing the state-based guard
    // in initiateConsultation) creates two live getUserMedia() streams and
    // two AudioWorkletNodes both wired to the same WebSocket — confirmed via
    // duplicate "AudioWorklet processor initialized" console logs, and a
    // likely cause of audio not reliably reaching the server.
    const existingStream = micStreamRef.current;
    if (existingStream && existingStream.getTracks().some(t => t.readyState === 'live')) {
      logger('Audio capture already active — skipping duplicate initialization.');
      return;
    }

    try {
      // The CAPTURE context always runs at 16 kHz — the rate Gemini Live expects.
      // IMPORTANT: We also set sampleRate in getUserMedia constraints so Chrome
      // captures at 16 kHz at the OS level, not just at the AudioContext level.
      // Without this, Chrome often grabs 48 kHz from the OS audio mixer and the
      // AudioContext resamples, but the resampled output drifts over time causing
      // progressive delay (symptom: gets slower after 2-3 turns).
      let captureCtx = captureCtxRef.current;
      if (!captureCtx || captureCtx.state === 'closed') {
        const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
        captureCtx = new AudioCtxClass({ sampleRate: IN_SAMPLE_RATE, latencyHint: 'interactive' });
        captureCtxRef.current = captureCtx;
      }

      if (captureCtx.state === 'suspended') {
        await captureCtx.resume();
      }

      // Request mic audio with explicit 16 kHz sample rate constraint.
      // Chrome may not always honour this but it signals the intent clearly
      // and avoids OS-level resampling on most hardware.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: IN_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });
      micStreamRef.current = stream;

      // Log actual sample rate to detect any OS-level mismatch
      const actualRate = captureCtx.sampleRate;
      if (actualRate !== IN_SAMPLE_RATE) {
        console.warn(
          `[Sonorus] AudioContext running at ${actualRate} Hz (expected ${IN_SAMPLE_RATE} Hz). ` +
          `Resampling will occur in the worklet.`
        );
      }

      // Wire mic → capture context → worklet → WebSocket
      if (captureCtx.state !== 'closed') {
        const source = captureCtx.createMediaStreamSource(stream);
        await setupAudioProcessor(captureCtx, source, actualRate);
      }



      logger(`Audio capture initialized at ${captureCtx.sampleRate} Hz (target: ${IN_SAMPLE_RATE} Hz).`);
    } catch (err) {
      console.error('Could not access microphone:', err);
      setStatus('Mic permission needed.');
    }
  };

  const floatTo16BitPCM = (float32Array: Float32Array): ArrayBuffer => {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buffer;
  };

  const queueAudioChunk = (arrayBuffer: ArrayBuffer) => {
    // Use the dedicated PLAYBACK context (24 kHz). Since the context was
    // created at 24 kHz and the buffer is also tagged 24 kHz, no resampling
    // occurs — the browser plays the samples at exactly the right pitch/speed.
    const playbackCtx = playbackCtxRef.current;
    if (!playbackCtx || playbackCtx.state === 'closed') return;

    // Convert PCM16 little-endian → Float32 normalised [-1, 1]
    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    // Buffer and context both at 24 kHz — zero resampling
    const audioBuffer = playbackCtx.createBuffer(1, float32Array.length, OUT_SAMPLE_RATE);
    audioBuffer.copyToChannel(float32Array, 0);

    // Schedule gapless playback
    const source = playbackCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(playbackCtx.destination);

    const currentTime = playbackCtx.currentTime;
    if (nextPlayTimeRef.current < currentTime) {
      // Queue was empty or fell behind — add a tiny lead-in to avoid glitch
      nextPlayTimeRef.current = currentTime + 0.02;
    }

    source.start(nextPlayTimeRef.current);
    nextPlayTimeRef.current += audioBuffer.duration;
  };

  const setupAudioProcessor = async (
    audioCtx: AudioContext,
    source: MediaStreamAudioSourceNode,
    actualSampleRate: number = IN_SAMPLE_RATE,
  ) => {
    const supportsWorklet = typeof audioCtx.audioWorklet !== 'undefined';

    if (supportsWorklet) {
      try {
        // Load the worklet module from public directory
        await audioCtx.audioWorklet.addModule('/audio/microphone-processor.js');

        // Create AudioWorkletNode, passing the target sample rate so the
        // processor can downsample if Chrome is running at 48 kHz.
        const processor = new AudioWorkletNode(audioCtx, 'microphone-processor', {
          processorOptions: {
            targetSampleRate: IN_SAMPLE_RATE,
            actualSampleRate: actualSampleRate,
          }
        });
        processorRef.current = processor;

        // Receive the PCM16 buffers (+ RMS energy) from the audio thread.
        // RMS checks always run locally (needed to detect if you start
        // talking again). The actual SEND to the server is withheld while
        // in 'thinking' — by the time local silence is confirmed, Gemini has
        // already closed out the turn on its side too, so there's nothing
        // useful left to send; withholding means no stray background noise
        // gets picked up as new input during that gap.
        processor.port.onmessage = (event) => {
          const { pcm16, rms } = event.data;
          updateMicLevelDisplay(rms);
          checkLocalBargeIn(rms);
          checkLocalThinkingIndicator(rms);
          if (conversationStateRef.current === 'thinking') return;
          if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
          wsRef.current.send(pcm16);
        };

        source.connect(processor);
        // Do NOT connect processor to destination — we don't want mic audio
        // playing through speakers. Remove the old processor.connect(audioCtx.destination) line.
        logger('AudioWorklet processor initialized.');
        return;
      } catch (workletErr) {
        console.warn('Failed to load AudioWorklet, falling back to ScriptProcessorNode:', workletErr);
      }
    }

    // Fallback implementation for older browsers
    const processor = audioCtx.createScriptProcessor(512, 1, 1);
    processorRef.current = processor;

    processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      const rms = computeRMS(inputData);
      updateMicLevelDisplay(rms);
      checkLocalBargeIn(rms);
      checkLocalThinkingIndicator(rms);
      if (conversationStateRef.current === 'thinking') return;
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      const pcm16Buffer = floatTo16BitPCM(inputData);
      wsRef.current.send(pcm16Buffer);
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);
    logger('ScriptProcessor fallback initialized.');
  };

  const stopAudioPlayback = async () => {
    // On barge-in / interruption: tear down ONLY the playback context to flush
    // queued audio buffers. The capture context is left completely untouched so
    // mic audio keeps streaming to the server throughout the interruption.
    const playbackCtx = playbackCtxRef.current;
    if (playbackCtx && playbackCtx.state !== 'closed') {
      try {
        await playbackCtx.close();
      } catch (_) { /* already closed */ }
    }

    // Spin up a fresh 24 kHz playback context for the next assistant turn
    const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
    const newPlaybackCtx = new AudioCtxClass({ sampleRate: OUT_SAMPLE_RATE });
    playbackCtxRef.current = newPlaybackCtx;
    nextPlayTimeRef.current = newPlaybackCtx.currentTime;
    logger("Playback context reset after interruption.");
  };

  // Local barge-in: cut assistant playback the instant real speech is
  // detected, without waiting for Gemini's own interruption round trip.
  // Gemini's server-side VAD still runs in parallel as the authoritative
  // signal — this is purely a faster local reflex layered on top.
  //
  // Deliberately gated on sustained RMS energy, not "a chunk arrived" — that
  // naive version previously caused a self-interruption thrashing loop when
  // it lived server-side (any background noise during playback tripped it).
  //
  // Tuned up from 0.02/3 after real testing on speakers (no headphones):
  // Sonorus's own voice bleeding from speakers into the mic was crossing the
  // original threshold and cutting responses short mid-sentence, with no
  // more audio left to recover with once Gemini had already finished sending
  // a (now short) response. Higher threshold + longer sustained-energy
  // requirement makes speaker echo far less likely to false-trigger, while
  // still reacting well before Gemini's own round-trip would.
  const BARGE_IN_RMS_THRESHOLD = 0.06;
  const BARGE_IN_DEBOUNCE_CHUNKS = 6; // ~192ms of sustained energy at 32ms/chunk
  const bargeInStreakRef = useRef(0);

  const checkLocalBargeIn = (rms: number) => {
    if (conversationStateRef.current !== 'speaking') {
      bargeInStreakRef.current = 0;
      return;
    }

    if (rms >= BARGE_IN_RMS_THRESHOLD) {
      bargeInStreakRef.current += 1;
      if (bargeInStreakRef.current >= BARGE_IN_DEBOUNCE_CHUNKS) {
        bargeInStreakRef.current = 0;
        conversationStateRef.current = 'listening';
        setConversationState('listening');
        setStatus('Awaiting your voice...');
        stopAudioPlayback();
      }
    } else {
      bargeInStreakRef.current = 0;
    }
  };

  // Thinking indicator: Gemini's real generation time (confirmed ~2-3s from
  // testing) was invisible to the user — the UI stayed on "Listening..." the
  // whole time because nothing ever signaled "your turn is done, I'm working
  // on it now." This detects YOUR silence locally (same RMS approach as
  // barge-in) and flips the UI to "Thinking..." the instant you stop —
  // purely cosmetic, zero network round trip, self-corrects back to
  // "Listening..." if you start talking again before a real response arrives.
  const SPEECH_ACTIVE_RMS_THRESHOLD = 0.06;
  const SILENCE_DEBOUNCE_CHUNKS = 6; // ~192ms of sustained near-silence
  const wasSpeakingRef = useRef(false);
  const silenceStreakRef = useRef(0);

  // Audio equivalent of the visual "Thinking..." indicator — a very short,
  // quiet blip, the same trick commercial voice assistants use (a soft tone
  // or "mm") to fill the silence while the real response is still generating.
  // Synthesized locally (no audio file), fully separate from the Gemini
  // playback context so it never interferes with response audio.
  const playThinkingTone = () => {
    try {
      const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
      const toneCtx = new AudioCtxClass();
      const oscillator = toneCtx.createOscillator();
      const gain = toneCtx.createGain();
      oscillator.type = 'sine';
      oscillator.frequency.value = 440;
      gain.gain.setValueAtTime(0.0001, toneCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.05, toneCtx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, toneCtx.currentTime + 0.15);
      oscillator.connect(gain);
      gain.connect(toneCtx.destination);
      oscillator.start();
      oscillator.stop(toneCtx.currentTime + 0.16);
      oscillator.onended = () => toneCtx.close();
    } catch (_) { /* non-critical, skip silently */ }
  };

  const checkLocalThinkingIndicator = (rms: number) => {
    const state = conversationStateRef.current;
    const isSpeechActive = rms >= SPEECH_ACTIVE_RMS_THRESHOLD;

    if (state === 'listening') {
      if (isSpeechActive) {
        wasSpeakingRef.current = true;
        silenceStreakRef.current = 0;
        return;
      }
      if (!wasSpeakingRef.current) return;

      silenceStreakRef.current += 1;
      if (silenceStreakRef.current >= SILENCE_DEBOUNCE_CHUNKS) {
        wasSpeakingRef.current = false;
        silenceStreakRef.current = 0;
        conversationStateRef.current = 'thinking';
        setConversationState('thinking');
        setStatus('Thinking...');
        playThinkingTone();
      }
      return;
    }

    if (state === 'thinking') {
      // User started talking again during the gap — the "you're done" call
      // was premature, go back to a listening indicator.
      if (isSpeechActive) {
        wasSpeakingRef.current = true;
        silenceStreakRef.current = 0;
        conversationStateRef.current = 'listening';
        setConversationState('listening');
        setStatus('Listening...');
      }
      return;
    }

    // Any other state (idle/speaking): reset tracking for the next turn.
    wasSpeakingRef.current = false;
    silenceStreakRef.current = 0;
  };

  const computeRMS = (float32Array: Float32Array): number => {
    if (float32Array.length === 0) return 0;
    let sumSquares = 0;
    for (let i = 0; i < float32Array.length; i++) {
      sumSquares += float32Array[i] * float32Array[i];
    }
    return Math.sqrt(sumSquares / float32Array.length);
  };

  const stopAudioRecording = () => {


    // Full teardown on disconnect — close both contexts.
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
    }
    if (captureCtxRef.current) {
      captureCtxRef.current.close();
      captureCtxRef.current = null;
    }
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close();
      playbackCtxRef.current = null;
    }
  };

  const disconnectSession = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    stopAudioRecording();
  };



  const logger = (msg: string) => {
    console.log(`[Sonorus Frontend] ${msg}`);
  };

  // State class mapper for the mic button
  const getMicClass = () => {
    switch (conversationState) {
      case 'listening': return 'mic-listening';
      case 'thinking': return 'mic-thinking';
      case 'speaking': return 'mic-speaking';
      default: return 'mic-idle';
    }
  };

  // Shared across every view (landing/agent/admin) so opening it from the
  // landing page's "Admin" button actually shows something immediately,
  // instead of silently setting state that only became visible later after
  // switching views — confirmed live as the exact bug being reported.
  const loginModal = showLoginModal && (
    <div className="login-modal-overlay">
      <div className="login-modal-card">
        <h2>Admin Panel Login</h2>
        <p className="login-subtitle">Enter administrator credentials to unlock telemetry.</p>
        <form onSubmit={handleAdminLogin}>
          <div className="form-group">
            <label>Username</label>
            <input
              type="text"
              value={adminUsername}
              onChange={(e) => setAdminUsername(e.target.value)}
              required
              placeholder="e.g. admin"
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={adminPassword}
              onChange={(e) => setAdminPassword(e.target.value)}
              required
              placeholder="••••••••"
            />
          </div>
          {loginError && <p className="error-text">{loginError}</p>}
          <div className="modal-actions">
            <button type="button" className="btn-cancel" onClick={() => setShowLoginModal(false)}>Cancel</button>
            <button type="submit" className="btn-login">Authenticate</button>
          </div>
        </form>
      </div>
    </div>
  );

  if (view === 'landing') {
    return (
      <>
        <LandingPage
          onEnterConsole={(mode) => {
            if (mode) setCallMode(mode);
            setView('agent');
          }}
          onOpenAdmin={() => setShowLoginModal(true)}
        />
        {loginModal}
      </>
    );
  }

  return (
    <div className="concierge-app">
      {/* Dynamic Background Wallpaper */}
      <div className="dynamic-bg-wallpaper" />

      {/* Interactive background dot grid */}
      <canvas ref={canvasRef} className="interactive-bg-canvas" />

      {/* Elegantly branded header */}
      <header className="luxury-header">
        <div className="header-left-placeholder"></div>

        <div className="header-brand-container">
          <div className="logo-wave-indicator">
            <div className="logo-wave-bar logo-bar-1"></div>
            <div className="logo-wave-bar logo-bar-2"></div>
            <div className="logo-wave-bar logo-bar-3"></div>
            <div className="logo-wave-bar logo-bar-4"></div>
            <div className="logo-wave-bar logo-bar-5"></div>
          </div>
          <span className="header-logo">SONORUS</span>
          <div className="logo-wave-indicator">
            <div className="logo-wave-bar logo-bar-1"></div>
            <div className="logo-wave-bar logo-bar-2"></div>
            <div className="logo-wave-bar logo-bar-3"></div>
            <div className="logo-wave-bar logo-bar-4"></div>
            <div className="logo-wave-bar logo-bar-5"></div>
          </div>
        </div>

        <div className="header-actions">
          {isAdminAuthenticated && (
            <button 
              className={`header-action-btn ${view === 'admin' ? 'active-tab-btn' : ''}`}
              title="Admin Dashboard"
              onClick={() => setView(view === 'admin' ? 'agent' : 'admin')}
            >
              <svg className="header-icon" viewBox="0 0 24 24" width="20" height="20">
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 16H6c-.6 0-1-.4-1-1V6c0-.6.4-1 1-1h12c.6 0 1 .4 1 1v12c0 .6-.4 1-1 1zm-4.5-9h-3c-.3 0-.5.2-.5.5v5c0 .3.2.5.5.5h3c.3 0 .5-.2.5-.5v-5c0-.3-.2-.5-.5-.5zm-4.5 3h-2c-.3 0-.5.2-.5.5v2c0 .3.2.5.5.5h2c.3 0 .5-.2.5-.5v-2c0-.3-.2-.5-.5-.5zm9-5h-2c-.3 0-.5.2-.5.5v7c0 .3.2.5.5.5h2c.3 0 .5-.2.5-.5v-7c0-.3-.2-.5-.5-.5z" />
              </svg>
            </button>
          )}
          {!isAdminAuthenticated && (
            <button 
              className="header-action-btn" 
              title="Admin Login"
              onClick={() => setShowLoginModal(true)}
            >
              <svg className="header-icon" viewBox="0 0 24 24" width="20" height="20">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
              </svg>
            </button>
          )}
          {isAdminAuthenticated && (
            <button 
              className="header-action-btn logout-btn" 
              title="Log Out"
              onClick={handleAdminLogout}
            >
              <svg className="header-icon" viewBox="0 0 24 24" width="20" height="20">
                <path d="M10.09 15.59L11.5 17l5-5-5-5-1.41 1.41L12.67 11H3v2h9.67l-2.58 2.59zM19 3H5c-1.11 0-2 .9-2 2v4h2V5h14v14H5v-4H3v4c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z" />
              </svg>
            </button>
          )}
        </div>
      </header>

      {loginModal}

      {view === 'admin' && isAdminAuthenticated ? (
        // ==========================================
        // Admin Telemetry Dashboard View
        // ==========================================
        <main className="admin-main">
          <div className="admin-container">
            {/* Sidebar Navigation */}
            <aside className="admin-sidebar">
              <div className="sidebar-title">Analytics Menu</div>
              <button className={`sidebar-link ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => setActiveTab('overview')}>
                <span>📊</span> Overview
              </button>
              <button className={`sidebar-link ${activeTab === 'wellbeing' ? 'active' : ''}`} onClick={() => setActiveTab('wellbeing')}>
                <span>🎭</span> Employee Wellbeing
              </button>
              <button className={`sidebar-link ${activeTab === 'stress' ? 'active' : ''}`} onClick={() => setActiveTab('stress')}>
                <span>⚡</span> Stress Analytics
              </button>
              <button className={`sidebar-link ${activeTab === 'conversation' ? 'active' : ''}`} onClick={() => setActiveTab('conversation')}>
                <span>🗣️</span> Conversations
              </button>
              <button className={`sidebar-link ${activeTab === 'pipeline' ? 'active' : ''}`} onClick={() => setActiveTab('pipeline')}>
                <span>🚀</span> AI Pipeline
              </button>
              <button className={`sidebar-link ${activeTab === 'privacy' ? 'active' : ''}`} onClick={() => setActiveTab('privacy')}>
                <span>🔒</span> Privacy & Audit
              </button>
            </aside>

            {/* Dashboard Workspace */}
            <section className="admin-content">
              {/* Tab 1: Overview */}
              {activeTab === 'overview' && (
                <div className="tab-pane">
                  <h1 className="tab-header">Dashboard Overview</h1>
                  
                  {/* Overview Metrics Cards Grid */}
                  <div className="metrics-grid">
                    <div className="metric-card">
                      <span className="metric-title">Total Conversations</span>
                      <span className="metric-value">{overviewMetrics?.total_conversations ?? '--'}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">Active Sessions</span>
                      <span className="metric-value live-pulse">{overviewMetrics?.active_sessions ?? '0'}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">Daily Active Users</span>
                      <span className="metric-value">{overviewMetrics?.daily_users ?? '--'}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">Avg Response Latency</span>
                      <span className="metric-value">{overviewMetrics?.avg_response_latency_ms ?? '--'} ms</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">Success Rate</span>
                      <span className="metric-value">{overviewMetrics?.success_rate ?? '--'}%</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">System Status</span>
                      <span className="metric-value system-ok">● {overviewMetrics?.system_status ?? 'Operational'}</span>
                    </div>
                  </div>

                  <div className="overview-split-layout">
                    {/* Live Sessions Monitor */}
                    <div className="panel live-sessions-panel">
                      <h3>Live Session Feed</h3>
                      <div className="table-responsive">
                        <table className="admin-table">
                          <thead>
                            <tr>
                              <th>Anonymous ID</th>
                              <th>Stage</th>
                              <th>Emotion</th>
                              <th>Duration</th>
                              <th>Avg Latency</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {liveSessions.length === 0 ? (
                              <tr>
                                <td colSpan={6} className="empty-table">No active sessions currently streaming.</td>
                              </tr>
                            ) : (
                              liveSessions.map((s) => (
                                <tr key={s.session_id}>
                                  <td className="monospace">{s.session_id.substring(0, 8)}...</td>
                                  <td><span className={`badge badge-stage-${s.stage}`}>{s.stage.toUpperCase()}</span></td>
                                  <td>{s.emotion}</td>
                                  <td>{s.duration_s}s</td>
                                  <td>{s.latency_ms} ms</td>
                                  <td className="system-ok">Active</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Alerts feed */}
                    <div className="panel alerts-panel">
                      <h3>System Warnings & Alerts</h3>
                      <div className="alerts-feed">
                        {alerts.length === 0 ? (
                          <div className="empty-feed">System is healthy. No active alerts.</div>
                        ) : (
                          alerts.map((a, i) => (
                            <div key={i} className={`alert-item alert-${a.severity.toLowerCase()}`}>
                              <span className="alert-severity">{a.severity.toUpperCase()}</span>
                              <div className="alert-body">
                                <strong>{a.title}</strong>
                                <p>{a.details}</p>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 2: Employee Wellbeing */}
              {activeTab === 'wellbeing' && (
                <div className="tab-pane">
                  <h1 className="tab-header">Employee Wellbeing Analytics</h1>
                  <p className="tab-description">Tracks rolling distributions of emotional wellness captured during voice sessions.</p>
                  
                  <div className="charts-split-layout">
                    <div className="panel chart-panel">
                      <h3>Emotion Distribution</h3>
                      {wellbeingMetrics ? (
                        // Render SVG Donut Chart
                        <div className="donut-chart-wrapper">
                          <svg width="200" height="200" viewBox="0 0 200 200">
                            <circle cx="100" cy="100" r="70" fill="transparent" stroke="rgba(255,255,255,0.05)" strokeWidth="20" />
                            {(() => {
                              const data = wellbeingMetrics.distribution || {};
                              const total = Object.values(data).reduce((a: any, b: any) => a + b, 0) as number;
                              let accAngle = 0;
                              const colors: Record<string, string> = {
                                happy: '#2ecc71', neutral: '#95a5a6', sad: '#3498db',
                                frustrated: '#e74c3c', anxious: '#e67e22', excited: '#f1c40f',
                                confused: '#9b59b6', engaged: '#1abc9c', playful: '#ff7675',
                                reflective: '#a29bfe', tired: '#ffeaa7'
                              };
                              const circ = 2 * Math.PI * 70;
                              return Object.entries(data).map(([em, val]: [string, any]) => {
                                const percentage = total > 0 ? val / total : 0;
                                const strokeLen = percentage * circ;
                                const strokeOffset = circ - strokeLen + accAngle;
                                accAngle -= strokeLen;
                                return (
                                  <circle
                                    key={em} cx="100" cy="100" r="70" fill="transparent"
                                    stroke={colors[em] || '#7f8c8d'} strokeWidth="20"
                                    strokeDasharray={`${strokeLen} ${circ - strokeLen}`} strokeDashoffset={strokeOffset}
                                    transform="rotate(-90 100 100)"
                                    style={{ cursor: 'pointer' }}
                                  >
                                    <title>{`${em.charAt(0).toUpperCase() + em.slice(1)}: ${val} (${(percentage * 100).toFixed(1)}%)`}</title>
                                  </circle>
                                );
                              });
                            })()}
                          </svg>
                          <div className="chart-legend">
                            {Object.entries(wellbeingMetrics.distribution || {}).map(([em, val]: [string, any]) => {
                              const colors: Record<string, string> = {
                                happy: '#2ecc71', neutral: '#95a5a6', sad: '#3498db',
                                frustrated: '#e74c3c', anxious: '#e67e22', excited: '#f1c40f',
                                confused: '#9b59b6', engaged: '#1abc9c', playful: '#ff7675',
                                reflective: '#a29bfe', tired: '#ffeaa7'
                              };
                              return (
                                <div key={em} className="legend-item">
                                  <span className="legend-dot" style={{ backgroundColor: colors[em] || '#7f8c8d' }} />
                                  <span className="legend-label">{em.toUpperCase()}</span>
                                  <span className="legend-val">{val}</span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ) : <div className="loader">Loading chart...</div>}
                    </div>

                    <div className="panel chart-panel">
                      <h3>Department-wise Wellbeing Trends</h3>
                      {wellbeingMetrics?.department_wellbeing ? (
                        <div className="dept-bars-container">
                          {Object.entries(wellbeingMetrics.department_wellbeing).map(([dept, counts]: [string, any]) => {
                            const happy = counts.happy || 0;
                            const engaged = counts.engaged || 0;
                            const playful = counts.playful || 0;
                            const total = Object.values(counts).reduce((a: any, b: any) => a + b, 0) as number;
                            const positive = happy + engaged + playful;
                            const pct = total > 0 ? (positive / total) * 100 : 0;
                            return (
                              <div key={dept} className="dept-bar-row">
                                <span className="dept-name">{dept}</span>
                                <div className="dept-bar-outer">
                                  <div className="dept-bar-inner" style={{ width: `${pct}%` }} />
                                </div>
                                <span className="dept-pct">{pct.toFixed(0)}% Positive</span>
                              </div>
                            );
                          })}
                        </div>
                      ) : <div className="loader">Loading department comparison...</div>}
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 3: Stress Analytics */}
              {activeTab === 'stress' && (
                <div className="tab-pane">
                  <h1 className="tab-header">Employee Stress Analytics</h1>
                  
                  <div className="charts-split-layout">
                    <div className="panel chart-panel">
                      <h3>Weekly Stress Level Trends</h3>
                      {stressMetrics?.weekly_trend ? (
                        // Render SVG Line Chart
                        <div className="line-chart-wrapper">
                          {(() => {
                            const trend = stressMetrics.weekly_trend;
                            const entries = Object.entries(trend).sort();
                            const width = 500;
                            const height = 200;
                            const padding = 30;
                            const chartWidth = width - padding * 2;
                            const chartHeight = height - padding * 2;
                            const maxVal = Math.max(...entries.map(([_, c]: [any, any]) => 
                              (c.high || 0) + (c.medium || 0) + (c.low || 0)
                            ), 5);

                            const points = entries.map(([date, c]: [any, any], idx) => {
                              const total = (c.high || 0) + (c.medium || 0) + (c.low || 0);
                              const x = padding + (idx / (entries.length - 1 || 1)) * chartWidth;
                              const y = padding + chartHeight - (total / maxVal) * chartHeight;
                              return { x, y, date };
                            });

                            const pathD = points.reduce((acc, p, idx) => 
                              idx === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`, ''
                            );

                            return (
                              <svg width="100%" height="200" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
                                <defs>
                                  <linearGradient id="stressGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#6c5ce7" stopOpacity="0.4" />
                                    <stop offset="100%" stopColor="#6c5ce7" stopOpacity="0" />
                                  </linearGradient>
                                </defs>
                                <path d={`${pathD} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`} fill="url(#stressGrad)" />
                                <path d={pathD} fill="none" stroke="#6c5ce7" strokeWidth="3" />
                                {points.map((p, idx) => (
                                  <circle key={idx} cx={p.x} cy={p.y} r="4" fill="#6c5ce7" stroke="#fff" strokeWidth="1" />
                                ))}
                              </svg>
                            );
                          })()}
                        </div>
                      ) : <div className="loader">Loading trends...</div>}
                    </div>

                    <div className="panel chart-panel">
                      <h3>Therapeutic Stress Reduction (Pre- vs Post-Conversation)</h3>
                      <p className="description">Measures shifts in stress indices from session start to graceful completion.</p>
                      {stressMetrics?.reductions ? (
                        <div className="reductions-stats">
                          <div className="reduction-row">
                            <span className="reduction-label">High Stress Reduced to Low</span>
                            <span className="reduction-val">{stressMetrics.reductions.high_to_low} sessions</span>
                          </div>
                          <div className="reduction-row">
                            <span className="reduction-label">High Stress Managed to Medium</span>
                            <span className="reduction-val">{stressMetrics.reductions.high_to_medium} sessions</span>
                          </div>
                          <div className="reduction-row">
                            <span className="reduction-label">Medium Stress Reduced to Low</span>
                            <span className="reduction-val">{stressMetrics.reductions.medium_to_low} sessions</span>
                          </div>
                          <div className="reduction-row">
                            <span className="reduction-label">Unchanged / Neutral Baseline</span>
                            <span className="reduction-val">{stressMetrics.reductions.no_change} sessions</span>
                          </div>
                        </div>
                      ) : <div className="loader">Loading reductions...</div>}
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 4: Conversation Analytics */}
              {activeTab === 'conversation' && (
                <div className="tab-pane">
                  <h1 className="tab-header">Conversation & Topic Analytics</h1>
                  
                  <div className="metrics-grid">
                    <div className="metric-card">
                      <span className="metric-title">Avg Session Length</span>
                      <span className="metric-value">{conversationMetrics?.avg_length_seconds ?? '--'}s</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">Avg Dialogue Turns</span>
                      <span className="metric-value">{conversationMetrics?.avg_turns ?? '--'} turns</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">Completion Rate</span>
                      <span className="metric-value">{conversationMetrics?.completion_rate ?? '--'}%</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-title">Abandonment Rate</span>
                      <span className="metric-value">{conversationMetrics?.abandonment_rate ?? '--'}%</span>
                    </div>
                  </div>

                  <div className="panel">
                    <h3>Discovered Conversation Topics</h3>
                    <div className="topics-list">
                      {conversationMetrics?.topics ? (
                        Object.entries(conversationMetrics.topics).map(([top, count]: [string, any]) => (
                          <div key={top} className="topic-tag-row">
                            <span className="topic-name">{top}</span>
                            <span className="topic-bar-outer">
                              <span className="topic-bar-inner" style={{ width: `${(count / 45) * 100}%` }} />
                            </span>
                            <span className="topic-count">{count} triggers</span>
                          </div>
                        ))
                      ) : <div className="loader">Loading topics...</div>}
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 5: AI Pipeline */}
              {activeTab === 'pipeline' && (
                <div className="tab-pane">
                  <h1 className="tab-header">AI Pipeline Node Performance & Latency</h1>
                  <p className="tab-description">Tracks health and node processing speeds across the pipeline stages.</p>
                  
                  {/* Pipeline monitor visualizer */}
                  <div className="panel visualizer-panel">
                    <h3>Sub-Second Cognitive Pipeline stages</h3>
                    {voicePipeline ? (
                      <div className="pipeline-monitor">
                        {['STT', 'Emotion Detection', 'Memory', 'LLM', 'Safety', 'TTS'].map((name, idx) => {
                          const metrics = voicePipeline[name] || { status: 'Operational', latency_ms: 100, success_rate: 100 };
                          const isOk = metrics.status === 'Operational';
                          return (
                            <div key={name} className="pipeline-node-wrapper">
                              <div className={`pipeline-node ${isOk ? 'node-ok' : 'node-error'}`}>
                                <div className="node-icon">
                                  {name === 'STT' && '📝'}
                                  {name === 'Emotion Detection' && '🎭'}
                                  {name === 'Memory' && '💾'}
                                  {name === 'LLM' && '🧠'}
                                  {name === 'Safety' && '🛡️'}
                                  {name === 'TTS' && '🔊'}
                                </div>
                                <div className="node-info">
                                  <span className="node-name">{name}</span>
                                  <span className="node-latency">{metrics.latency_ms} ms</span>
                                  <span className="node-success">{metrics.success_rate}% OK</span>
                                </div>
                              </div>
                              {idx < 5 && <div className="pipeline-arrow">➔</div>}
                            </div>
                          );
                        })}
                      </div>
                    ) : <div className="loader">Loading pipeline stages...</div>}
                  </div>

                  {/* Latency Dashboard percentile breakdown */}
                  <div className="panel latency-dashboard-panel">
                    <h3>Latency Percentiles (Avg, P50, P90, P95, P99)</h3>
                    <div className="table-responsive">
                      <table className="admin-table">
                        <thead>
                          <tr>
                            <th>Pipeline Stage</th>
                            <th>Average</th>
                            <th>P50</th>
                            <th>P90</th>
                            <th>P95</th>
                            <th>P99</th>
                          </tr>
                        </thead>
                        <tbody>
                          {latencyMetrics ? (
                            Object.entries(latencyMetrics).map(([stg, lat]: [string, any]) => (
                              <tr key={stg}>
                                <td><strong>{stg}</strong></td>
                                <td>{lat.avg} ms</td>
                                <td>{lat.p50} ms</td>
                                <td>{lat.p90} ms</td>
                                <td>{lat.p95} ms</td>
                                <td>{lat.p99} ms</td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={6} className="empty-table">Loading latency percentiles...</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* AI Performance Statistics */}
                  <div className="panel ai-performance-panel">
                    <h3>AI Pipeline Model Performance</h3>
                    {aiPerformance ? (
                      <div className="metrics-grid">
                        <div className="metric-card">
                          <span className="metric-title">STT Accuracy Estimate</span>
                          <span className="metric-value">{(aiPerformance.stt_confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div className="metric-card">
                          <span className="metric-title">Emotion Confidence</span>
                          <span className="metric-value">{(aiPerformance.emotion_confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div className="metric-card">
                          <span className="metric-title">Pipeline Fallback Rate</span>
                          <span className="metric-value">{aiPerformance.fallback_rate}%</span>
                        </div>
                        <div className="metric-card">
                          <span className="metric-title">Memory Hits Success</span>
                          <span className="metric-value">{aiPerformance.memory_retrieval_success}%</span>
                        </div>
                      </div>
                    ) : <div className="loader">Loading AI performance metrics...</div>}
                  </div>
                </div>
              )}

              {/* Tab 6: Privacy & Audit */}
              {activeTab === 'privacy' && (
                <div className="tab-pane">
                  <h1 className="tab-header">System Privacy & Audit Logging</h1>
                  
                  <div className="charts-split-layout">
                    <div className="panel privacy-panel">
                      <h3>Privacy Configuration</h3>
                      <div className="privacy-details">
                        <div className="privacy-item">
                          <span>Connection Encryption</span>
                          <strong className="badge-ok">Active (TLS 1.3 / WSS)</strong>
                        </div>
                        <div className="privacy-item">
                          <span>Database Encryption</span>
                          <strong className="badge-ok">Active (AES-256)</strong>
                        </div>
                        <div className="privacy-item">
                          <span>Voice Pipeline Anonymity</span>
                          <strong className="badge-ok">Enforced (No raw data logged)</strong>
                        </div>
                        <div className="privacy-item">
                          <span>Data Retention Policy</span>
                          <strong>7 Days Rolling Log Purge</strong>
                        </div>
                      </div>
                    </div>

                    <div className="panel audit-panel">
                      <h3>Administrative Audit Log</h3>
                      <div className="audit-feed">
                        {auditLogs.length === 0 ? (
                          <div className="empty-feed">No administrative logs recorded.</div>
                        ) : (
                          auditLogs.map((log, i) => (
                            <div key={i} className="audit-item">
                              <span className="audit-time">{new Date(log.timestamp).toLocaleTimeString()}</span>
                              <div className="audit-body">
                                <strong>{log.operator.toUpperCase()} {log.action}</strong>
                                <p>{log.details}</p>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </div>
        </main>
      ) : (
        // ==========================================
        // User Voice Console Interface (Standard)
        // ==========================================
        <main className="concierge-main">
          <div className="concierge-layout">
            <div className="interactive-column">
              <div className="gold-card status-card">
                <span className="card-tag">Voice Console</span>

                <p className="description">
                  Experience voice interactions that feel genuinely human. Speak naturally, interrupt at any point, or share your thoughts.
                </p>

                <div className="status-display">
                  <span className={`status-dot dot-${conversationState}`}></span>
                  <span className="status-text">{status}</span>
                  {session && <span className="session-id-indicator" style={{ marginLeft: 'auto', fontSize: '0.8rem', opacity: 0.5 }}>ID: {session.session_id.substring(0, 8)}</span>}
                </div>

                {retryInfo && (
                  <div className="retry-badge">
                    <span className="retry-spinner" />
                    <span className="retry-text">
                      Reconnecting to Gemini&nbsp;&nbsp;{retryInfo.attempt} / {retryInfo.maxRetries}
                    </span>
                  </div>
                )}

                {isConnected && (
                  <div
                    title="Live mic input level — should move when you talk. If it never moves, the browser isn't picking up your voice."
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      margin: '6px 0 2px',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      letterSpacing: '0.1em',
                      color: '#8c89b4',
                    }}
                  >
                    <span>MIC</span>
                    <div
                      style={{
                        flex: '0 0 140px',
                        height: '6px',
                        background: 'rgba(140,137,180,0.18)',
                        borderRadius: '3px',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          width: `${Math.round(micLevel * 100)}%`,
                          height: '100%',
                          background: micLevel > 0.05 ? '#34c759' : '#c5c3dd',
                          transition: 'width 80ms linear',
                        }}
                      />
                    </div>
                  </div>
                )}

                <div className={`mic-container mic-container-${conversationState}`}>
                  <div className="waveform-container left-wave">
                    <div className="waveform-bar bar-1"></div>
                    <div className="waveform-bar bar-2"></div>
                    <div className="waveform-bar bar-3"></div>
                    <div className="waveform-bar bar-4"></div>
                    <div className="waveform-bar bar-5"></div>
                  </div>

                  <div className={`mic-halo halo-${conversationState}`} />
                  <button
                    onClick={isConnected ? disconnectSession : initiateConsultation}
                    className={`mic-button ${getMicClass()}`}
                    title={isConnected ? 'Disconnect' : 'Connect to Curator'}
                  >
                    <svg className="mic-icon" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                      <rect x="9" y="2" width="6" height="11" rx="3" fill="currentColor" />
                      <path d="M19 10c0 3.5-2.5 6.4-5.8 6.9V20h2.3c.6 0 1 .4 1 1s-.4 1-1 1H8.5c-.6 0-1-.4-1-1s.4-1 1-1h2.3v-3.1C7.5 16.4 5 13.5 5 10c0-.6.4-1 1-1s1 .4 1 1c0 2.8 2.2 5 5 5s5-2.2 5-5c0-.6.4-1 1-1s1 .4 1 1z" fill="currentColor" />
                    </svg>
                  </button>

                  <div className="waveform-container right-wave">
                    <div className="waveform-bar bar-6"></div>
                    <div className="waveform-bar bar-7"></div>
                    <div className="waveform-bar bar-8"></div>
                    <div className="waveform-bar bar-9"></div>
                    <div className="waveform-bar bar-10"></div>
                  </div>
                </div>

                <div className="connection-action">
                  <p className="tap-to-start-text">
                    {isConnected ? 'TAP TO END CONVERSATION' : 'TAP TO START CONVERSATION'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
