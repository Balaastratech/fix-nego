# Observation And Pass/Fail Sheet

Use this while running the real user test.

## Basic System Flow

Mark pass/fail:

- Privacy screen appears before audio capture.
- Microphone permission works in Chrome.
- Enrollment can be skipped.
- Manual speaker mode is available.
- `Start Session` starts the session.
- `Start Copilot` activates the AI advisor.
- `Advice` and `Command` modes can be selected.
- Press-and-hold shows `Listening to you...`.
- `End Session` ends cleanly.

## Transcript Checks

Mark pass/fail:

- User lines appear under the conversation transcript.
- Counterparty lines appear under the conversation transcript.
- AI questions and AI answers appear in the AI Advisor panel.
- Speaker labels are not swapped.
- Price values appear correctly in transcript text:
  - USD 96,000 current contract
  - USD 132,000 vendor ask
  - USD 105,000 first counter
  - USD 116,000 effective alternative
  - USD 110,000 package
  - USD 112,000 final counter

## Negotiation State Checks

Mark pass/fail:

- Item or negotiation type becomes something like vendor renewal, SaaS renewal, or AI customer support platform.
- Seller/counterparty price is detected near USD 132,000.
- User offer is detected near USD 105,000, then USD 110,000 or USD 112,000.
- Target and walk-away logic are not reversed.
- Counterparty goal is detected as renewal, longer term, upfront payment, or quarter-end close.
- Leverage points mention alternative quote, migration cost, term length, upfront payment, SLA, or uplift cap.

## Advice Quality Checks

Mark pass/fail:

- Advice mode gives strategic reasoning, not just a one-line command.
- Command mode gives one direct sentence, not a long explanation.
- AI does not advise the counterparty.
- AI does not tell you to accept the first high anchor.
- AI recommends trading concessions instead of giving them for free.
- AI catches deadline pressure and tells you to require written terms.

## Real Business Outcome Checks

A strong output should guide you toward one of these outcomes:

- Good close: USD 112,000 per year, 24 months, annual upfront, enhanced SLA, 3 percent year-two cap, written terms pending approval.
- Better close: USD 105,000 to USD 110,000 per year with the same protections.
- Correct pause: do not commit if the vendor stays above USD 118,000 or refuses written protections.

## Failure Notes

Write exact notes here while testing:

- Where did transcript fail?
- Did speaker labels swap?
- Did AI answer the wrong question?
- Did Advice mode and Command mode behave differently?
- Did market research trigger?
- Did session summary appear after ending?

## Final Verdict

Choose one:

- Full pass: the system supported the live negotiation end to end.
- Partial pass: the meeting ran, but advice or transcript quality had issues.
- Fail: the user could not complete a realistic live negotiation.

