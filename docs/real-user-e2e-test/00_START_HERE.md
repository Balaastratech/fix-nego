# Real User End-to-End Test: B2B Vendor Renewal

Use this package to test the AI Negotiation Copilot like a real business meeting, not like a developer test.

## Scenario

You are the buyer/procurement lead at a mid-market SaaS company. You are negotiating renewal pricing for an AI customer support platform your company already uses.

The counterparty is the vendor's account executive.

## Files To Use

1. `01_USER_MEETING_BRIEF.md`
   - Your private prep sheet.
   - Do not show this to the counterparty.

2. `02_COUNTERPARTY_SCRIPT.md`
   - What the counterparty should say.
   - Give this file to the person role-playing the vendor.

3. `03_USER_SCRIPT_AND_UI_COMMANDS.md`
   - What you should click in the app.
   - What you should say out loud during the meeting.

4. `04_ASK_AI_PROMPTS.md`
   - Exact questions to ask AI in Advice mode and Command mode.

5. `05_OBSERVATION_AND_PASS_FAIL_SHEET.md`
   - What to watch in the UI.
   - What counts as pass/fail for the full system.

6. `06_WEB_RESEARCH_BASIS.md`
   - Why this meeting script is realistic.
   - Sources used for negotiation structure.

7. `07_SOLO_COUNTERPARTY_AI_PROMPT.md`
   - Paste-ready prompt for using another AI as the counterparty.

8. `08_SOLO_RUN_GUIDE.md`
   - How to run the full test alone with a second AI voice/chat app.

## Fastest App Path

Use Chrome.

Open the deployed frontend:

https://negotiation-frontend-219079068693.us-central1.run.app

If you want local testing instead, open your local frontend after starting the app:

http://localhost:3000

## Meeting Setup

Use two people if possible:

- You: buyer/procurement lead
- Counterparty: vendor account executive

If you are alone, read both scripts out loud and click the correct speaker button before each line.

Use manual speaker mode for this test. It is the most reliable current path for validating transcript, speaker labels, negotiation state, and AI advice.

## Timing

Run the meeting slowly. After each important price or term statement, pause 3 to 5 seconds so the transcript and strategy panels can update.

Expected total time: 12 to 18 minutes.
