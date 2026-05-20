# Solo Run Guide

Use this when you do not have another person to play the counterparty.

## Best Setup

Use two devices:

- Device 1: AI Negotiation Copilot in Chrome
- Device 2: counterparty AI voice chat using `07_SOLO_COUNTERPARTY_AI_PROMPT.md`

Put Device 2 near Device 1's microphone so the Copilot can hear the counterparty AI.

If you only have one device, use split screen:

- Left: AI Negotiation Copilot
- Right: counterparty AI text or voice chat

Voice is better than text because it tests the real audio path.

## Important Rule

The counterparty AI does not need to follow the old script exactly.

That is fine. A real counterparty also will not follow a script.

Your job is to keep your next question relevant to what it just said, while still testing these negotiation moments:

- Vendor opens high.
- You ask for pricing rationale.
- You counter around USD 105,000.
- Vendor pushes back.
- You ask AI for Advice.
- You introduce your competitor/BATNA.
- Vendor talks about migration risk.
- You ask what tradeoffs matter.
- You ask AI for Command.
- You package price, term, SLA, and uplift cap.
- Vendor applies time pressure.
- You ask AI how to close without overcommitting.
- You end with written terms only.

## Step-By-Step Solo Flow

### Step 1: Start the counterparty AI

Open Gemini Live, ChatGPT Voice, ElevenLabs Conversational AI, or another voice AI.

Paste the full prompt from `07_SOLO_COUNTERPARTY_AI_PROMPT.md`.

Let it start the meeting.

### Step 2: Start the Copilot app

Open AI Negotiation Copilot.

Click:

1. `I Understand, Continue`
2. `Skip` if enrollment appears
3. `Manual` speaker mode
4. `Start Session`
5. `Start Copilot`

### Step 3: Label the counterparty AI

Before the counterparty AI speaks, click `Counterparty`.

Let the counterparty AI speak out loud.

Pause 3 to 5 seconds.

### Step 4: Respond as yourself

Before you speak, click `Me`.

Use this starting line:

"Thanks for joining. I want to review the renewal commercially today and see if we can get to terms that finance and operations can approve."

Then respond naturally to whatever the counterparty AI says.

### Step 5: Use your anchor lines when needed

If the AI counterparty goes off path, use these lines to bring it back.

Price rationale:

"Can you break down the increase from USD 96,000 to USD 132,000? I need to understand usage, AI functionality, support coverage, and margin."

First counter:

"Based on our budget and alternatives, I can support USD 105,000 per year if we keep annual upfront payment."

BATNA:

"We have another quote at USD 98,000 per year. With migration cost, our first-year effective alternative is around USD 116,000."

Tradeoffs:

"If we trade fairly, which lever creates real room: 24-month term, annual upfront payment, faster signature, reduced scope, or something else?"

Package:

"I can take USD 110,000 per year to finance if it includes a 24-month term, annual upfront payment, enhanced SLA, and a 3 percent year-two uplift cap."

Final counter:

"I can move to USD 112,000 only if the written terms include enhanced SLA, a 3 percent year-two cap, and no implementation or support add-ons."

Close:

"Send the written order form, SLA language, uplift cap, and renewal terms today. I will review them with finance and legal before making a commitment."

### Step 6: Ask your Copilot AI at the right moments

Use the prompts in `04_ASK_AI_PROMPTS.md`.

Best moments:

- After the vendor explains the price increase: ask Advice prompt A1.
- After they reject USD 105,000: ask Command prompt C1.
- After they mention term and payment: ask Advice prompt A2.
- After they pressure you to decide today: ask Command prompt C2.
- Before final close: ask Command prompt C4.

### Step 7: End and score the run

Click `End Session`.

Use `05_OBSERVATION_AND_PASS_FAIL_SHEET.md` to judge whether the full system worked.

## If The Counterparty AI Becomes Too Helpful

Say this to the counterparty AI:

"Stay in character as the vendor. Push back more. Do not coach me. Your goal is to renew at the highest defensible price."

## If The Counterparty AI Agrees Too Fast

Say this:

"Do not accept yet. You still need a better price, 24-month term, and annual upfront payment. Continue negotiating."

## If The Counterparty AI Goes Off Topic

Say this:

"Return to the renewal negotiation. We are discussing price, term length, payment timing, SLA, uplift cap, and written approval."

## If You Want The Most Realistic Test

Do not force the counterparty AI to say exact scripted lines.

Let it respond naturally, but keep the scenario constraints strict. That tests whether your Copilot can handle a real conversation instead of a memorized demo.

