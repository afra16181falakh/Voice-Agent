# Sonorus

Sonorus is a real-time voice agent platform — a conversational AI that actually talks like a person, remembers context, answers questions grounded in a real knowledge base, and hands off to a human when it should. It ships as three coordinated pieces: a FastAPI backend running a cascaded voice pipeline, a React web app (landing page + admin telemetry dashboard), and a React Native mobile app.

## What it does

- **Personal Companion mode** — inbound, warm, emotionally aware conversation. Remembers context within a session and answers real questions grounded in a knowledge base instead of guessing.
- **Loan Reminder mode** — outbound calls where the agent speaks first, grounded in the specific customer record it's calling about, and negotiates rather than reading a script.
- **English + Hindi**, with natural code-switching mid-conversation.
- **Human hand-off** — recognizes financial hardship, disputes, and explicit requests for a person, and escalates cleanly instead of pushing through.
- **Live transcripts** and telemetry (latency, sentiment, session outcomes) visible in real time and logged for review.

## Architecture

```
backend/    FastAPI + PostgreSQL (pgvector) — the voice pipeline, auth, and all APIs
frontend/   React + Vite — public landing page and admin telemetry dashboard
mobile/     React Native (Expo) — push-to-talk mobile app
```

### Voice pipeline

A cascaded (not single black-box) pipeline, so every stage is independently measurable and swappable:

| Stage | Provider |
|---|---|
| Speech-to-text | Deepgram Nova-3 |
| Language model | Groq (Llama 3.3 70B) |
| Text-to-speech | Cartesia Sonic |

Local, fully free fallbacks (faster-whisper, Ollama, Piper) remain wired in and configurable via environment variables, for zero-cost/offline operation.

### Backend

- FastAPI, async SQLAlchemy, PostgreSQL with the `pgvector` extension for semantic search.
- JWT-based auth (email/password with email verification via Resend, plus Google Sign-In), PBKDF2 password hashing, and per-endpoint rate limiting — all stdlib-only, no extra crypto dependencies.
- A general-purpose knowledge base (embeddings via Gemini) that the agent grounds its answers in, with tool-calling support (e.g. `escalate_to_human`).
- Telemetry: conversation analytics, wellbeing/stress tracking, latency metrics, and an admin dashboard, backed by real data (not mocked once history exists).
- A lightweight push-to-talk REST API for the mobile app, separate from the WebSocket streaming path the web app uses.

### Frontend (web)

- Public landing page describing the product, plus a live demo widget.
- Admin dashboard: overview, employee wellbeing analytics, stress analytics, conversation trends, AI performance, and audit logs — gated behind admin login.
- Installable as a PWA.

### Mobile app

- Email/password + Google sign-in, with a hamburger-drawer navigation pattern.
- Push-to-talk voice calls with a live animated call screen (state-driven: listening / thinking / speaking).
- Call history (real per-user transcripts), knowledge base browsing, and a live stats dashboard.
- Ships over-the-air updates via EAS Update — most changes reach installed devices without a new APK.

## Getting started

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Create a `.env` file at the project root (see `backend/app/config.py` for the full list of settings) with at minimum:

```
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=sonorus_db

GROQ_API_KEY=...
DEEPGRAM_API_KEY=...
CARTESIA_API_KEY=...
GEMINI_API_KEY=...

JWT_SECRET=...
RESEND_API_KEY=...
```

Run it:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api`, `/sessions`, and `/ws` to the local backend (see `vite.config.ts`).

### Mobile

```bash
cd mobile
npm install
npx expo start
```

Update `mobile/src/config.ts` with your backend's reachable URL before running on a physical device. For a production build:

```bash
npx eas-cli build --platform android --profile preview
```

## Tech stack

**Backend:** FastAPI, SQLAlchemy (async), PostgreSQL + pgvector, Deepgram, Groq, Cartesia, Gemini (embeddings), Resend (email)
**Frontend:** React, TypeScript, Vite
**Mobile:** React Native, Expo, React Navigation, expo-audio, expo-updates
**Infra:** Railway (backend + database), EAS Build/Update (mobile)
