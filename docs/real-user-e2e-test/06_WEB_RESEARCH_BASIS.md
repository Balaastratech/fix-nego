# Web Research Basis

This test scenario is based on common B2B procurement and vendor-renewal negotiation patterns.

## Sources Used

- Program on Negotiation at Harvard Law School, "Sales Negotiation Techniques"
  - Source: https://www.pon.harvard.edu/daily/business-negotiations/sales-negotiation-techniques/
  - Used for: anchoring, framing counteroffers with credible rationale, avoiding weak over-explanation, and handling the first offer.

- Program on Negotiation at Harvard Law School, defensive negotiation guidance
  - Source: https://www.pon.harvard.edu/daily/batna/batna-and-dealmaking-negotiations-defending-yourself-against-influence-negotiation-strategies/
  - Used for: BATNA, ZOPA, preparation, and separating information from influence.

- Program on Negotiation at Harvard Law School, distributive negotiation guidance
  - Source: https://www.pon.harvard.edu/daily/dealmaking-daily/what-is-distributive-negotiation-strategies/
  - Used for: resisting unilateral concessions and using walk-away discipline.

- Gartner, B2B buying journey
  - Source: https://www.gartner.com.au/en/sales/insights/b2b-buying-journey
  - Used for: making the scenario a realistic multi-stakeholder B2B buying decision rather than a simple one-person purchase.

- Negotiations.AI, "Procurement Negotiation Playbook: Renewals, Price Increases, and Payment Terms"
  - Source: https://negotiations.ai/blog/procurement-negotiation-playbook
  - Used for: renewal diagnosis, target/acceptable/walk-away ranges, concession ladder, package negotiation, payment terms, SLA, term length, and approval-ready written close.

## Design Choices

The script uses a SaaS vendor renewal because it exercises the full product:

- Live conversation capture
- Buyer versus seller role tracking
- Price extraction
- Counterparty goal detection
- BATNA and walk-away reasoning
- Advice mode for strategy
- Command mode for exact wording
- Market or background research opportunities
- Post-session summary

## What The AI Should Learn From The Meeting

The AI should infer:

- The user is the buyer.
- The counterparty is the seller/vendor.
- The vendor anchored at USD 132,000.
- The user has a current price of USD 96,000.
- The user wants roughly USD 105,000 to USD 112,000.
- The user's walk-away is near USD 118,000.
- The user's BATNA is a competitor quote with effective first-year cost around USD 116,000.
- The vendor values a 24-month term, annual upfront payment, and quarter-end timing.
- The best strategy is to trade across price, term, payment, SLA, and uplift cap.

