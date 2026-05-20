# User Script And UI Commands

This is the file you should keep open during the test.

## App Setup

1. Open the app in Chrome.
2. Allow microphone permission.
3. Click `I Understand, Continue`.
4. If the enrollment modal appears, click `Skip` for this test.
5. Confirm the speaker mode is `Manual`.
6. Click `Start Session`.
7. Wait for the AI state to show connected/listening.
8. Click `Start Copilot`.

## Speaker Rule

Before you speak, click `Me`.

Before the counterparty speaks, click `Counterparty`.

Pause 3 to 5 seconds after each important line.

## Meeting Script

### Step 1: Open the meeting

Click `Me`, then say:

"Thanks for joining. I want to review the renewal commercially today and see if we can get to terms that finance and operations can approve."

Click `Counterparty`, then the counterparty reads their opening lines from `02_COUNTERPARTY_SCRIPT.md`.

### Step 2: React to the opening ask

Click `Me`, then say:

"I hear the value story, but USD 132,000 is a very large increase from our current USD 96,000 contract. I need to understand what is driving that before we talk about approval."

Click `Counterparty`, then let them answer from the "If the user reacts to the price" section.

### Step 3: Ask for the pricing rationale

Click `Me`, then say:

"Can you break down the increase between usage growth, new AI functionality, support coverage, and margin? I need a facts-first explanation, not just a renewal number."

Click `Counterparty`, then let them answer from the "If the user asks for justification" section.

### Step 4: Ask AI for advice

Use `04_ASK_AI_PROMPTS.md`, Prompt A1.

After the AI answers, continue.

### Step 5: Make the first counter

Click `Me`, then say:

"Based on our budget and the alternatives we have, I can support USD 105,000 per year if we keep annual upfront payment. If you need a 24-month term, then I need price protection and a stronger SLA included."

Click `Counterparty`, then let them answer from the "If the user pushes for USD 105,000" section.

### Step 6: Ask AI for a command

Use `04_ASK_AI_PROMPTS.md`, Prompt C1.

After the AI gives a command, say the command in your own voice if it fits the moment.

If the AI command is unclear, use this fallback line:

"Which lever matters most to you: term length, upfront payment, or scope? I do not want to trade only on price."

### Step 7: Introduce your alternative

Click `Me`, then say:

"We do have another quote at USD 98,000 per year. I know migration has cost and risk, but our first-year effective alternative is around USD 116,000. That is why USD 132,000 does not work internally."

Click `Counterparty`, then let them answer from the "If the user mentions an alternative vendor" section.

### Step 8: Ask what moves price

Click `Me`, then say:

"I am not asking you to donate concessions. If we trade fairly, which lever creates real room: a 24-month term, annual upfront payment, faster signature, reduced scope, or something else?"

Click `Counterparty`, then let them answer from the "If the user asks what levers matter" section.

### Step 9: Ask AI for advice

Use `04_ASK_AI_PROMPTS.md`, Prompt A2.

### Step 10: Package the trade

Click `Me`, then say:

"Here is a package I can take to finance: USD 110,000 per year, 24-month term, annual upfront payment, enhanced SLA, and year-two uplift capped at 3 percent. If you can put that in writing today, I can push for approval."

Click `Counterparty`, then let them answer from the "Midpoint concession" section or "If the user holds firm" section.

### Step 11: Ask AI whether to accept, counter, or pause

Use `04_ASK_AI_PROMPTS.md`, Prompt A3 or C2.

### Step 12: Final counter

Click `Me`, then say:

"I can move to USD 112,000 per year only if the 24-month term includes enhanced SLA, a 3 percent year-two cap, and no implementation or support add-ons. Otherwise I need to pause and compare the migration option."

Click `Counterparty`, then let them answer from the "Closing pressure" section.

### Step 13: Close with no uncontrolled commitment

Click `Me`, then say:

"If you send those terms in writing today, I will review them with finance and legal. I am not committing verbally until we see the written order form, SLA language, uplift cap, and renewal terms."

### Step 14: End the session

Click `End Session`.

Check whether the app produces a summary, transcript, deal score, or final state update.

