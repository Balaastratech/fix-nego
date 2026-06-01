# Desktop Hosted Backend Reference Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans only after this reference plan is re-evaluated against the full current codebase.

**Goal:** Preserve the current hosted-backend plus desktop-client deployment direction as a reference snapshot while product scope is still changing.

**Architecture:** Windows desktop companion connects to a hosted FastAPI backend over authenticated WSS. The backend owns provider keys, invite-only OTP access, optional persistence, and Oracle Cloud Free Tier deployment assumptions.

**Tech Stack:** Electron, FastAPI, WebSocket, Gemini/Vertex, Deepgram, OCI Compute, OCI Email Delivery, NSIS.

---

## Re-evaluation Required Before Implementation

This plan is a reference snapshot only. Do not implement it directly without re-checking the full current codebase first.

Before changing code, re-read `AGENTS.md` and `HANDOFF.md`, then re-evaluate the full repository end to end. Do not rely only on particular files or the file paths named in this plan, because the desktop/backend/frontend wiring, product scope, active privacy strategy, persistence behavior, packaging flow, and deployment assumptions may change before implementation.

Re-check especially:

- Which desktop features are still kept or removed.
- Whether persistence is still needed.
- Whether `PERSISTENCE_MODE=none|sqlite` is still the right design.
- Whether backend OTP auth is still preferred.
- Whether Oracle Cloud Free Tier is still the deployment target.
- Whether the desktop app still hardcodes localhost or dev-only endpoints anywhere.
- Whether browser/frontend code is still out of product scope.
- Whether `HANDOFF.md` contains newer context that supersedes this plan.

After re-evaluation, update this plan before implementation.

## Summary

- Target product: Windows desktop companion only.
- Keep for now: meeting source selection, local/remote transcripts, hold-to-ask, AI replies, vision frames, language controls, pause/resume, and privacy routing.
- Hosting direction: Oracle Cloud Free Tier first, with an OCI Ampere A1 VM behind HTTPS/WSS.
- Current repo reality from the planning pass: Electron desktop still uses local/dev backend assumptions in places, backend `/ws` is anonymous, and SQLite session persistence is actively used by multiple backend services.
- Shared server-side provider keys are the v1 default. BYOK is not part of this reference plan.

## Key Changes

- Add backend-owned invite OTP auth:
  - `POST /api/auth/request-otp`
  - `POST /api/auth/verify-otp`
  - `POST /api/auth/ws-ticket`
  - Store invited emails in server config for v1.
  - Send OTP through OCI Email Delivery/SMTP.
  - Keep OTPs and one-use WebSocket tickets in memory with short TTLs.
  - Require auth before creating or preconnecting a negotiation session.

- Make persistence configurable:
  - Add `PERSISTENCE_MODE=none|sqlite`.
  - Default first Oracle desktop deployment to `none`.
  - Implement a null session store for no database writes, no session history restore, and no SQLite file.
  - Keep SQLite behind `PERSISTENCE_MODE=sqlite`; if enabled, add user ownership checks before session restore/list/get.

- Prepare backend for desktop-only hosted deployment:
  - Keep Gemini Live, Vertex/Gemini advice/vision, Deepgram streaming, FastAPI, WebSocket, and current companion runtime paths.
  - Create a lean production dependency profile that excludes browser-era or disabled stacks such as SpeechBrain, pyannote, Whisper, torch/torchaudio, and diarization dependencies unless re-evaluation proves they are still required.
  - Build and run a linux/arm64 backend image on OCI Ampere A1.
  - Put Caddy or Nginx in front for TLS, WSS, and health checks.

- Update desktop distribution assumptions:
  - Replace hardcoded localhost/dev endpoints with a packaged fixed production WSS URL.
  - Keep any local backend override hidden or developer-only.
  - Add first-run wizard for email OTP login, backend health, mic/screen permissions, meeting app checks, and privacy route validation.
  - Store long-lived desktop auth state in Windows-safe storage, with short-lived tokens/tickets in memory.
  - Keep NSIS installer flow; signing and auto-update are release hardening after the first internal installer.

- Product cleanup direction:
  - Do not ship the Next browser frontend as the main product.
  - Gate or remove browser-only deployment docs and flows from the desktop release path.
  - Do not delete frontend code until a later cleanup task explicitly confirms removal scope.

## Test Plan

- Backend:
  - OTP request/verify success.
  - Uninvited email rejected.
  - Expired OTP rejected.
  - One-use WebSocket ticket cannot be reused.
  - WebSocket rejects missing, invalid, and used tickets before session creation.
  - `PERSISTENCE_MODE=none` performs no SQLite writes and disables history restore.
  - `PERSISTENCE_MODE=sqlite` persists sessions with user ownership and blocks cross-user restore.

- Desktop:
  - Packaged backend URL is used instead of localhost.
  - First-run wizard completes login and reaches ready state.
  - Start, pause, resume, end, source selection, hold-to-ask, vision, language controls, and privacy routing still send the existing desktop companion payloads.

- Deployment:
  - Backend Docker image builds for linux/arm64.
  - Hosted health endpoint passes behind TLS proxy.
  - Hosted WSS works from packaged desktop app.
  - OCI Email Delivery sends OTP to an invited address.
  - Backend can start with no database file when `PERSISTENCE_MODE=none`.

## Assumptions

- The production backend URL will be known before packaging.
- The first hosted release prioritizes a working desktop pilot over browser parity.
- Oracle Free Tier capacity may be unavailable in some regions; deployment docs should include a fallback region or retry note.
- No local LLM is used in the desktop product path.
- Provider keys remain on the hosted backend only.
