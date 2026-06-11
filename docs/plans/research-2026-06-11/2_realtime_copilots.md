# Real-Time AI Copilot / Teleprompter Category Report (as of 2026-06-11)

## 1. Category map

Four sub-segments have emerged, distinguished by *who knows the AI is there*:

1. **Stealth interview copilots** (user hides AI from counterparty): Cluely (origin), Interview Coder, Final Round AI "Interview Copilot," LockedIn AI, Parakeet AI, Sensei AI, Verve AI, InterviewMan, OphyAI, AceRound. Consumer-priced ($20–150/mo), high churn by design (users stop paying when hired).
2. **Transparent real-time agent assist** (employer-sanctioned): Cresta (Forrester Leader, Conversation Intelligence Q2 2025 — https://cresta.com/agent-assist), plus contact-center incumbents. Enterprise ACV, sticky.
3. **Bot-free notetakers** (no live answer-feeding; device-side audio capture without a visible bot): Granola — raised $43M Series B at $250M (May 2025, https://techcrunch.com/2025/05/14/ai-note-taking-app-granola-raises-43m-at-250m-valuation-launches-collaborative-features/) then $125M at **$1.5B** (Mar 2026, https://techcrunch.com/2026/03/25/granola-raises-125m-hits-1-5b-valuation-as-it-expands-from-meeting-notetaker-to-enterprise-ai-app/).
4. **Autonomous negotiation agents** (async, not live-call): Pactum (Walmart procurement), CarEdge AI negotiator. Notably, the negotiation winners are *asynchronous agents*, not live teleprompters.

A counter-industry of detection vendors (InterviewGuard, Truffle, Fabric, Honorlock, SpaceComplexity) has formed in direct response.

## 2. Cluely deep-dive

**Origin/pivots.** Roy Lee launched **Interview Coder** (Feb 2025) after suspension from Columbia; claimed $1M ARR in 36 days / $110K MRR (self-reported, Indie Hackers: https://www.indiehackers.com/post/tech/from-zero-to-1m-arr-in-36-days-by-publicly-messing-with-big-tech-SRC9H50RFF9dV4n83ohl). Cluely launched April 2025 as "cheat on everything" with $5.3M seed (Abstract/Susa, https://techcrunch.com/2025/04/21/columbia-student-suspended-over-interview-cheating-tool-raises-5-3m-to-cheat-on-everything/). Pivot sequence: interview cheating → "cheat on everything" consumer → enterprise sales/meeting assistant (June–July 2025) → by Nov 2025, "the best AI notetaker, starting with the consumer" (https://techcrunch.com/2025/11/05/cluelys-roy-lee-hints-that-viral-hype-is-not-enough/). The "cheating" framing was deliberately softened once enterprise deals required it (https://medium.com/@olasenidavid/how-i-analyzed-cluelys-120m-pivot-my-first-ai-product-analysis-project-c4a451f19a4a).

**Funding.** $15M Series A from a16z, June 2025; ~$120M post-money per two outside investors (https://techcrunch.com/2025/06/20/cluely-a-startup-that-helps-cheat-on-everything-raises-15m-from-a16z/; a16z's own memo: https://a16z.com/announcement/investing-in-cluely/).

**ARR claims and the correction (key falsifiable event).** Lee claimed ARR went $3M → $7M in one week after the July 2025 enterprise launch (TechCrunch, above). On **March 5, 2026** he admitted the $7M figure was fabricated/inflated: real total ~**$5.2M** ($2.7M consumer + $2.5M enterprise), a ~35% gap (https://www.tipranks.com/news/private-companies/i-told-her-some-bs-cluely-ceo-admits-to-fabricating-revenue-numbers-from-last-year; https://www.inc.com/leila-sheridan/an-a16z-backed-startup-that-helps-people-cheat-on-job-interviews-just-got-caught-in-a-7-million-lie-the-ceo-was-sweating/91313070; analysis: https://developmentcorporate.com/saas/ai-startup-arr-manipulation-how-rage-bait-culture-normalized-lying-about-revenue/). Lee then posted a defiant video response (https://piunikaweb.com/2026/03/10/cluely-ceo-roy-lee-fires-back-techcrunch-revenue-lie-rant/). Bloomberg used the episode in its "ARR is the least-trusted metric of the AI era" piece (https://www.bloomberg.com/news/articles/2026-04-07/what-is-arr-behind-the-least-trusted-metric-of-the-ai-era).

**Retention.** No published cohort data. By Nov 2025 Lee refused to share numbers ("you should never share revenue numbers") and on retention said only "we're doing better than I expected, but it's not the fastest growing company of all time" and "maybe we launched too early" (https://techcrunch.com/2025/11/05/cluelys-roy-lee-hints-that-viral-hype-is-not-enough/). The refusal plus the notetaker pivot is the strongest indirect churn signal.

**Pricing.** Free (5 responses/day), Pro $20/mo, **Pro + Undetectability $75/mo** (stealth is literally a paid add-on), Enterprise ~$200/mo/seat (https://www.eesel.ai/blog/cluely-pricing; https://dupple.com/tools/cluely). One disclosed $2.5M enterprise contract claim (https://medium.com/@olasenidavid/how-i-analyzed-cluelys-120m-pivot-my-first-ai-product-analysis-project-c4a451f19a4a — self-reported by Lee, unverified).

**Controversy handling.** Strategy was rage-bait-as-distribution (viral "cheat on your date" ad), then progressive sanitization of messaging for enterprise. Security blemishes: a reported mid-2025 breach exposing ~83K users' records/transcripts/screenshots via an admin password left in a public GitHub repo, with DMCA notices sent to a researcher (https://geekbye.com/blog/best-cluely-alternatives; https://www.linkjob.ai/hub/cluely-risk — **competitor sources; treat as low-confidence until corroborated**), and a reported Electron postMessage flaw enabling silent screenshot capture (same caveat).

## 3. Other players + pricing

- **Final Round AI**: ~$6.9M seed-II (Jan 2025, https://tracxn.com/d/companies/final-round-ai/__jExsq_yeYZhlcwnffrolaaPsPaK8ZXTi3dPNjZJHLJE); markets "10M+ users" on its homepage (self-claimed, https://www.finalroundai.com/). Pricing complaints are the loudest in the category: advertised "$41.67/mo" resolving to a ~$500 annual commitment at checkout; tiers ~$96–148/mo; a Trustpilot analysis of 100 reviews found ~40% severe complaints — copilot freezing during live interviews, a "3-day money-back guarantee" functionally unusable, auto-renewals of $249–488, billing issues = 17% of 1-star reviews (https://rainaiservices.com/reviews/final-round-ai/; https://www.trustpilot.com/review/finalroundai.com).
- **LockedIn AI**: $54.99/mo (or $39.99 quarterly); markets "116ms responses" and "military-grade stealth" (vendor claims, https://www.lockedinai.com/compare/lockedinai-vs-parakeet-ai).
- **Parakeet AI**: ~$29 for 3 session credits, no refunds on accidentally-opened sessions; browser version visible to proctoring (https://interviewman.com/blog/best-parakeet-ai-alternative — competitor source).
- **Sensei AI**: ~$89/mo monthly or ~$24/mo annual; Chrome-extension-only, so visible during full-desktop shares (https://www.lockedinai.com/blog/sensei-ai-vs-lockedinai-comprehensive-review — competitor source).
- Note: most "comparison" content in this niche is competitor-published SEO; pricing pages are the only firm ground.

## 4. Detection / platform risk

- **Technique**: overlays render at a graphics layer (DirectX/Metal) below what Zoom/Teams/Meet screen-capture sees (https://spacecomplexity.ai/blog/ai-cheating-coding-interviews).
- **Detection is real and improving**: gaze-saccade analysis (reading vs. thinking), uniform 4–5s response latency before every answer, keystroke/copy-paste telemetry, follow-up probing; CoderPad reportedly flags Cluely's Cmd+Enter hotkey (https://www.aceround.app/blog/can-ai-be-detected-in-job-interviews/; https://interviewsidekick.com/blog/cluely-review).
- **Prevalence**: Fabric's 50K-candidate dataset shows detected cheating rising 15% (June 2025) → 35% (Dec 2025) (https://fabrichq.ai/blogs/state-of-cheating-in-interviews-in-2026-tools-trends-and-prevention — detection vendor, incentive to inflate).
- **Employer reaction (high confidence)**: Google reinstated at least one in-person interview round (Pichai, Aug 2025: https://www.entrepreneur.com/business-news/google-mckinsey-reintroduce-in-person-interviews-due-to-ai/496041); Amazon requires candidates to attest they won't use unauthorized tools; Cisco and McKinsey added face-to-face rounds (same source). Consequences for caught candidates include rescinded offers and early-tenure firings (https://aitrainer.work/guides/stealth-ai-coding-interview-assistant/).
- **Platform policy**: enterprise Teams/Zoom deployments increasingly block third-party bots and Google Meet flags them, pushing the market toward device-side ("bot-free") capture — which sidesteps platform enforcement but not recording-consent law (https://www.bliro.io/en/blog/transcribe-zoom-google-meet-teams-without-bots-joining-calls-the-top-3-bot-free-notetakers; https://tldv.io/blog/is-bot-free-recording-legal/; https://www.granola.ai/blog/ai-notetaker-participant-privacy-consent). No platform currently *detects* a local OS-level overlay; enforcement has shifted to the hiring/proctoring layer.

## 5. UX / latency lessons

- **The usability cliff is ~1–3 seconds.** Cresta engineering: pauses >~300ms feel unnatural; >~1.5s rapidly degrades experience (https://cresta.com/blog/engineering-for-real-time-voice-agent-latency). An arXiv enterprise sales-copilot study targets ~2.8s mean answer latency as acceptable for *rep-facing dashboards* (https://arxiv.org/html/2603.21416). Indie builders converge on "1–3 seconds, before the awkward silence" and report Electron overhead alone breaks this (https://www.indiehackers.com/post/ive-been-building-a-real-time-ai-copilot-for-sales-reps-every-tool-i-looked-at-only-helps-after-the-call-is-over-3bd90756bd).
- **Reality vs. claims**: Business Insider-style testing and Reddit reports put Cluely at 5–12s actual latency vs. a 300ms marketing claim, plus hallucinated resume details and outright freezes (https://interviewsidekick.com/blog/cluely-review; https://www.linkjob.ai/hub/cluely-high-latency; https://medium.com/@wenhaooyang/cluely-i-tried-the-ai-that-cheats-for-you-in-meetings-a53a89c01d56). Final Round users report garbled/slow answers mid-interview (https://www.trustpilot.com/review/finalroundai.com).
- **What works**: short, glanceable prompts (battle-card style à la Cresta) beat paragraph answers; reading full sentences aloud is precisely what gaze/timing detection catches. The dual-cognitive-load problem (listening + reading + speaking) is the recurring UX failure in reviews.

## 6. Positioning: stealth vs. transparent

Evidence strongly favors transparent/sanctioned positioning commercially:
- **Granola** (transparent-ish, no answer-feeding): $250M → **$1.5B** in ~10 months (TechCrunch links above).
- **Cresta** (employer-sanctioned): Forrester Leader, durable enterprise revenue (https://cresta.com/agent-assist).
- **Pactum** (transparent autonomous negotiation): Walmart — 68% of approached suppliers closed with the AI, ~3% avg savings, ~75% of suppliers *preferred* the bot (https://pactum.com/understanding-agentic-ai-in-procurement-how-autonomous-ai-has-been-transforming-supplier-deals/).
- **Cluely** (stealth): viral CAC machine but inflated-then-retracted ARR, refusal to disclose retention, and serial pivots *toward* the transparent notetaker category. Stealth generated attention, not durable revenue; every funded player has migrated toward sanctioned use cases.
- Stealth tools also carry structural churn (job seekers quit paying on hire) and legal exposure (consent statutes, breach liability).

## 7. Negotiation copilots specifically

No funded, real-time, in-call *negotiation* teleprompter exists at scale — this is a genuine gap. What exists:
- **CarEdge AI negotiator** (async agent, $50 flat): handles dealer calls/texts/emails; typical ~$1,500 off quote within ~3 days (https://wtop.com/local/2025/10/would-you-let-ai-negotiate-a-car-deal-for-you/; https://fortune.com/2025/09/10/this-30-year-old-ceo-says-his-ai-negotiator-can-successfully-haggle-down-the-price-of-a-car-by-thousands-of-dollars/).
- **DIY agents (MoltBot/Clawdbot)**: one user pitted 8–10 dealerships against each other, saving $4,200+ (https://mikemason.ca/writing/ai-negotiation-agents-jan-2026/ — anecdote).
- **Pactum**: enterprise procurement, autonomous chat, not live-call.
- **Secondus**: a real-time negotiation copilot (pressure-tactic detection, "what to say next") but it's a **Devpost hackathon project**, not a company (https://devpost.com/software/secondus-real-time-negotiation-copilot).
- Interview tools (LockedIn, OphyAI, InterviewMan) bolt on "salary negotiation" modes as marketing extensions of the same teleprompter (https://www.lockedinai.com/blog/the-role-of-ai-in-negotiating). The market's revealed lesson: for negotiation, *delegating* to an async agent beats *whispering* to a live human.

## Key falsifiable claims

| Claim | Source | Confidence |
|---|---|---|
| Cluely raised $15M from a16z, June 2025, ~$120M valuation | https://techcrunch.com/2025/06/20/cluely-a-startup-that-helps-cheat-on-everything-raises-15m-from-a16z/ | High |
| Lee admitted (Mar 5, 2026) the $7M ARR claim was false; real ~$5.2M ($2.7M consumer / $2.5M enterprise) | https://www.tipranks.com/news/private-companies/i-told-her-some-bs-cluely-ceo-admits-to-fabricating-revenue-numbers-from-last-year; https://www.inc.com/leila-sheridan/...91313070 | High |
| Lee refused to disclose revenue/retention by Nov 2025; pivoted to notetaker | https://techcrunch.com/2025/11/05/cluelys-roy-lee-hints-that-viral-hype-is-not-enough/ | High |
| Cluely charges $75/mo extra specifically for "undetectability" | https://www.eesel.ai/blog/cluely-pricing | Medium-high |
| Cluely real latency 5–10s vs 300ms claimed | https://interviewsidekick.com/blog/cluely-review | Medium |
| Cluely breach exposed ~83K users via public-repo admin password | https://geekbye.com/blog/best-cluely-alternatives (competitor) | Low-medium — needs primary corroboration |
| Final Round AI: ~40% severe complaint rate in 100-review Trustpilot sample; auto-renew $249–488 | https://rainaiservices.com/reviews/final-round-ai/; https://www.trustpilot.com/review/finalroundai.com | Medium |
| Google reinstated in-person interview rounds over AI cheating (Pichai) | https://www.entrepreneur.com/business-news/google-mckinsey-reintroduce-in-person-interviews-due-to-ai/496041 | High |
| Detected interview cheating rose 15%→35% Jun–Dec 2025 (50K candidates) | https://fabrichq.ai/blogs/state-of-cheating-in-interviews-in-2026-tools-trends-and-prevention | Medium (vendor data) |
| >1.5s response latency rapidly degrades live-voice UX | https://cresta.com/blog/engineering-for-real-time-voice-agent-latency | High |
| Granola (transparent) hit $1.5B valuation Mar 2026 | https://techcrunch.com/2026/03/25/granola-raises-125m-hits-1-5b-valuation-as-it-expands-from-meeting-notetaker-to-enterprise-ai-app/ | High |
| Walmart/Pactum: 68% close rate, ~3% savings, 75% supplier preference for bot | https://pactum.com/understanding-agentic-ai-in-procurement-how-autonomous-ai-has-been-transforming-supplier-deals/ | Medium (vendor) |
| No funded real-time negotiation teleprompter exists; closest are async agents (CarEdge) and a hackathon project (Secondus) | https://fortune.com/2025/09/10/...; https://devpost.com/software/secondus-real-time-negotiation-copilot | Medium (absence-of-evidence) |

**Bottom line**: stealth real-time copilots proved distribution genius but product failure — latency 2–4x past the usability cliff, rising detection, structural churn, and the category leader caught inflating revenue. Commercial gravity pulls every survivor toward transparent, sanctioned, or asynchronous-agent positioning; live negotiation copiloting remains an open, unproven niche.