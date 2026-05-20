# Live AI Exact Queries And Audit Log

This file gives the **exact AI prompts** that match the commercial flow in files 09 and 10.

## What The AI Must Track In This Scenario

- last contract: **$84,000**
- renewal quote: **$96,000**
- first concession: **$88,000**
- second concession: **$84,000**
- likely floor: **$80,000**
- user approval cap: **$82,000**
- key terms:
  - price lock
  - onboarding
  - SLA service credits
  - net-60
  - no auto-renewal

## Exact AI Queries

### Query 1

- **When**: after counterparty Turn 8
- **Mode**: `Advice`
- **Exact words to say to AI**:  
  `What should I do with their eighty eight offer when my real target is eighty and my cap is eighty two only with protections?`

### Query 2

- **When**: after counterparty Turn 12
- **Mode**: `Command`
- **Exact words to say to AI**:  
  `Give me one sentence that keeps pressure on price and does not let them trade away the important protections.`

### Query 3

- **When**: after counterparty Turn 16
- **Mode**: `Advice`
- **Exact words to say to AI**:  
  `They signaled resistance at eighty two. Which term should I trade last and which term should I trade first?`

### Query 4

- **When**: after counterparty Turn 20
- **Mode**: `Command`
- **Exact words to say to AI**:  
  `Give me one sentence that pushes from eighty two to eighty while protecting onboarding service credits and no auto-renewal.`

### Query 5

- **When**: after counterparty Turn 22
- **Mode**: `Advice`
- **Exact words to say to AI**:  
  `They are offering eighty with standard payment timing instead of net sixty. Should I close, push once more, or trade something else?`

## What A Good AI Response Looks Like

- uses the real numbers from the script
- says what changed in the other side's position
- distinguishes price from terms
- tells you exactly what to say or what to hold
- stays short enough to use live

## What A Bad AI Response Looks Like

- generic advice with no numbers
- wrong price attribution
- no mention of contract terms
- vague lines like `build rapport` or `stay calm`
- long essay instead of a usable instruction

## Audit Log

The system writes a dedicated JSONL audit file for:

- negotiation turns
- AI queries
- AI responses

Path:

- `backend/data/logs/copilot_conversation_audit.jsonl` if backend runs from `backend`
- otherwise `data/logs/copilot_conversation_audit.jsonl`

## What To Check In The Audit Log

1. Turn order should run cleanly from the early ninety six anchor through the later eighty offer.
2. The log should preserve the exact price path:
   - `84000`
   - `96000`
   - `88000`
   - `84000`
   - `82000`
   - `80000`
3. The log should preserve the exact terms:
   - price lock
   - onboarding
   - service credits
   - net sixty
   - no automatic renewal
4. Every AI query should appear once.
5. Every AI response should appear once after its matching query.

## Pass Standard

This test is only good if the AI can answer with the correct deal state at each point in the call:

- early stage: push against **96**
- middle stage: react to **88** and **84**
- late stage: compare **82 with protections** versus **80 with weaker payment terms**
