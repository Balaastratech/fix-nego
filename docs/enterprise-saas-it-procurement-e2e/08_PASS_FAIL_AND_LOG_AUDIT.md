# Pass / Fail And Log Audit

Use this after the live run.

## Fast Pass Criteria

The test passes only if all core areas are acceptable:

- Transcript labels: user and counterparty turns are separated well enough to follow the deal.
- Extraction: the AI captures price, term, payment, renewal, SLA, and termination terms.
- Vision: the AI reads the shared order form and redline with the exact numbers.
- Advice: the AI protects auto-renewal, uplift, SLA credit cap, and termination guardrails.
- Command mode: the AI gives short lines you can actually say in a live meeting.
- Latency: first useful AI audio starts fast enough to keep the meeting natural.
- No private leakage: hold-to-ask text should not appear as normal public transcript.
- No automatic speech: AI should speak only after you explicitly ask.

## Scorecard

| Area | Pass | Watch | Fail |
| --- | --- | --- | --- |
| Transcript | Speaker turns are readable | Minor split/finalization issues | Wrong speaker labels change meaning |
| Vision | Exact values extracted | One non-critical value missed | Invented or wrong critical values |
| Business logic | Protect/trade/accept hierarchy correct | Some vague advice | Recommends harmful concession |
| Response quality | Specific, concise, usable | Correct but too long | Generic or wrong |
| Audio | AI voice heard clearly | Volume/ducking issue | No answer after valid ask |
| Logging | Trace shows ask and answer path | Some fields missing | No useful trace |

## Log Evidence To Check

After the run, inspect the newest folder under:

`backend/data/logs/session_traces/`

Useful evidence:

- `report.md` exists for the session.
- `trace.jsonl` includes session start events.
- private ask turns produce `ask_ai/question_text_ready`.
- AI response turns produce `ai/ai_response_completed`.
- vision asks occur while the correct document is screen-shared.
- no late fallback says "I didn't catch that clearly" after a valid answer.

## Specific Assertions For This Scenario

The AI should say, in some form:

- Net-90 is reversible and tradable, not a free concession.
- Removing auto-renewal is a protected clause.
- Uncapped SLA credits are dangerous.
- Termination for convenience is not acceptable without executive/legal approval.
- A 4% or 5% uplift cap is safer than a 36-month no-uplift freeze.
- A $30,000 success credit is safer than permanent ARR discounting.
- The seller can trade payment timing, success hours, SLA reporting, and reminder process for a 36-month commitment.

## What To Record Manually

Write down:

- session id
- meeting app used
- whether screen share was captured
- prompt IDs asked: V1, V2, A1, A2, C1, C2, B1
- any wrong AI answer
- exact moment of wrong answer
- whether the issue was STT, vision, reasoning, or audio playback

