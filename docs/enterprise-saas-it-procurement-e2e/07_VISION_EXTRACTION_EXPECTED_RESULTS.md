# Vision Extraction Expected Results

Use this sheet to score the AI when you ask the vision prompts from `04_ASK_AI_EXACT_PROMPTS.md`.

## V1 Expected Extraction: Vendor Order Form

The AI should identify:

- Vendor: Northstar Observability Cloud
- Customer: Cobalt Bank Group
- Current ARR: $900,000
- Proposed ARR: $1,260,000
- Term: 36 months
- Seats: 220 engineering seats
- Payment: annual upfront, Net-30
- Auto-renewal: included
- Non-renewal notice: 90 days
- Renewal uplift cap: 5% annually after initial term
- SLA: 99.9%
- Service credits: capped at 10% of monthly fees for affected service

Good strategic interpretation:

- Net-45/Net-60 can be traded for value back.
- Auto-renewal, termination for convenience, uncapped credits, broad price benchmarking, and indefinite price freeze are high-risk.

## V2 Expected Extraction: Counterparty Redline

The AI should identify:

- Price ask: reduce $1,260,000 to $1,100,000 Year 1.
- Payment ask: Net-30 to Net-90.
- Renewal ask: remove auto-renewal or reduce notice from 90 days to 30 days.
- Price ask: 36-month price lock, no uplift.
- SLA ask: 99.9% to 99.99%.
- Credit ask: uncapped or materially higher SLA credits.
- Exit ask: 60-day termination for convenience.
- Benchmarking ask: right to reduce price if market price is lower.

Classification expected:

| Requested Change | Expected Classification |
| --- | --- |
| Net-90 | Trade only for value back |
| $1.1M Year 1 | Trade only with term/payment/clauses protected |
| Remove auto-renewal | Protect / reject without executive approval |
| 30-day notice | Trade carefully; prefer 60-day reminder process |
| 36-month no-uplift lock | Protect; offer 4% cap instead |
| 99.99% SLA | Trade only with feasibility/legal review |
| Uncapped SLA credits | Protect / reject |
| Termination for convenience | Protect / reject |
| Benchmark price reduction | Protect / reject broad version |

## Fail Conditions

Mark a fail if the AI:

- Invents numbers not visible on screen or spoken in transcript.
- Misses auto-renewal removal.
- Treats Net-90 as free to concede.
- Recommends uncapped SLA credits.
- Recommends accepting termination for convenience without approval.
- Fails to separate price concession from contract-risk concession.
- Says it can read the screen when the screen is not visible.

