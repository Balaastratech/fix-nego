# Copilot Evaluation Harness

This harness tests the Live AI negotiation advisor with scripted, speaker-labeled text turns over the real backend WebSocket. It intentionally bypasses microphone, STT, and speaker recognition so failures point to advisor reasoning, prompt quality, and context handling.

## Prerequisites

Set this in `backend/.env` for evaluation runs only:

```env
EVAL_MODE_ENABLED=True
```

Start the backend from `backend`:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## Smoke Run

Run one or two scenarios without the LLM judge:

```powershell
.\venv\Scripts\python.exe scripts\run_copilot_eval.py --limit 2 --no-judge
```

## Full Run

Run the full portfolio with deterministic scoring plus the LLM judge:

```powershell
.\venv\Scripts\python.exe scripts\run_copilot_eval.py
```

Reports are written under:

```text
data/eval_reports/<run_id>/
```

Use `summary.json` for the pass/fail view and each scenario JSON for the exact transcript, user query, AI response, deterministic checks, and judge rationale.

## Audio Pipeline Eval

The audio eval suite is separate from the text-only copilot reasoning suite. It targets the real audio path:

```text
browser PCM -> VAD / UTTERANCE_END -> Google STT -> SpeechBrain speaker labeling -> transcript events
```

### Generate the synthetic corpus

```powershell
.\venv\Scripts\python.exe scripts\generate_audio_eval_corpus.py
```

This creates:

```text
evals/audio_fixtures/manifest.json
evals/audio_fixtures/wav/...
```

### Backend-only audio eval

This drives enrollment plus `AUDIO_CHUNK` / `UTTERANCE_END` directly over the backend websocket.

```powershell
.\venv\Scripts\python.exe scripts\run_audio_backend_eval.py --limit 2
```

Reports are written under:

```text
data/audio_eval_reports/backend/<run_id>/
```

### Browser/VAD audio eval

This drives the real frontend with synthetic microphone audio through the browser path. Start both backend and frontend first.

From `frontend`:

```powershell
npm run audio:eval -- --limit 2
```

Reports are written under:

```text
backend/data/audio_eval_reports/browser/<run_id>/
```
