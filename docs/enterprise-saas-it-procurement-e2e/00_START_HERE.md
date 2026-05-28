# Enterprise SaaS & IT Procurement E2E Test

Use this package to test the AI Negotiation Copilot in the exact niche you described: a high-value enterprise SaaS renewal where the rep must defend ARR, auto-renewal, uplift, SLA, payment, and exit terms under procurement pressure.

The scenario is fictional, but the pressure points are based on real SaaS procurement patterns: renewal uplift caps, auto-renewal notice windows, Net-60/Net-90 asks, SLA credits, overage rules, benchmarking, and late-stage legal redlines.

## Scenario

You are the seller's enterprise account executive at **Northstar Observability Cloud**. The counterparty is the buyer's IT procurement lead at **Cobalt Bank Group**.

You are trying to close a renewal and expansion for observability, incident response, and AI operations monitoring. Procurement wants the software, but they are using legal and finance terms to reduce long-term vendor leverage.

## What This Test Proves

- Virtual meeting capture works in a real back-and-forth conversation.
- The AI extracts exact commercial and legal terms from speech.
- The AI reads shared-screen documents and classifies terms from vision.
- The AI follows a strategic trade hierarchy instead of giving generic negotiation advice.
- The AI protects compounding ARR clauses while allowing reversible concessions.
- The logs and session trace provide enough evidence to audit the run afterward.

## Files

1. `01_USER_PRIVATE_BRIEF.md`
   - Your private strategy sheet. Do not share with the counterparty.

2. `02_COUNTERPARTY_BRIEF_AND_SCRIPT.md`
   - Give this to the person playing procurement.

3. `03_USER_SCRIPT_AND_AI_TIMING.md`
   - Keep this open during the meeting. It tells you what to say, when to share documents, and exactly when to ask the AI.

4. `04_ASK_AI_EXACT_PROMPTS.md`
   - Copy/read these into the hold-to-ask flow.

5. `05_VENDOR_ORDER_FORM_TO_SHARE.md`
   - The vendor order form you can share with the counterparty and screen-share for vision tests.

6. `06_COUNTERPARTY_REDLINE_TO_SHARE.md`
   - The counterparty's procurement redline. The counterparty can screen-share this during the meeting.

7. `07_VISION_EXTRACTION_EXPECTED_RESULTS.md`
   - Expected extraction answers for the screen-share / video-analysis test.

8. `08_PASS_FAIL_AND_LOG_AUDIT.md`
   - How to score AI response quality, extraction, business logic, latency, transcript labels, and logs.

9. `09_SOLO_COUNTERPARTY_AI_PROMPT.md`
   - Paste-ready prompt if you want another AI to role-play procurement.

10. `10_WEB_RESEARCH_BASIS.md`
   - Research basis and source links used to make the scenario realistic.

11. `assets/enterprise_saas_procurement_cover.png`
   - Generated cover visual for demo context.

12. `assets/northstar_order_form_vision_card.svg`
   - Deterministic, exact-text visual asset for OCR/vision testing.

13. `11_USER_EXACT_DIALOGUE_WITH_AI.md`
   - The clean user-side dialogue script. Use this during the live call.

14. `12_COUNTERPARTY_EXACT_DIALOGUE.md`
   - The clean counterparty-side dialogue script. Give this to the other person.

## Use These Two Files For The Real Run

If you want the simplest live test, ignore the brief-style files and use only:

- `11_USER_EXACT_DIALOGUE_WITH_AI.md`
- `12_COUNTERPARTY_EXACT_DIALOGUE.md`

The user file includes exactly what to say and exactly when to ask AI. The counterparty file includes only the other person's lines in the same sequence.

## Recommended Setup

Use the desktop companion path with Zoom, Google Meet, or Microsoft Teams.

1. Start the backend and Electron desktop companion.
2. Join a virtual meeting with one counterparty.
3. Select the active meeting window in the companion.
4. Keep AI speech manual only: ask the AI only when you hold the orb.
5. Open `05_VENDOR_ORDER_FORM_TO_SHARE.md` or `assets/northstar_order_form_vision_card.svg` and screen-share it when instructed.
6. Ask the counterparty to open and share `06_COUNTERPARTY_REDLINE_TO_SHARE.md` when instructed.

## Expected Duration

15 to 22 minutes.

Run slowly. Pause 3 to 5 seconds after each important number, clause, or concession so the transcript, extraction, and advice have enough context.
