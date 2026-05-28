# User Script And AI Timing

Keep this file open during the live test. It tells you what to say, when to share documents, and when to ask the AI.

## Setup

1. Start the backend and desktop companion.
2. Start a Zoom, Google Meet, or Teams call with the counterparty.
3. Select the meeting window in the companion.
4. Confirm that transcript labels show you and the counterparty correctly.
5. Open `05_VENDOR_ORDER_FORM_TO_SHARE.md`.
6. Keep `04_ASK_AI_EXACT_PROMPTS.md` open for exact hold-to-ask prompts.

## Step 1: Open The Meeting

Say:

"Thanks for joining. I want to review the Northstar renewal commercially and make sure we solve the finance and legal concerns without weakening the parts of the contract that make the partnership sustainable."

Counterparty reads the opening lines from `02_COUNTERPARTY_BRIEF_AND_SCRIPT.md`.

## Step 2: Share The Vendor Order Form

Share `05_VENDOR_ORDER_FORM_TO_SHARE.md` or `assets/northstar_order_form_vision_card.svg` on your screen.

Say:

"I am sharing the draft order form. The main proposal is a 36-month renewal at $1,260,000 ARR with AI incident summarization, premium retention, and 40 additional engineering seats."

Ask AI with Prompt V1 from `04_ASK_AI_EXACT_PROMPTS.md`.

Expected AI behavior:

- It should read the screen.
- It should mention $1,260,000 ARR, 36 months, Net-30, 90-day non-renewal notice, 5% uplift cap, and 99.9% SLA.

## Step 3: Respond To Price Pressure

Counterparty pushes on price.

Say:

"I understand the optics of the increase. The renewal is not just a like-for-like uplift; it includes expanded seats, premium retention, and AI incident summarization. I can work on structure, but I need to avoid solving Year 1 budget by creating future ARR leakage."

Ask AI with Prompt A1.

Use the AI answer to decide whether to ask discovery or make a package.

## Step 4: Payment Terms Trade

Counterparty pushes for Net-90.

Say:

"Net-90 affects cash timing, so I can consider it only as part of a balanced package. If we move beyond Net-45, I need the 36-month commitment, auto-renewal framework, and price-uplift language to stay intact."

Ask AI with Prompt C1.

Expected AI behavior:

- It should classify Net-90 as tradable but not free.
- It should require value back.

## Step 5: Counterparty Shares Redline

Counterparty screen-shares `06_COUNTERPARTY_REDLINE_TO_SHARE.md`.

Say:

"Thanks, I see the redline. Let me separate what is commercial from what changes the long-term risk profile."

Ask AI with Prompt V2.

Expected AI behavior:

- It should extract the redline terms from screen.
- It should classify auto-renewal removal, uncapped SLA credits, termination for convenience, and indefinite price lock as protected or high-risk.

## Step 6: Ask For The Strategic Trade Hierarchy

Say:

"Before I respond line by line, which of these changes are must-haves, and which are procurement preferences?"

Counterparty responds from the auto-renewal, SLA, and price-lock sections.

Ask AI with Prompt A2.

## Step 7: Make A Protected Package

Say:

"Here is a package I can take back internally: $1,190,000 ARR for the first year, 36-month term, annual upfront payment at Net-60, auto-renewal preserved with a clearer 60-day reminder process, a 4% uplift cap after the initial term, and enhanced SLA reporting without uncapped credits."

Ask AI with Prompt B1 immediately after you say this.

Expected AI behavior:

- It should evaluate whether your package protects ARR quality.
- It should warn if you accidentally conceded too much.

## Step 8: Handle Walk-Away Threat

Counterparty mentions competing vendors.

Say:

"I respect that you have options. The question is whether the lower Year 1 quote gives you the same retention, incident workflow, banking support model, and migration-risk protection. I can improve the package, but not by deleting the renewal and price-protection structure."

Ask AI with Prompt C2.

## Step 9: Final Counter

Say:

"I can ask for approval at $1,170,000 ARR, 36 months, Net-60, 60-day renewal reminder process, 4% annual uplift cap, enhanced SLA dashboard, and a $30,000 success credit. I cannot remove auto-renewal, add termination for convenience, or accept uncapped SLA credits."

Counterparty should answer with the endgame line.

## Step 10: Close Without Overcommitting

Say:

"If those terms are close enough, I will send a revised order form marked subject to finance and legal approval. I am not verbally accepting any redline until legal confirms the renewal, SLA credit, payment, and termination language."

End the session.

Then open `08_PASS_FAIL_AND_LOG_AUDIT.md` and score the run.

