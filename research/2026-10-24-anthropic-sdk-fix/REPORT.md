# Anthropic SDK break — real fix (job j3a27, 24-10-2026)

Lives at `C:\Balaastra\projects\negotiation-copilot\app\research\2026-10-24-anthropic-sdk-fix\` after merge.

## 1. Review of Codex job j0874 (the `<2` cap)
- Its evidence is right: SDK 1.17.0 raises `TypeError ... unexpected keyword argument 'temperature'`,
  0.105.2 passes. Reproduced here (old adapter + 1.17.0 → same TypeError, 3/3 adapter tests fail).
- Its conclusion is right too: `<2` does not fix it, so leave j0874 unmerged.
- What it missed: (a) the break is in **1.0.0**, not 2.0 (temperature is absent from
  `messages.create` in 1.0.0, 1.17.0 and 2.3.0 source); (b) a second break that no pin fixes
  (below); (c) its suite run stopped at test 98/267 because on Windows pytest-timeout kills the
  whole process — here each file runs in its own process, so 221-239 tests report.
- Earlier report dia089 said "2.x breaks, `<2` is safe" and "installed 0.105.2 is fine today".
  The SDK source supports neither claim in full: the cap is wrong (break at 1.0), and 0.105.2 is
  only fine for models that still accept temperature.

## 2. Root cause
1. **SDK side.** anthropic 1.0 removed `temperature`, `top_p`, `top_k` from `messages.create`
   signatures (MIGRATION.md: "only gone from the method signatures, not from the API … pass it
   through `extra_body`"). The adapter passed `temperature=` directly → TypeError before any request.
2. **Model side.** Anthropic's model docs: Opus 4.7/4.8, Sonnet 5, Opus 5/5.5 and Fable reject
   sampling params with a 400; Sonnet 5.5 / Haiku 5.5 reject non-default values. The app's default
   Claude reasoning model is `claude-opus-4-8` (registry), so that route returns a 400 **on any SDK,
   including today's 0.105.2**. (From Anthropic's docs; not confirmed with a live call — no spend.)
- Other call sites: only one Anthropic call exists (`text_client._generate_anthropic`); vision goes
  through it (covered by a test); no streaming, no `httpx` objects handed to the SDK, no
  `with_raw_response`. Model listing uses raw HTTP, not the SDK.

## 3. Fix (committed on this branch)
- `backend/app/providers/text_client.py`: temperature now goes via `extra_body` (accepted by every
  SDK 0.39-2.3, no feature detection needed) and only for model ids that still accept it
  (Claude 3.x, 4.0-4.6). Other models run at the model default; a comment says so and a debug log
  line records the omission. No silent drop without a comment.
- `requirements.txt`, `requirements-desktop.txt`: `anthropic>=0.39.0,<3` (proven range; a next major
  could remove more — re-run the check before allowing it).
- `backend/tests/test_anthropic_sdk_compat.py`: offline check (real adapter + real SDK, in-memory
  HTTP transport, placeholder key): temperature sent for Haiku 4.5, omitted for Opus 4.8, vision
  request shape, allow-list for 15 model ids.

## 4. Proof
Offline adapter check, 18 tests, per SDK (fresh Python 3.11 venvs):

| SDK | fixed adapter | old adapter |
|---|---|---|
| 0.39.0 (floor) | 18 pass | — |
| 0.105.2 (installed today) | 18 pass | Opus 4.8 gets temperature (fail) |
| 1.17.0 (Codex's cap) | 18 pass | TypeError, 3/3 fail |
| 2.3.0 (latest) | 18 pass | — |

Full backend suite, same throwaway venv (fresh install of requirements-desktop + dev + Codex's
test extras; resolved anthropic 2.3.0), unchanged main vs fix, one process per test file:

| | reported | passed | failed | errors | skipped |
|---|---|---|---|---|---|
| main | 221 | 177 | 31 | 5 | 8 |
| fix | 239 | 194 | 32 | 5 | 8 |

- +18 = the new SDK tests, all pass.
- The one extra failure, `test_wespeaker_cosine_similarity_calculation`, is flaky on main too
  (re-run 5x: main failed 3/5, fix 1/5; random embeddings vs a fixed 0.1 threshold).
- Every other failure/error is identical on main (suite-comparison.json). None touches the Claude
  adapter (no existing test imports it). Causes: missing `wespeaker` package, stale mocks
  (`speech_transcriber`, `state`, `start_time`), timing asserts, a Gemini key check, Windows
  long-path setup errors in trace tests.
- The same 4 files hang on both runs (20 s timeout kills the file): live_ask_turn_packaging,
  speaker_integration, speaker_service_properties, voice_encoder. Same as Codex's timeout.
- vs Codex's baseline 82 pass / 16 fail (98 of 267 run): all 16 of those failures are in the main
  list here or sit in a hanging file; nothing new.

## 5. Task-management project (not edited)
- `app/routes/ai.py` makes two `messages.create` calls with model/max_tokens/system/messages only —
  **no temperature, no SDK break**. Offline check (`check_task_management.py`) passes on SDK
  0.39.0, 0.105.2, 1.17.0 and 2.3.0.
- Real problem there: it calls `claude-3-haiku-20240307` (Claude Haiku 3), retirement date
  19-04-2026 in Anthropic's model list, so both AI routes most likely fail today on any SDK
  (not confirmed live — no spend).
- `task-management.patch` (passes `git apply --check -p1` in that repo, which was left untouched):
  model → `claude-haiku-4-5` (same request shape), `anthropic>=0.20.0,<3`.
  Apply from the project root: `git apply -p1 <path>\task-management.patch`; undo with `-R`.

## 6. Not done / limits
- Memory brief and closing B-1102: `memory.py` is outside this job's sandbox (blocked), so not run.
- No live API call, so the model-side 400s and the Haiku 3 retirement come from Anthropic's docs.
