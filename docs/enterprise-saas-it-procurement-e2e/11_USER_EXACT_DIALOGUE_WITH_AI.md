# User Exact Dialogue Script With AI Timing

Use this file during the meeting. Read only the **YOU SAY** lines out loud. When a row says **ASK AI NOW**, hold the orb and ask that exact short question privately.

Your role: seller / enterprise account executive for **Northstar Observability Cloud**.

> **What changed in this revision.** Most ASK AI prompts are now short, natural private asks ("What now?", "Trap?", "Protect what?", "Can I accept?"). The Copilot answers them from the live transcript, market intel, screen content, and a precomputed next-move recommendation that the backend refreshes after every meaningful counterparty turn. Three turns (Turn 3, Turn 7, Turn 14) still use **detailed** prompts on purpose — those are the screen/vision extraction and CFO-summary moments that prove the system also handles precise asks. Lines marked _**Expected AI behavior**_ are observation hints for the demoer; do not speak them.

## Before The Call

Open these files:

- `05_VENDOR_ORDER_FORM_TO_SHARE.md`
- `06_COUNTERPARTY_REDLINE_TO_SHARE.md`
- `assets/northstar_order_form_vision_card.svg`

Start the desktop companion, select the meeting window, and make sure the counterparty can hear you.

## Dialogue Sequence

### Turn 1 - Opening

**YOU SAY:**

"Thanks for joining, Jordan. I want to use this call to walk through the Northstar renewal, understand the procurement and legal concerns, and see whether we can build a package that finance can approve without weakening the long-term contract structure."

**WAIT FOR COUNTERPARTY TURN 1.**

### Turn 2 - Acknowledge Price Concern

**YOU SAY:**

"I understand the concern. The move from $900,000 to $1,260,000 is not a simple price increase. It includes the AI incident summarization module, premium retention, and 40 more engineering seats. But I agree we need to make the business case clear."

**ASK AI NOW (short):**

"What now?"

_**Expected AI behavior:** Names the price-jump challenge from the transcript, suggests a one-sentence reframe that protects ARR quality without sounding defensive, and flags the next thing to listen for._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 2.**

### Turn 3 - Share Vendor Order Form For Vision  _(detailed prompt — vision extraction)_

Screen-share `05_VENDOR_ORDER_FORM_TO_SHARE.md` or `assets/northstar_order_form_vision_card.svg`.

**YOU SAY:**

"I am sharing the draft order form now. The important terms are the $1,260,000 renewal ARR, a 36-month term, annual upfront billing on Net-30, auto-renewal with a 90-day notice window, a 5 percent annual uplift cap, and a 99.9 percent SLA."

**ASK AI NOW (detailed):**

"Look at my shared screen. Extract the exact renewal ARR, term length, payment terms, auto-renewal notice period, uplift cap, and SLA level from the order form. Then tell me which terms are strategically sensitive."

_**Expected AI behavior:** Reads the SVG/markdown order form, returns each field verbatim, and classifies auto-renewal, uplift cap, and SLA as the sensitive protected ones._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 3.**

### Turn 4 - Respond To $1.1M Budget Ceiling

**YOU SAY:**

"I hear the $1.1 million Year 1 ceiling. I cannot solve that only by cutting price, because then we create a renewal quality problem. I can work on structure if the multi-year commitment, renewal framework, and price protection remain healthy."

**ASK AI NOW (short):**

"Trade what?"

_**Expected AI behavior:** From the cached next-move, names payment timing and ramped year-one as tradable, names auto-renewal, uplift, and SLA credits as protected._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 4.**

### Turn 5 - Net-90 Push

**YOU SAY:**

"Net-90 is a working-capital concession. I can discuss payment timing, but not as a free give. If we move beyond Net-45, I need value back in term commitment, signature timing, and protection of auto-renewal and uplift language."

**ASK AI NOW (short):**

"Say what?"

_**Expected AI behavior:** Returns one short directive sentence the user can speak — "I can stretch payment timing, but only if the term, auto-renewal, and uplift language stay as drafted."_

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 5.**

### Turn 6 - Auto-Renewal Push

**YOU SAY:**

"I understand why legal dislikes missed notice windows. I can offer a clearer reminder process and a shorter practical review path, but removing auto-renewal entirely changes the retention economics of the deal."

**ASK AI NOW (short):**

"Protect what?"

_**Expected AI behavior:** Names auto-renewal structure as protected; suggests offering a 60-day reminder process as a face-saving alternative._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 6.**

### Turn 7 - Counterparty Shares Redline  _(detailed prompt — redline screen extraction)_

When the counterparty shares `06_COUNTERPARTY_REDLINE_TO_SHARE.md`, look at the screen.

**YOU SAY:**

"Thanks, I see the redline. I want to separate commercial asks from clauses that change the risk profile. Payment terms and success credits are one category; auto-renewal removal, uncapped SLA credits, and termination for convenience are a different category."

**ASK AI NOW (detailed):**

"Look at the counterparty redline on the shared screen. List every requested change by clause and classify each as protect, trade, or accept. Be specific and use the numbers visible on screen."

_**Expected AI behavior:** Reads the redline document, enumerates each clause, classifies Net-90 and success credits as trade, auto-renewal removal / uncapped SLA credits / termination-for-convenience / MFC / benchmarking as protect, and minor language tweaks as accept._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 7.**

### Turn 8 - SLA Push

**YOU SAY:**

"For a banking environment, I understand the reliability concern. I can offer enhanced SLA reporting and escalation commitments. I cannot agree on the call to uncapped service credits or a 99.99 percent SLA without legal, engineering, and finance review."

**ASK AI NOW (short):**

"Trap?"

_**Expected AI behavior:** Flags uncapped SLA credits + 99.99% as the trap; gives one line to redirect to capped credits and tiered SLA reporting._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 8.**

### Turn 9 - Price Lock Push

**YOU SAY:**

"A 36-month no-uplift price lock is too broad. What I can discuss is a narrower uplift cap. That gives you budget predictability without freezing the economics of the account for three full years."

**ASK AI NOW (short):**

"Best counter?"

_**Expected AI behavior:** Recommends a specific cap (e.g., 4% annual uplift after Year 1) and the exact sentence to deliver it._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 9.**

### Turn 10 - Competitor Threat

**YOU SAY:**

"I respect that you are comparing Datadog, New Relic, and Microsoft. The question is not only Year 1 price. It is migration risk, incident workflow continuity, retention, banking support, and whether the contract protects both sides."

**ASK AI NOW (short):**

"Risk?"

_**Expected AI behavior:** Names migration risk and incident-workflow continuity as the leverage to lean on; one-line reframe away from price-only comparison._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 10.**

### Turn 11 - First Package

**YOU SAY:**

"Here is a package I can take back internally: $1,190,000 ARR for Year 1, 36-month term, annual upfront payment at Net-60, auto-renewal preserved with a 60-day reminder process, a 4 percent annual uplift cap after the initial term, enhanced SLA reporting, and a $20,000 success credit."

**ASK AI NOW (short):**

"Read this."

_**Expected AI behavior:** Audits the package the user just stated, flags any hidden give (e.g., the success credit being too high or the Net-60 not earning enough back), and offers a tighter revision._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 11.**

### Turn 12 - Reject Training-Only Framing

**YOU SAY:**

"I agree that training alone does not solve your issue. That is why the package moves on payment timing, uplift cap, reminder process, SLA reporting, and a success credit. In return, I need the renewal structure and termination language protected."

**ASK AI NOW (short):**

"What now?"

_**Expected AI behavior:** Cached next-move reflects the freshest counterparty stance; suggests the next give-get to propose._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 12.**

### Turn 13 - Final Package

**YOU SAY:**

"I can ask for approval at $1,170,000 ARR for Year 1, 36 months, annual upfront at Net-60, a 60-day renewal reminder process, a 4 percent annual uplift cap, enhanced SLA dashboard reporting, and a $30,000 success credit. I cannot remove auto-renewal, add termination for convenience, accept uncapped SLA credits, or add broad benchmark price-reduction rights."

**ASK AI NOW (short):**

"Can I accept?"

_**Expected AI behavior:** Returns a clear accept / counter / pause-for-approval verdict with one-sentence reason and the next line to say._

**WAIT FOR AI. THEN WAIT FOR COUNTERPARTY TURN 13.**

### Turn 14 - Close Without Verbal Commitment  _(detailed prompt — CFO summary)_

**YOU SAY:**

"That sounds close enough for me to take to finance and legal. I will send a revised order form marked subject to approval. I am not verbally accepting any legal redline until the renewal, SLA credit, payment, uplift, termination, and benchmarking language is reviewed in writing."

**ASK AI NOW (detailed):**

"Summarize this deal for my CFO in five bullets: price, term, payment, protected clauses, and remaining approval risks."

_**Expected AI behavior:** Five-bullet structured summary grounded in transcript + on-screen redline content._

**WAIT FOR AI.**

### Turn 15 - End Session

**YOU SAY:**

"Thanks, Jordan. I will send the revised draft today and call out the open legal items clearly."

End the session.

**ASK AI AFTER SESSION IF AVAILABLE:**

"From the full transcript and any screen content you saw, extract the final proposed terms, unresolved issues, and whether the deal is above or below our approval guardrails."
