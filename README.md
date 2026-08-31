# AI Negotiation Copilot

A real-time AI meeting/negotiation copilot. It listens in on a live conversation, transcribes and analyzes it as it happens, and gives you private, spoken coaching — prices, sentiment, leverage points, and direct answers to questions you ask it mid-conversation without the other party hearing.

Started as a submission for the **Gemini Live Agent Challenge**; has since grown into a two-client product built around one backend:

- **Desktop Companion** (`desktop/`) — Windows Electron app, the actively developed client. Binds to a meeting window (Zoom/Meet/Teams/etc.), captures your mic and the meeting audio as separate sources, and plays AI replies only to you.
- **Browser Dashboard** (`frontend/`) — the original hackathon UI. Runs entirely in the browser using your mic. Lighter to set up, good for a quick demo, but not the client new features land on first.

Both talk to the same **FastAPI backend** (`backend/`) over a single WebSocket.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Repo Layout](#repo-layout)
- [Prerequisites](#prerequisites)
- [Install & Run](#install--run)
  - [1. Backend](#1-backend)
  - [2. Desktop Companion (primary client)](#2-desktop-companion-primary-client)
  - [3. Browser Dashboard (alt client)](#3-browser-dashboard-alt-client)
- [Environment Variables](#environment-variables)
- [WebSocket API](#websocket-api)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Project Status & Known Gaps](#project-status--known-gaps)
- [License](#license)

---

## What It Does

- **Dual-model architecture**: Gemini Live handles the real-time voice conversation (including native-audio spoken answers); a background Gemini Flash "listener" agent continuously extracts prices, sentiment, and context from the conversation and injects that intel into the Live session so its advice is grounded, not generic.
- **Multi-provider STT**: Google Cloud Speech, Deepgram (nova-3, multi-language), or Gemini Live's own native transcription — selectable per deployment via `TRANSCRIPTION_PROVIDER`.
- **BYOK multi-provider text/vision layer**: swap the reasoning/vision/fast-text/STT provider per slot between Google, OpenAI, Anthropic, Groq, DeepSeek, and OpenRouter without a restart, via an in-app Settings page or `.env`.
- **Hold-to-Ask**: hold a button/hotkey to privately ask the AI a direct question mid-conversation. The desktop app mutes your forwarded mic to the meeting during the hold (via a virtual audio cable) so only the AI hears the question; it answers back with native spoken audio.
- **Optional speaker recognition**: SpeechBrain ECAPA-TDNN voice-print enrollment + pyannote overlap detection + Conv-TasNet speech separation, for distinguishing "you" from "them" automatically instead of manual speaker-tagging. Heavy (torch-based), off by default in the hosted profile.
- **Session outcome summary**: savings/effectiveness scoring at the end of a session.
- **Auto-reconnect** on Gemini Live session drops, with degraded-mode signaling to the client.

## Architecture

```
                    ┌─────────────────────────┐
                    │   FastAPI backend        │
   Desktop Companion│   (backend/app/)          │  Browser Dashboard
   (Electron, Win)  │                           │  (Next.js, any OS)
        │           │  single WebSocket: /ws    │        │
        └──────────►│  REST: /health, /api/*   │◄────────┘
       LOCAL_MIC_PCM│                           │  mic PCM (browser)
      REMOTE_APP_PCM│  ┌─────────────────────┐  │
        ASK_AI_PCM  │  │ Gemini Live session  │  │  AI_RESPONSE / audio
        SCREEN_FRAME│  │ (native audio)       │  │  TRANSCRIPT_UPDATE
                    │  └─────────┬───────────┘  │  STRATEGY_UPDATE
                    │            │ intel         │
                    │  ┌─────────▼───────────┐  │
                    │  │ Listener agent        │  │
                    │  │ (Gemini Flash, bg)    │  │
                    │  └───────────────────────┘  │
                    │  STT: Google / Deepgram      │
                    │  Speaker-ID: SpeechBrain(opt)│
                    └─────────────────────────────┘
```

The desktop app tags every audio chunk with its source (`LOCAL_MIC_PCM` = you, `REMOTE_APP_PCM` = the meeting/counterparty, `ASK_AI_PCM` = a private Hold-to-Ask question) so the backend never has to guess who's speaking on that path. The browser dashboard instead relies on manual "User" / "Counterparty" speaker buttons (or optional speaker-recognition once enrolled).

## Features

- Real-time voice capture and transcription for both speakers
- Live AI coaching via Gemini Live with spoken responses
- Background market research via Google Search grounding
- Proactive Copilot mode — the AI can alert you to critical moments unprompted
- Hold-to-Ask — hold a button/hotkey to ask the AI a private question mid-conversation
- Response modes: detailed "advice" vs. tactical one-line "command"
- Multi-language support (Deepgram multi-language + response-language translation)
- BYOK: bring your own API keys for any supported provider, switch per session
- Session outcome summary (savings, effectiveness score)
- Auto-reconnect on Gemini Live session drops with degraded-mode signaling
- Desktop-only: system/meeting-window audio capture, screen-frame vision context, VB-Cable-based mic isolation during Hold-to-Ask

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn, WebSockets |
| Conversational AI | Google Gemini Live (native audio) + Gemini Flash (background listener) |
| STT | Google Cloud Speech, Deepgram nova-3 (Sarvam AI streaming STT integration in progress, not yet wired into config) |
| Speaker ID (optional) | SpeechBrain ECAPA-TDNN, pyannote.audio, WeSpeaker, Conv-TasNet |
| Multi-provider BYOK | OpenAI, Anthropic, Groq, DeepSeek, OpenRouter (OpenAI-compatible adapter) |
| Auth | Clerk (JWT) + app-session tokens + shared bearer token for hosted deployments |
| Desktop client | Electron 31, native Windows audio routing, VB-Cable integration |
| Browser client | Next.js 15, React 19, TypeScript, TailwindCSS, Web Audio API (AudioWorklet), VAD |
| Logging | Structured JSON logging + per-session trace files + conversation audit log |
| Testing | pytest (backend), Vitest (frontend) |
| Deployment | Oracle Cloud (Always-Free Ampere A1 VM) behind Caddy, systemd-managed |

## Repo Layout

```
fix-nego/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point, startup patches, CORS, /health, /api/ready
│   │   ├── config.py            # All settings (Pydantic Settings) — see this for the full env var list
│   │   ├── api/                 # REST + WebSocket routes (auth, providers, websocket)
│   │   ├── models/               # Pydantic message/session models
│   │   ├── services/             # Gemini client, negotiation engine, STT, speaker-ID, providers, etc.
│   │   └── utils/                 # Logging, tracing, patches
│   ├── tests/                    # pytest suite
│   ├── requirements.txt          # Full local/research profile (adds torch/SpeechBrain/pyannote)
│   ├── requirements-desktop.txt  # Lean BYOK profile — what production actually runs
│   ├── .env.example              # Full annotated env var reference
│   └── Dockerfile
│
├── desktop/                      # Electron companion app (primary client)
│   ├── src/                      # main.js, preload.js, overlay/dashboard renderer
│   ├── scripts/                  # VB-Cable installer, PowerShell helpers
│   └── .env.example
│
├── frontend/                     # Next.js browser dashboard (alt client)
│   ├── app/, components/, hooks/, lib/, utils/
│   └── tests/                    # Vitest suite
│
├── deploy/                       # Oracle Cloud production deploy (Caddy, systemd, setup script)
│   └── DEPLOY.md                 # Full VM provisioning walkthrough
│
├── docs/code_map/                # Structured code map with path:line references — read this to
│                                  # navigate the codebase before grepping around blind
│
└── xr-application/                # Separate side project (pitch-deck generator) — not part of the core product
```

`docs/code_map/00_INDEX.md` is the maintained, authoritative map of every backend service, settings flag, and known gotcha — check it before spelunking through `services/` yourself.

## Prerequisites

- **Python 3.11+**
- **Node.js 18+** (for the browser dashboard) — https://nodejs.org
- **A Google Gemini API key** (AI Studio) — https://aistudio.google.com/app/apikey — or a GCP project with Vertex AI enabled
- To run the **desktop companion**: **Windows 10/11** (system-audio capture and VB-Cable integration are Windows-only)
- Optional, for true Hold-to-Ask privacy on desktop: **[VB-CABLE](https://vb-audio.com/Cable/)** virtual audio driver (bundled installer script provided)
- Optional BYOK keys for any provider you want to use instead of/alongside Gemini: Deepgram, OpenAI, Anthropic, Groq, DeepSeek, OpenRouter

## Install & Run

### 1. Backend

The backend has **two dependency profiles** — pick one, don't install both into the same environment:

| Profile | File | What it adds | When to use |
|---|---|---|---|
| **Lean / BYOK** | `requirements-desktop.txt` | Nothing heavy — no torch, no ML | Recommended. This is what production actually runs. Speaker-recognition features stay off. |
| **Full / research** | `requirements.txt` | torch, SpeechBrain, pyannote, WeSpeaker, Conv-TasNet, Whisper | Only if you want local speaker diarization / voice-print recognition. Multi-GB install, pinned `torch==2.1.0` + `numpy<2` (do not upgrade — `k2`/torch ABI compatibility). |

```bash
git clone https://github.com/Balaastratech/fix-nego.git
cd fix-nego/backend

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements-desktop.txt   # or requirements.txt for the full profile

cp .env.example .env
```

Edit `backend/.env` — at minimum:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_GENAI_USE_VERTEXAI=False
TRANSCRIPTION_PROVIDER=deepgram
DEEPGRAM_API_KEY=your_deepgram_api_key_here   # only if TRANSCRIPTION_PROVIDER=deepgram
CORS_ORIGINS=http://localhost:3000
```

`.env.example` is fully annotated with every setting (STT tuning, speaker-recognition thresholds, auth, feature flags) — read it before touching `config.py` directly.

Run it:

```bash
uvicorn app.main:app --reload --port 8000
```

Verify:

```bash
curl http://localhost:8000/health      # {"status": "healthy"}
curl http://localhost:8000/api/ready   # {"ready": true, ...}
```

### 2. Desktop Companion (primary client)

Windows only.

```powershell
cd desktop
npm install
copy .env.example .env
```

Edit `desktop/.env` to point at your local backend:

```env
COMPANION_BACKEND_WS=ws://localhost:8000/ws
```

```powershell
npm start
```

For real Hold-to-Ask privacy (the meeting app never hears your private question), install VB-Cable and route the meeting app's mic input through it:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-vbcable.ps1
```

Then in the app: pick the meeting window to capture, pick your listening output for AI replies, pick the virtual-cable output as the meeting-route output, and select that virtual cable as the microphone inside Zoom/Meet/Teams. Full walkthrough in [`desktop/README.md`](desktop/README.md).

### 3. Browser Dashboard (alt client)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`, grant microphone access, and use the "User"/"Counterparty" buttons to tag each speaker manually (there's no automatic source-tagging on this client the way there is on desktop). To point it at a non-default backend, create `frontend/.env.local`:

```env
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

## Environment Variables

Each surface ships a fully annotated example file — treat these as the source of truth, not the table below:

- [`backend/.env.example`](backend/.env.example) — every backend setting (STT, speaker-recognition thresholds, auth, feature flags)
- [`desktop/.env.example`](desktop/.env.example) — backend WS URL, privacy-mode, VB-Cable toggle
- [`deploy/.env.oracle.example`](deploy/.env.oracle.example) — the lean production profile used on the live Oracle deployment

The handful that matter for a first local run:

| Variable | Where | Required | Default | Description |
|---|---|---|---|---|
| `GEMINI_API_KEY` | backend | Yes (unless using Vertex) | — | Google AI Studio key |
| `GOOGLE_GENAI_USE_VERTEXAI` | backend | No | `True` | `False` = AI Studio/BYOK (no GCP project needed), `True` = Vertex |
| `TRANSCRIPTION_PROVIDER` | backend | No | `google_stt` | `google_stt` or `deepgram` |
| `DEEPGRAM_API_KEY` | backend | If using Deepgram | — | Required when `TRANSCRIPTION_PROVIDER=deepgram` |
| `CORS_ORIGINS` | backend | No | `http://localhost:3000` | Comma-separated allowed browser origins |
| `SPEAKER_RECOGNITION_ENABLED` | backend | No | `True` in `requirements.txt` profile, must be `False` on the lean profile | Gates the whole torch/SpeechBrain path |
| `COMPANION_SHARED_TOKEN` | backend + desktop | No | empty (auth disabled) | Set matching values on both sides to gate a hosted backend |
| `AUTH_REQUIRED` | backend | No | `False` | Enables Clerk JWT login |
| `COMPANION_BACKEND_WS` | desktop | No | production URL | Point at `ws://localhost:8000/ws` for local dev |
| `NEXT_PUBLIC_WS_URL` | frontend | No | `ws://<host>:8000/ws` | Backend WebSocket URL |

## WebSocket API

All client↔server traffic goes over a single WebSocket at `/ws`: JSON text frames for control messages, binary frames for raw PCM audio. This is a representative sample, not the full catalog — see `docs/code_map/04_backend_api_models_providers.md` and `backend/app/models/messages.py` for every message type.

**Client → Server** (JSON): `PRIVACY_CONSENT_GRANTED`, `START_NEGOTIATION`, `VISION_FRAME`, `SET_RESPONSE_LANGUAGE`, `SET_LANGUAGE_PROFILE`, `MEETING_BINDING`, `END_NEGOTIATION`
**Client → Server** (binary, source-tagged): `LOCAL_MIC_PCM`, `REMOTE_APP_PCM`, `ASK_AI_PCM`

**Server → Client**: `CONNECTION_ESTABLISHED`, `CONSENT_ACKNOWLEDGED`, `SESSION_STARTED`, `SESSION_RESTORED`, `SESSION_RECONNECTING`, `TRANSCRIPT_UPDATE`, `STRATEGY_UPDATE`, `AI_RESPONSE`, `AI_DEGRADED`, `HOLD_TO_ASK_STATE`, `MEETING_BINDING_UPDATE`, `CAPTURE_HEALTH_UPDATE`, `LANGUAGE_UPDATE`, `VISION_STATUS`, `PERSISTENCE_STATUS`, `AUDIO_INTERRUPTED`, `ERROR`
**Server → Client** (binary): 24kHz Int16 PCM (Gemini voice response)

## Testing

```bash
# Backend
cd backend
venv\Scripts\activate           # or source venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v

# Frontend
cd frontend
npm test                  # run once
npm run test:coverage     # with coverage
npm run test:ui           # interactive UI
```

## Deployment

Production runs the **lean profile** (`requirements-desktop.txt`) on an **Oracle Cloud Always-Free Ampere A1 VM**, behind Caddy for automatic HTTPS/WSS, managed by systemd. The full walkthrough — VM creation, firewall (two layers), DNS, env setup, the one-shot `setup-oracle.sh` provisioning script, verification, and rollback — is in [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

If you fork this to run your own hosted backend, set `COMPANION_SHARED_TOKEN` on both the VM and your desktop build — without it, anyone who finds the WebSocket URL can connect using their own BYOK keys.

## Troubleshooting

**Microphone not working (browser dashboard)**
- You must be on `http://localhost:3000` or an HTTPS origin — browsers block mic access elsewhere.
- Check the browser actually granted the permission prompt.

**WebSocket connection fails**
- Confirm the backend is up: `http://localhost:8000/health` → `{"status":"healthy"}`.
- Check `CORS_ORIGINS` in `backend/.env` includes your client's origin.
- If a shared token is set, a wrong/missing `COMPANION_SHARED_TOKEN` closes the WS during handshake with code `1008`.

**Gemini API errors**
- Verify `GEMINI_API_KEY` is set and valid.
- Confirm the model in `GEMINI_MODEL`/`GEMINI_LIVE_MODEL_AISTUDIO` is available for your account/region — the app auto-falls-back to `GEMINI_MODEL_FALLBACK` on session drops.

**Desktop: meeting app still hears me during Hold-to-Ask**
- The meeting app's microphone input must be the VB-Cable output, not your real mic — see `desktop/README.md`'s device-pairing pattern.
- `virtual_mic_helper_unavailable` degraded state means no virtual route output is selected in the app.

**Speaker recognition install fails (torch/numpy)**
- This only applies to the full `requirements.txt` profile. `torch==2.1.0` is pinned against `numpy<2` for `k2`/ABI compatibility — don't upgrade either independently.
- If you don't need automatic speaker diarization, use `requirements-desktop.txt` instead and skip this entirely.

**CORS errors in browser console**
- `CORS_ORIGINS` must exactly match the frontend origin including protocol and port, e.g. `CORS_ORIGINS=http://localhost:3000`.

## Project Status & Known Gaps

- The **desktop companion** is the actively developed client; the **browser dashboard** is the original hackathon UI and may lag behind on newer features (multi-provider BYOK, Hold-to-Ask native audio, meeting-window binding).
- Sarvam AI streaming STT (`backend/app/services/sarvam_stream.py`) is an in-progress integration, not yet wired into `config.py`'s provider validation.
- No `LICENSE` file is present yet — all rights are reserved by default until one is added.
- See `docs/code_map/` for a maintained, more granular list of dead code and open gotchas per subsystem.

## License

No license file yet. All rights reserved by the author until one is added.
