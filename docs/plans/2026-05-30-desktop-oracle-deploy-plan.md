# Desktop + Oracle-Hosted Backend — Accurate Deployment Plan (2026-05-30)

> Supersedes (does not delete) `2026-05-29-desktop-hosted-backend-reference-plan.md`.
> That file stays as the reference snapshot. This is the actionable plan.
> `[Agent: Claude Code]` — re-read `AGENTS.md` + `HANDOFF.md` before executing.

## STATUS BOARD (updated 2026-05-30)

| Phase | What | Status | Commit |
|---|---|---|---|
| **F** | Git secret/PII cleanup (untrack db/jsonl, ignore runtime_providers.json keys) | ✅ **DONE** | `bed7bcf` |
| **B** | Lean `requirements-desktop.txt` — boot-proven, 209 MB, no torch | ✅ **DONE** | `76bf965` |
| **A** | Config-driven backend URL (kill 3 hardcoded localhost) | ✅ **DONE** | `c4c7209` |
| **G** | True per-session BYOK (keys sent per WS session, no overwrite) | ✅ **CODE DONE** (offline-verified; awaits 2-desktop live test) | uncommitted |
| **C** | Minimal auth (shared token) + Caddy TLS/WSS | 🟡 **CODE DONE** (C1 token gate offline-verified; C2 Caddyfile ready, needs VM) | uncommitted |
| **D** | Oracle A1 VM stand-up (VM, firewall, systemd, DNS `api.balaastratech.com`) | 🟡 **ARTIFACTS READY** (deploy/ scripts+units+DEPLOY.md; awaits user's Oracle actions) | uncommitted |
| **E** | Package unsigned `.exe` + GitHub Release + INSTALL.md | ⬜ TODO | — |
| **H** | Verify mute works in the PACKAGED app (`.ps1` resourcesPath) | ⬜ TODO | — |

**Verified-but-not-yet-live (carry-over checks):**
- Phase A: not yet run via `npm start` — confirm overlay+full connect (localhost dev / prod default).
- Phase B: boot-tested on Windows venv; re-run install+boot on Oracle linux/aarch64.

**Recommended remaining order:** D (get it hosted + live) → G (per-session BYOK for concurrent testers) → C (token+TLS, can fold into D's Caddy step) → E (package + release) → H (mute in packaged build).

**Key constraints to remember:**
- Deploy Oracle `.env` in **AI-Studio/BYOK mode** (`GOOGLE_GENAI_USE_VERTEXAI=False`, empty `GOOGLE_CLOUD_PROJECT`) — do NOT copy the user's local Vertex `.env`.
- Lean profile requires speaker-ID/SpeechBrain/PerfectListener/google_stt to stay **disabled** (their torch imports are absent).
- Domain: **balaastratech.com** → backend at `api.balaastratech.com`.

## Decisions locked with the user (2026-05-30)

| Decision | Choice |
|---|---|
| Backend location | **Hosted on Oracle Cloud Free Tier** (user already has a tenancy) |
| API keys / cost | **BYOK** — each user pastes their own keys in Settings; we host/pay nothing for AI usage |
| Audience | **Just me / testing** (solo, small) |
| Installer | **Unsigned + install instructions**, hosted free on **GitHub Releases** |
| Requirements | **New lean prod requirements file**, verified against real code; web frontend deps excluded |
| Scope | **Desktop app + backend ONLY.** `frontend/` (Next browser app) is out of scope, do not build/ship it. Do not delete it. |

Because it's BYOK + solo testing, we deliberately DROP the heavy parts of the old reference plan:
OTP/email auth, OCI Email Delivery, and SQLite multi-user ownership checks are **not** needed for v1.
Auth is reduced to a single shared bearer token (good enough for a private test box).

---

## Current repo reality (verified this pass)

- **Hardcoded localhost in 3 desktop files** — must become configurable:
  - `desktop/src/renderer/app.js:70` → `const BACKEND_WS_URL = "ws://localhost:8000/ws";`
  - `desktop/src/renderer/overlay.js:6` → same `ws://localhost:8000/ws`
  - `desktop/src/renderer/full.js:838` → `const BACKEND_HTTP = "http://localhost:8000";`
- **`backend/requirements.txt` is huge and heavy**: `torch==2.1.0`, `torchaudio`, `speechbrain`, `pyannote.audio`, `openai-whisper`, `wespeaker`, `k2` (via patch), `librosa`, `s3prl`, `peft`, `asteroid-filterbanks`, `onnxruntime`, `hdbscan`, `scipy`, `numpy<2`, `webrtcvad-wheels`, `pyttsx3`. Multi-GB. Won't fit comfortable free tiers and is slow to build on ARM.
- **Heavy imports are mostly LAZY** (inside functions) → strippable:
  - `speechbrain_service.py`: torch/speechbrain/torchaudio all imported inside methods.
  - `perfect_listener.py`: pyannote/asteroid/wespeaker/torch all lazy.
  - `voice_encoder.py`: resemblyzer lazy.
  - `stt_service.py`: `google.cloud.speech_v2` lazy (only on google_stt path).
- **Hard top-level imports that MUST stay**: `huggingface_hub` (`main.py:17-18`), `numpy` (imported at module top in `listener_agent.py:34`, `eagle_service.py:9`).
- **Module-top heavy imports — STARTUP RISK to verify**: `speaker_service.py:22-24` (`numpy`, `webrtcvad`, `torch`), `speaker_enrollment.py:14` (`torch`). If these are on the websocket/companion import chain, removing torch/webrtcvad breaks boot. **Must confirm before trusting lean requirements (Task B1).**
- **Backend defaults to Vertex** (`GOOGLE_GENAI_USE_VERTEXAI=True`) which needs GCP creds — not portable. BYOK path = **AI Studio** (key-only) already exists (`runtime_config.google_backend()` + Settings → Advanced → Google backend).
- **No auth** on `/ws` or the REST API.
- **Secrets / PII committed or staged** (security cleanup needed):
  - `backend/data/negotiation_sessions.db` (tracked, modified) — conversation persistence.
  - `backend/data/logs/copilot_conversation_audit.jsonl` (tracked, modified) — full transcript audit log = PII.
  - `backend/data/runtime_providers.json` (untracked) — may contain pasted API keys.
  - Real `backend/.env` likely holds live keys — confirm it is gitignored.

---

## Security / cleanup findings that need your attention

1. **PII + secrets in git.** The audit `.jsonl`, the `.db`, and `runtime_providers.json` should be removed from tracking and gitignored. If real keys were ever committed, they must be rotated. (High priority.)
2. **CORS is wide open** (`allow_methods=["*"], allow_headers=["*"]`, broad origins incl. `null`/`file://`). Fine for desktop, but combined with no auth + a public IP = anyone who finds the host can drive your AI. The shared bearer token + firewall fixes this.
3. **No transport security yet.** `ws://` is plaintext. Hosting on a public IP means audio/transcripts travel unencrypted. Caddy in front gives free auto-HTTPS/WSS (`wss://`).
4. **`runtime_providers.json` stores API keys in plaintext on disk.** Acceptable on a single-user box you control; document it, lock file perms, never commit it.
5. **Debug/dev scripts shipped in backend** (`check_device.py`, `fix_torchaudio.py`, `verify_*.py`, `download_*.py`, `*.bck`, `backups/`). Not security-critical but should be excluded from the deploy image to keep it lean and reduce attack surface.
6. **`/api/log` accepts arbitrary frontend payloads** into logs — low risk (log injection), note only.

---

## Plan of work (phased)

### Phase A — Desktop config: kill hardcoded localhost (small, do first)
- **A1.** Add a single source of truth for the backend URL in the desktop app. Options: read from `desktop/.env` (`COMPANION_BACKEND_WS` / `COMPANION_BACKEND_HTTP`) via the existing `dotenv` dep, fall back to `ws://localhost:8000/ws` for dev. Wire it through `preload.js` so renderer files read it from a bridge instead of a literal.
- **A2.** Replace the 3 literals (`app.js:70`, `overlay.js:6`, `full.js:838`) with the resolved value.
- **A3.** Add the shared bearer token to the WS connect + REST calls (header or `?token=` query for WS, since browsers/Electron WS can't set arbitrary headers easily — use a query param or the existing ws-ticket idea simplified to one static token).
- **Verify:** `node --check` on all touched files; start desktop pointed at localhost backend → still connects.

### Phase B — Lean backend requirements (the file you asked for)
- **B1. (GATE) Verify the real startup import chain.** Trace what `app.main` → `app.api.websocket` → `companion_runtime` → `listener_agent` / `speaker_service` import at **module top**. Confirm whether `torch`/`webrtcvad`/`numpy` are mandatory for boot or only lazy. This determines whether the lean file can omit torch.
- **B2.** Create `backend/requirements-desktop.txt` (prod/hosted profile) containing ONLY what the live BYOK+Deepgram path needs. Expected set (to be confirmed by B1):
  - Core: `fastapi`, `uvicorn[standard]`, `websockets`, `pydantic`, `pydantic-settings`, `python-dotenv`, `pillow`, `python-json-logger`, `asgi-correlation-id`, `httpx`.
  - AI/providers (BYOK): `google-genai`, `openai`, `anthropic`.
  - Hard imports: `huggingface_hub` (used by main.py shim), `numpy` (module-top in listener_agent).
  - STT: Deepgram is called over HTTP/WebSocket via `httpx`/`websockets` (no SDK needed — confirm).
  - **Excluded** (web/heavy/diarization, all lazy): `torch`, `torchaudio`, `speechbrain`, `pyannote.audio`, `openai-whisper`, `wespeaker`, `s3prl`, `peft`, `asteroid-filterbanks`, `onnxruntime`, `hdbscan`, `librosa`, `scipy`, `webrtcvad-wheels`, `resemblyzer`, `pyttsx3`, `google-cloud-speech`.
- **B3.** Make the few heavy module-top imports safe when absent: guard `speaker_service.py` / `speaker_enrollment.py` top imports behind try/except or move them lazy, IFF B1 shows they're on the boot path. Set prod env `SPEECHBRAIN_ENABLED=False`, `SPEAKER_RECOGNITION_ENABLED=False`, `PERFECT_LISTENER_ENABLED=False`, `TRANSCRIPTION_PROVIDER=deepgram`, `GOOGLE_GENAI_USE_VERTEXAI=False` so no heavy path is invoked.
- **B4.** Keep the original `requirements.txt` untouched as the full local-dev profile (do not delete).
- **Verify:** fresh venv install of `requirements-desktop.txt` → `uvicorn app.main:app` boots → `/health` 200 → a desktop session with a pasted Deepgram + Google AI Studio key transcribes and gets an AI reply. This is the real acceptance test for the lean file.

### Phase C — Minimal auth + transport (solo-safe, not OTP)
- **C1.** Add a single `COMPANION_SHARED_TOKEN` env on the backend. Reject `/ws` and sensitive REST without it. (One static secret; no email/OTP — that was overkill for solo testing.)
- **C2.** Front the backend with **Caddy** for automatic free HTTPS/WSS (Let's Encrypt). Needs a hostname — use a free DNS (e.g. DuckDNS/nip.io) pointed at the Oracle public IP, or a free subdomain.
- **Verify:** `wss://<host>/ws?token=…` connects from the packaged desktop app; missing/wrong token rejected.

### Phase D — Oracle Cloud deployment (I will walk you through, step by step)
- **D1.** Create an **Ampere A1 Flex** VM (1–2 OCPU / 6–12 GB is plenty for the lean backend) in a region with capacity (Ashburn/Phoenix most reliable). Ubuntu LTS image.
- **D2.** Open ports: ingress 80/443 in the OCI Security List **and** `iptables`/`ufw` on the VM (Oracle images block by default — common gotcha).
- **D3.** Install Python 3.11+, clone repo (or copy backend only), create venv, `pip install -r requirements-desktop.txt`.
- **D4.** Run uvicorn under `systemd` (auto-restart, starts on boot). Caddy as a second systemd service reverse-proxying to `127.0.0.1:8000` with auto-TLS.
- **D5.** Avoid the **idle-reclaim** trap (Oracle stops <10% CPU/network instances over 7 days): a tiny cron/health pinger keeps it alive, or accept restarts.
- **D6.** Put real keys only in the VM's `backend/.env` (BYOK means users paste their own anyway; backend keys can stay empty). Lock file perms `chmod 600`.
- **Verify:** from your PC, `curl https://<host>/health` 200; desktop app connects over `wss://`.

### Phase E — Desktop packaging + free distribution
- **E1.** Set the packaged production backend URL (`wss://<host>/ws`) as the default in the desktop config, with a hidden dev override for localhost.
- **E2.** `npm run dist` (electron-builder, NSIS target already configured) → produces an `.exe` installer. Confirm `audio-isolator.ps1` ships via `extraResources` (already configured).
- **E3.** Create a **GitHub Release**, upload the `.exe` (free hosting). Write `INSTALL.md`: download → SmartScreen → "More info → Run anyway" → first-run: paste your API keys in Settings → pick providers → start.
- **E4.** (Deferred) signing via Azure Trusted Signing or EV cert to remove SmartScreen — not now.
- **Verify:** install on a clean Windows session from the GitHub Release, run, connect to Oracle backend, complete a session.

### Phase F — Security/PII cleanup (do alongside, before any push)
- **F1.** `git rm --cached` the `.db`, the audit `.jsonl`, and `runtime_providers.json`; add to `.gitignore`. Confirm `backend/.env` is gitignored.
- **F2.** If any real key was ever committed (check history), **rotate it**.
- **F3.** Add a `.dockerignore`/deploy-exclude for dev scripts, `backups/`, `*.bck`, `tests/`, eval dirs so they don't ship to the VM.

---

### Phase G — True per-session BYOK (multi-tenant keys) [user-chosen 2026-05-30]
**Problem (verified):** `runtime_config` reads ONE global `backend/data/runtime_providers.json` for the whole process. Transcription/AI ARE isolated per session (each WS → own `session_id` → own `NegotiationSession`, `listener_agent`, `DeepgramStreamSession.get(session_id)`, Gemini Live). But **keys/provider selections are global** → with 2+ concurrent testers, the last `Save` wins and everyone uses that key. User chose **per-session keys sent from the desktop**.

- **G1. Desktop:** store the user's keys + per-slot provider/model locally (Windows-safe storage / `desktop/.env` for dev). Send them once on WS connect — either as `?` is unsafe for secrets, so send a `CONFIG`/`PROVIDER_CONFIG` text message immediately after `CONNECTION_ESTABLISHED`, before `start`. MUST be over `wss://` (Phase C/Caddy) so keys aren't plaintext on the wire.
- **G2. Backend store:** add `session.provider_overrides` (keys + slot selections + google_backend) populated from that message; never write them to the global JSON.
- **G3. Resolver plumbing:** make `runtime_config` resolvers session-aware. Least-invasive: a `contextvars.ContextVar` set at the top of per-session message handling (and around `start_live_preconnect`) so existing module-level `_rc.provider_for()/api_key_for()/google_api_key()/google_use_vertex()/google_backend()/google_live_models()` calls read the current session's overrides first, then fall back to env. Touch points (from prior multi-provider work): `gemini_client.py` (vision, advice, `open_live_session`), `listener_agent.py`, `next_move_cache.py`, `translation.py`, `companion_runtime.py` (`_deepgram_streaming_enabled`/`_deepgram_api_key`/`_resolved_stt_provider`), `stt_service.py` (`_resolve_stt_selection`), `deepgram_stream.py`.
- **G4. Live preconnect:** `websocket.py:110` calls `start_live_preconnect(session, settings.GEMINI_API_KEY, ...)` with the ENV key. Defer preconnect until the per-session config arrives, or re-key the Live session from `session.provider_overrides`.
- **G5. Keep the global JSON path** working when `PROVIDER_RUNTIME_OVERRIDE_ENABLED` + no session override (solo/dev). Reversible.
- **Verify:** two desktops with DIFFERENT keys connect concurrently → each session's AI calls use its OWN key (assert via traces); neither overwrites the other; global JSON untouched. Bad/missing key fails only that session.

### Phase H — Mute verification in the PACKAGED app (carry-over concern)
- Mute is desktop-local (Zoom Alt+A via `audio-isolator.ps1`), independent of backend/multi-tenancy.
- **H1.** Verify `main.js` resolves the `.ps1` via `process.resourcesPath/scripts/audio-isolator.ps1` when packaged (electron-builder `extraResources`), not the dev `__dirname` path — otherwise mute silently dies in the installer.
- **H2.** Document the one-time per-tester step: Zoom → Settings → Keyboard Shortcuts → enable **Global Shortcut** for Mute/Unmute. Provide VB-Cable as fallback.
- **Verify:** installed build, hold orb on a Zoom call → Zoom mutes; desktop console logs `hotkey send-keys ... result ok:true`.

### Code-sharing reality (answer recorded)
- Backend source: private (VM only), never distributed.
- Desktop: ships compiled, but `app.asar` is unpackable → JS readable. Acceptable for testing. Hard rule: **no secrets baked into the desktop build** (BYOK satisfies this). Valuable logic stays backend-side.

## Open questions before/within execution
1. **B1 result** decides if `torch` can truly be dropped or must stay as a stripped CPU wheel. (Resolve first.)
2. Do you have a **hostname** preference for HTTPS, or should I set up a free DuckDNS subdomain? (Needed for Caddy TLS; raw IP can't get a normal cert.)
3. Confirm the desktop app should **default to the Oracle URL** in the shipped build (yes per plan) vs. ask on first run.
4. Is Deepgram reached via raw `httpx`/`websockets` (no SDK) — confirm in B2 so the lean file is correct.

## Test matrix (acceptance)
- Lean venv boots backend; `/health` 200; no torch/speechbrain import error.
- Desktop (localhost) session: Deepgram transcript + AI Studio reply works BYOK.
- `wss://` over Caddy from packaged app; bad token rejected.
- Oracle VM survives reboot (systemd) and isn't reclaimed (pinger).
- Clean-Windows install from GitHub Release connects to Oracle and completes a session.
- No secrets/PII tracked in git; dev scripts excluded from deploy.

## Sources (2026 research)
- Oracle Free Tier A1 limits/capacity/idle-reclaim: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm , https://fullmetalbrackets.com/blog/oci-free-tier-breakdown
- Free backend hosting comparison (cold starts/WebSocket): https://snapdeploy.dev/blog/free-backend-hosting-2026-apis-servers , https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026
- Koyeb/Fly free tier reality: https://www.koyeb.com/docs/faqs/pricing
- Electron distribution + signing/SmartScreen: https://www.electronjs.org/docs/latest/tutorial/code-signing , https://dev.to/raxxostudios/how-to-build-and-distribute-an-electron-desktop-app-in-2026-24nk
</content>
</invoke>


