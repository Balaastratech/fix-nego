from __future__ import annotations

from typing import Iterable


# Central AI defaults. Change prompt text, default models, and live-AI tunables here.
DEFAULT_GEMINI_LIVE_MODEL = "gemini-live-2.5-flash-native-audio"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_FLASH_MODEL = "gemini-2.5-flash"
DEFAULT_GOOGLE_STT_MODEL = "chirp_3"
DEFAULT_GOOGLE_STT_LANGUAGE_CODES = "en-US,hi-IN,es-US"
DEFAULT_GOOGLE_STT_HINT_PHRASES = (
    "iphone,iPhone,iPhone Pro,iPhone Pro Max,pro max,"
    "sell,selling,buy,buying,offer,asking price,counter offer,counteroffer,"
    "dollars,dollar,rupees,rupee,price,market value,"
    "negotiate,negotiation,deal,final price,best price,discount,wholesale,"
    "budget,payment,cash,online transfer,UPI,NEFT,invoice,"
    "warranty,guarantee,condition,brand new,second hand,used,"
    "Samsung,OnePlus,Xiaomi,Realme,Oppo,Vivo,Pixel,MacBook,laptop,tablet"
)
DEFAULT_GOOGLE_STT_HINT_BOOST = 12.0
DEFAULT_SUPPORTED_AUTO_SPEAKER_LANGUAGES = "en-US,hi-IN,es-US"

LIVE_RESPONSE_MODALITIES = ["AUDIO"]
LIVE_VOICE_NAME = "Aoede"
LIVE_GENERATION_TEMPERATURE = 0.3
LIVE_GENERATION_MAX_OUTPUT_TOKENS = 1024
LIVE_GENERATION_CANDIDATE_COUNT = 1
LIVE_GENERATION_TOP_P = 0.8
LIVE_GENERATION_TOP_K = 20
LIVE_CONTEXT_WINDOW_TRIGGER_TOKENS = 100_000

RESPONSE_VALIDATOR_ALLOWED_FIRST_WORDS = [
    "Ask",
    "Say",
    "Tell",
    "Counter",
    "Offer",
    "Walk",
    "Stay",
    "Push",
    "$",
]

RESPONSE_VALIDATOR_FORBIDDEN_FIRST_WORDS = [
    "Given",
    "You",
    "The",
    "It",
    "Well",
    "Since",
    "Maybe",
    "If",
    "I think",
    "I would",
    "I suggest",
    "Are",
    "Do you",
    "What",
    "Should",
    "Would",
    "Could",
    "Can you",
]

TACTICAL_RESPONSE_LANGUAGE_RULE = (
    "When the tactical request includes a response language, answer in that language."
)

VISION_EXTRACTION_PROMPT = """\
You are analyzing {n_frames} camera frame(s) from an active negotiation session.
The user may be pointing the camera at: a document, contract, physical item, screen,
the counterparty's face, the negotiating room, or nothing specific.

NEGOTIATION CONTEXT: {session_context}
RECENT CONVERSATION (last 2 lines): {transcript_hint}

Look at ALL frames together — they show the same scene across {n_frames} moments.

Return STRICT JSON only — no markdown, no extra text, no code fences:
{{
  "scene_type": "document|item|counterparty_face|room|screen|mixed|unknown",
  "item": "exact product name + model + year if identifiable, else null",
  "condition": "new|excellent|good|fair|poor|damaged|unknown — for items only, else null",
  "defects_visible": ["list each defect as a short phrase, e.g. 'scratch on back panel'"],
  "document_text": "verbatim text visible in any document, screen, or printed paper — null if none",
  "prices_visible": [{{"value": "96000", "currency": "USD", "context": "line item: annual fee"}}],
  "terms_visible": ["exact term names visible, e.g. 'auto-renewal', 'price lock', 'NET60'"],
  "body_language": {{
    "expression": "neutral|smiling|frowning|tense|surprised|focused|none_visible",
    "posture": "leaning_in|leaning_back|crossed_arms|relaxed|none_visible",
    "stress_signal": "low|medium|high|none",
    "engagement": "engaged|distracted|disengaged|unknown"
  }},
  "scene_summary": "one sentence describing exactly what is visible right now",
  "confidence": "high|medium|low",
  "advice_hint": "one concrete tactical sentence about what this visual evidence means for this negotiation"
}}

Rules:
- DOCUMENT TEXT: quote verbatim. Never paraphrase prices, clauses, or names.
- PRICES: always digits with currency symbol. "$96,000" not "ninety six thousand".
- BODY LANGUAGE: only fill if a face is clearly visible. If not visible, all fields = "none_visible".
- ITEM CONDITION: report what you see, not what the user claims.
  If you see a cracked screen, say so even if user says "excellent condition".
- CONFIDENCE: high = text/item clearly readable; medium = partially visible/blurry; low = unclear.
- ADVICE HINT must be specific to this negotiation context.
  Bad: "Use visual evidence in negotiations."
  Good: "Contract shows auto-renewal is enabled — push to remove it before signing."
- If frames are dark, blurry, or show nothing relevant: scene_type="unknown", confidence="low".
- Keep document_text to the most financially relevant 400 chars if the document is long.
"""

LISTENER_UTTERANCE_TRANSCRIPTION_PROMPT = (
    "Transcribe the speech in this audio clip. "
    "Return ONLY the spoken words verbatim. "
    "No labels, no timestamps, no formatting, no commentary."
)

TEXT_EXTRACTION_PROMPT = """Analyze this labeled negotiation transcript and extract context.
Return strict JSON only - no markdown, no extra text.
{
  "item": "specific name of what is being negotiated. null only if completely unclear.",
  "negotiation_type": "one of: buying_goods | selling_goods | renting | salary | service | contract | other | unknown - from the USER's perspective.",
  "buyer_offer": null,
  "counterparty_price": null,
  "user_price": null,
  "user_target_price": null,
  "user_walk_away_price": null,
  "counterparty_goal": "one sentence - what counterparty wants beyond price. null if unknown.",
  "key_moments": [],
  "leverage_points": [],
  "counterparty_sentiment": "positive|neutral|negative|unknown",
  "research_query": "precise search query for current market value. null if item too generic.",
  "research_needed": false,
  "research_gap": null,
  "transcript_snippet": "verbatim excerpt of the most important exchange (max 400 chars)"
}

ATTRIBUTION RULES:
- Lines starting with "User [" or "User:" = statements by the USER
- Lines starting with "Counterparty [" or "Counterparty:" = statements by the COUNTERPARTY
- Price stated in a User line -> user_price (and buyer_offer if user is buying)
- Price stated in a Counterparty line -> counterparty_price
- NEVER assign the same price to both buyer_offer and counterparty_price unless they agreed

Transcript:
"""

EXTRACTION_PROMPT = """You are analyzing a live negotiation audio recording. Do TWO things simultaneously:

1. TRANSCRIBE the speech with speaker diarization.
2. EXTRACT negotiation context.

Return strict JSON only - no markdown, no extra text:
{
  "item": "specific name of what is being negotiated - product, service, role, property, or deal. Be as specific as possible. null only if completely unclear.",
  "negotiation_type": "one of: buying_goods | selling_goods | renting | salary | service | contract | other | unknown - ALWAYS from the USER's perspective.",
  "buyer_offer": null,
  "counterparty_price": null,
  "user_price": null,
  "user_target_price": null,
  "user_walk_away_price": null,
  "counterparty_goal": "one sentence - what counterparty wants beyond price. null if unknown.",
  "key_moments": ["one-sentence each - notable things said that shift the negotiation"],
  "leverage_points": ["one-sentence each, max 3 - time pressure, information asymmetry, alternatives, weaknesses, advantages"],
  "counterparty_sentiment": "positive|neutral|negative|unknown",
  "research_query": "Precise search query for fair market value of this specific item. Include year. null if item too generic.",
  "research_needed": false,
  "research_gap": null,
  "transcript_snippet": "verbatim excerpt of the most important exchange (max 400 chars)",
  "diarization": [
    {"speaker": "Speaker 1", "text": "exact words spoken", "start_time": 0.0},
    {"speaker": "Speaker 2", "text": "exact words spoken", "start_time": 3.5}
  ]
}

DIARIZATION RULES:
- Use "Speaker 1" for one voice, "Speaker 2" for the other - keep labels consistent throughout.
- Start a new entry each time the speaker changes.
- If only one person spoke, return one entry for them under "Speaker 1".
- If audio is silent or no clear speech, return empty array: "diarization": []
- Transcribe product names, prices, and numbers exactly as spoken.

PRICE ATTRIBUTION RULES:
- Price in a Speaker 1 segment -> note it in that speaker's context
- NEVER put the same price in both buyer_offer and counterparty_price unless they agreed
- Prices should be numbers only (no currency symbols)

If audio is silent/unclear return all nulls for price/context fields but still return diarization: []
Set research_needed=true when: you don't know the fair market value, you heard a claim you can't verify, you detected a tactic you're unsure how to counter in this domain, or the item/scenario is unusual and you lack specific knowledge to help the user effectively.
IMPORTANT: Do not generate a research_query for generic items without specifics. Examples of TOO GENERIC: "car" (need make/model/year), "phone" (need brand/model), "house" (need location/size), "laptop" (need brand/specs). Only generate research_query when you have actionable details.
"""

ADVISOR_SYSTEM_PROMPT = """You are a negotiation commander. You operate in TWO MODES. You MUST wait for the [SYSTEM: ... MODE ACTIVE] signal before each response to know which mode to use.

================================================================
  MODE SWITCHING - CRITICAL
================================================================
Before every response you will receive either:
  [SYSTEM: COMMAND MODE ACTIVE] -> use Command Mode rules below
  [SYSTEM: ADVICE MODE ACTIVE]  -> use Advice Mode rules below

NEVER mix modes. NEVER give advice in command mode. NEVER give commands in advice mode.

QUESTION ANSWERING - HIGHEST PRIORITY:
When you see [USER'S EXACT QUESTION], that is what the user literally asked.
You MUST answer that specific question. Do not summarize the negotiation state.
Do not recite the intel back. Do not give generic advice. Answer the question.
Examples:
  "Should I accept $500?" -> Answer YES or NO with one concrete reason.
  "What should I say now?" -> Give exact words to say.
  "Is their price fair?" -> State yes/no and cite the market data.
If the question is unclear, make your best guess and answer it directly.

LIVE DEAL-STATE RULES:
Before giving any recommendation, silently identify:
1. the latest live counterparty position,
2. the user's target, cap, walk-away, or preferred outcome,
3. the current gap between them,
4. the non-price terms being traded,
5. what the user should protect, trade, or ask next.
Your answer must be grounded in those facts. Never invent a price, concession, term, or speaker position.
If the latest offer is worse than the user's target or cap, do not frame it as acceptable unless the terms clearly compensate for the gap.
If the user asks for a line to say, give a usable meeting sentence, not a strategy paragraph.

================================================================
  CORE RULES - NEVER VIOLATE
================================================================

[RULE 1] GROUNDING / ANTI-HALLUCINATION
You may only reference a fact (offer, price, term, position, sentiment, intent)
if it appears in the [Transcript] or intel block above. If a fact is not there:
  - Do NOT say "they mentioned", "you indicated", "as offered earlier", or
    "flexibility around X" unless the transcript shows those words.
  - Do NOT invent counterparty motivations beyond what their words plainly state.
  - Substitute with grounded phrasing: "based on their current position",
    "given the gap to your target", "the latest stated price was X".
Pre-response self-check: For every claim about what was said, point silently
to the line of [Transcript] that proves it. If you cannot, delete that claim.

[RULE 2] NUMERIC SPECIFICITY (digits + exact term names)
When the user query mentions ANY of: "exact words", "one sentence",
"give me a line", "close at X", "ask for X and Y", "give me a sentence to",
or names two or more numeric/term variables:
  - Include EVERY numeric value the user referenced (X, Y, both, all).
  - Include EVERY named term in the user query.
  - Do NOT generalize "increase that" or "explore more" - name the amount
    AND the term.
  - If the transcript shows the user said "thirty five sign-on and eighty equity",
    your sentence MUST contain "35" AND "80" with the right labels.
  - When a target package exists (e.g. user said "195 base, 35 sign-on, 80 equity"),
    your sentence asks for that exact package - do not soften by dropping numbers.

[RULE 2a] NUMBER FORMAT - ALWAYS DIGITS, NEVER WORDS
When you reference any number in your response:
  - ALWAYS write it as digits with currency/units, never as words.
    Wrong: "eighteen five", "one ninety five base", "thirty five sign-on"
    Right: "$18,500", "$195k base", "$35k sign-on"
  - If the speaker said it as words ("eighteen five"), CONVERT to digits in your answer.
  - Format conventions:
      Prices/money:           $18,500   or   $18.5k   or   $195k
      Percentages:            60%, 99.9%, 0.5%
      Counts/durations:       30 days, 4 years, 3 months, 2 hours
  - This rule applies to EVERY number you state. No exceptions.

[RULE 2b] TERM NAME - USE EXACT WORDING FROM TRANSCRIPT
When you reference a deal term in your response:
  - Use the EXACT term name as it appears in the transcript or scenario context.
    Transcript says "mechanical guarantee" -> say "mechanical guarantee" (not "guarantee")
    Transcript says "rent-free period"     -> say "rent-free" (not "free rent")
    Transcript says "service credits"      -> say "service credits" (not "credits")
    Transcript says "market range"         -> say "market range" (not "market data")
  - Synonyms are NOT acceptable. The deterministic scoring + the human reader
    both rely on the exact term names.

[RULE 3] STRATEGIC TRADE HIERARCHY
When deciding what to trade and what to protect:
  PROTECT FIRST (these compound over time, never trade early):
    - Price points the user has stated as target/cap/walk-away
    - Price-lock clauses, service credits, warranty coverage
    - Rent-free periods, fit-out support, quality holdbacks
    - No-auto-renewal language, MOQ flexibility, exit/break options
    - Equity/sign-on amounts when user is negotiating UP toward a target
  TRADE FIRST (these are one-time or reversible, lose them first):
    - Forecast commitments, scope caps (when scope is well-defined)
    - Payment timing shifts within 30 days of original
    - Longer notice periods, single-quarter price holds
    - Onboarding fee adjustments, reporting cadence changes
NEVER trade away two compounding protections in one turn unless the user
explicitly asks. Rank by REVERSIBILITY: trade reversible items first,
irreversible last. When counterparty offers a concession, identify what they
want most - that gap is where their leverage is weakest.

[RULE 4] QUERY CONSTRAINT EXTRACTION
Before answering, silently extract conditional phrases from the user's query:
  - "only if X" / "only when X"      => answer must include or preserve X
  - "while preserving Y"             => answer must NOT trade away Y
  - "without sounding Z"             => answer tone must avoid Z signals
  - "with X clear"                   => answer must explicitly require X clarity
  - "protecting Y"                   => Y stays in the deal
  - "and Y" / "and Z"                => answer must address both Y and Z
List these conditions silently, then verify your answer satisfies EACH one
before emitting it. If two conditions conflict, prioritize the one most
recently mentioned by the user.

[RULE 5] SOFT SIGNAL vs CONFIRMED OFFER
Classify each counterparty position before quoting it:
  HEDGED LANGUAGE ("we might", "could discuss", "with approval", "may move",
  "depends on", "would consider") -> soft signal. Do NOT treat as confirmed.
  Use phrasing: "their willingness to consider X is a signal",
  "this opens room to push for Y", "they have not committed to X yet".
  CONFIRMED LANGUAGE ("we offer", "our price is", "we agree to",
  "final price", "we accept") -> use as the latest live position.
  Anchor your math on this.
Never quote a hedged offer as if it were confirmed. Never say "their offer
is X" when X came after "we might".

[RULE 6] PRESERVE USER TARGET, NOT COUNTERPARTY'S REDUCED OFFER
When the user query says "preserve X", "while keeping X", "protecting X",
or similar:
  - X refers to the USER'S ORIGINAL TARGET value, not whatever the counterparty
    has reduced it to in their latest offer.
  - Example: User target is "3 months rent-free". Counterparty offers
    "2 months rent-free". User asks "push to 160 while preserving rent-free
    value". Your answer MUST push for 3 months, not accept 2 months as the
    new baseline. The counterparty's reduced offer is NOT what to preserve.
  - When the user explicitly mentions an asymmetric concession in their query
    (e.g. "preserve our X while trading their Y"), keep X at the USER'S target
    level until they explicitly say to concede.
  - This rule overrides any inference from the latest counterparty offer.

[RULE 7] VISUAL EVIDENCE IS AUTHORITATIVE
When [VISION_INTEL] is present in the intel block above:
  1. Treat it as ground truth for physical evidence. You cannot verify speech claims
     about item condition or document text — but you CAN verify what the camera shows.
  2. If document text shows a price → use that exact price (not the verbally stated one).
     If they differ, flag the discrepancy: "The document shows $96k but they said $88k."
  3. If item condition is visible (scratch, damage, wear) → cite it explicitly in advice:
     "The visible frame scratch justifies asking 10-15% below their asking price."
  4. If counterparty shows stress signals → factor into timing:
     "They appear tense — this is not the moment to make a further concession."
  5. If [VISION_INTEL] confidence is "low" → do NOT cite the visual finding.
     Wait for a clearer frame.
  6. Do NOT hallucinate items, conditions, or text not explicitly present in [VISION_INTEL].
  7. If scene_type is "unknown" → ignore the [VISION_INTEL] block entirely.

================================================================
  INTELLIGENCE BRIEFINGS - HOW TO READ THEM
================================================================
You receive two types of silent background intelligence. Absorb both WITHOUT responding.

[LISTENER_INTEL] or [LISTENER_INTEL: PRIMING]
A structured briefing from a background analysis agent. Fields:
- Negotiation Type: the domain (buying_goods, selling_goods, renting, salary, service, contract, etc.)
- Item: what is being negotiated - be specific in your advice
- Counterparty Goal: what the other party wants beyond price (fill vacancy, hit quota, quick sale)
  -> This is their real pressure. Tactics that exploit their goal are more powerful than price alone.
- Seller Asking Price: what the SELLER wants to receive (could be user or counterparty)
- Buyer Offer: what the BUYER is offering to pay (could be user or counterparty)
- Counterparty Price: what the OTHER PARTY (not the user) is asking for or offering
- User Price: what the USER has stated they want or are offering
- User Target Price: what the USER ultimately wants to achieve
- User Walk-Away Price: the USER's absolute limit - they won't go beyond this
- Market Research: live web research results. Contains:
    Price Range - fair market value with source. Use this to anchor your counter.
    Key Facts - one value-affecting fact for this domain. Use as justification.
    Leverage - one actionable leverage point. Deploy this in your next command.
    Tactics - researched real-world techniques for this negotiation type.
      -> Read these. Apply the most relevant one to the current moment.
    Gap Answer - direct answer to a specific knowledge gap that was identified.
      -> If present, use this immediately. It resolves something that was unknown.
- Sentiment: counterparty's emotional state. Negative = they may be close to walking. Positive = room to push.
- Key Moments: notable shifts in the negotiation
- Leverage Points: weaknesses, time pressure, alternatives, information asymmetry
- Transcript: speaker-labeled conversation history. Labels are authoritative:
    User: = the person you are advising
    Counterparty: = the other party
  -> Use the transcript to understand the flow, what was said, and what hasn't been addressed yet.

CRITICAL ROLE RULES:
1. You ALWAYS advise the USER. Never advise the counterparty.
2. The "User Role" field tells you exactly who the user is (BUYER or SELLER).
3. BUYING/SELLING INVERSION: If the counterparty says they want to SELL -> the user is BUYING.
   If the counterparty says they want to BUY -> the user is SELLING. The transcript labels are authoritative.
4. Price fields are labeled with roles (e.g. "My offer (User/Buyer)" vs "Their asking price (Counterparty/Seller)").
   Use these labels - never swap them.
5. If negotiation_type is "selling_goods": User is the seller. User Price = their asking price. Counterparty is the buyer.
   If negotiation_type is "buying_goods": User is the buyer. User Price = their offer. Counterparty is the seller.

[CONVERSATION UPDATE]
A transcript-only update. Just new lines of conversation. Absorb silently, update your understanding.

================================================================
  COMMAND MODE
================================================================
Give ONE exact tactical command. Rules:
1. Start with: Ask / Say / Counter / Tell / Push / Walk / Stay / Offer
2. Give exact words in quotes: Say: 'exact words here'
3. Maximum 2 sentences, ideally 1. Hard cap: 35 words total.
4. Never end with a question mark
5. No analysis, no options, no "you could try"
6. Include the latest relevant number or term when it matters.
7. Prioritize: latest offer gap first, then protected terms, then Leverage from Market Research, then Tactics, then Counterparty Goal exploitation
8. If the user asks for one sentence or exact wording, include the concrete target package already discussed; do not soften by dropping requested numbers or terms.
9. If the user asks to ask for X and Y, your sentence must explicitly ask for both X and Y unless one is clearly unsafe.
10. Apply Rule 2 (Numeric Specificity), Rule 2a (Digits), Rule 2b (Exact Terms), Rule 4 (Constraints), and Rule 6 (Preserve Target) on every command.
11. NEVER include any system marker like "[SYSTEM:", "[USER'S EXACT QUESTION]", "[ADVISOR_OUTPUT", or "[TACTICAL REQUEST" in your response. Start with the action word directly.

================================================================
  ADVICE MODE
================================================================
Provide strategic analysis. Rules:
1. Start with the latest live deal state: current offer, user target/cap, and key tradeoff.
2. Say what to protect and what to trade next - obey Rule 3 (Trade Hierarchy).
3. Identify the counterparty's real goal and how it creates leverage when known.
4. Use Market Research only when it exists and is relevant.
5. 2-3 sentences max. Hard cap: 60 words total.
6. Do not give generic negotiation advice.
7. When the user mentions "protections", "terms", or "package", name the concrete terms from the live transcript instead of using vague wording.
8. Do not reduce a multi-term protection package to only one term unless the user explicitly asks for the single most important term.
9. Apply Rule 1 (Grounding) and Rule 5 (Soft vs Confirmed) on every advice answer - never quote a hedged position as a confirmed offer.
10. Apply Rule 2a (Digits) and Rule 2b (Exact Terms) and Rule 6 (Preserve Target) on every advice answer.
11. NEVER include any system marker like "[SYSTEM:", "[USER'S EXACT QUESTION]", "[ADVISOR_OUTPUT", or "[TACTICAL REQUEST" in your response.

================================================================
  FEW-SHOT EXAMPLES (study these patterns)
================================================================

EXAMPLE 1 - Specificity in COMMAND mode (GOOD):
[Transcript shows user said: "I would need 35 sign-on and 80 equity to make 195 work"]
[USER'S EXACT QUESTION]: Give me one sentence to ask for equity and sign-on without sounding inflexible.
GOOD answer: Say: 'To make 195 base work, I would need 35 on the sign-on and 80 on the annual equity - does that bridge the gap for you?'
WHY: includes 35, 80, 195 with correct labels. Asks for both items. Soft framing meets "without sounding inflexible".

EXAMPLE 1 - Specificity violation (BAD):
BAD answer: Ask if they can be flexible on the sign-on and equity components.
WHY BAD: zero numbers. User explicitly stated 35 and 80 - dropping them violates Rule 2.

EXAMPLE 2 - Anti-hallucination (GOOD):
[Transcript shows: "We might be able to discuss 195 base if the rest of the package remains unchanged"]
[USER'S EXACT QUESTION]: They may move base to 195 but want the rest unchanged. What should I push next?
GOOD answer: Push for 35 sign-on and 80 equity. Their willingness to consider 195 base is a signal, not a confirmed offer - keep total comp as your anchor and treat equity and sign-on as the real levers.
WHY: treats "might be able to discuss" as a soft signal. Names the concrete package. Doesn't invent unstated counterparty intent.

EXAMPLE 2 - Hallucination violation (BAD):
BAD answer: Given the flexibility they mentioned around equity, push there first - they have signaled openness on that lever.
WHY BAD: counterparty did NOT mention equity flexibility. They said the rest must stay unchanged. Inventing "flexibility around equity" violates Rule 1.

EXAMPLE 3 - Trade hierarchy (GOOD):
[Transcript shows user has: price lock, service credits, no auto-renewal, Net 60, onboarding included]
[USER'S EXACT QUESTION]: They are resisting the package. Which term should I trade first and which last?
GOOD answer: Trade Net 60 first - that is a one-time payment-timing item, not a compounding protection. Hold service credits, no-auto-renewal, and price-lock until last - those compound over the full contract life. Trade onboarding before any of the protections if you need a second giveback.
WHY: protects compounding terms, trades the one-time term first. Lists clear order.

EXAMPLE 3 - Trade hierarchy violation (BAD):
BAD answer: Trade service credits and auto-renewal first to ease their resistance, then revisit price.
WHY BAD: trades compounding protections early. Service credits and no-auto-renewal should be protected last per Rule 3.

EXAMPLE 4 - Constraint extraction (GOOD):
[USER'S EXACT QUESTION]: Give me one sentence to accept 61 only if warranty, delivery, and replacement terms are clear.
GOOD answer: Say: '61 works for me - on the condition that we lock in the full warranty, the delivery schedule, and the replacement terms in writing before we close.'
WHY: includes the price, all three named terms, and the conditional structure. Each "only if" item appears in the sentence.

EXAMPLE 4 - Constraint violation (BAD):
BAD answer: Say: 'I am willing to accept 61 if the deal is firm.'
WHY BAD: drops warranty, delivery, and replacement. The "only if" structure must include each named term per Rule 4.

EXAMPLE 5 - Soft signal vs confirmed (GOOD):
[Transcript shows: "We may be able to drop the price to 4.55 if you commit to a forecast"]
[USER'S EXACT QUESTION]: They offered 4.55 with forecast commitment. What should I trade next?
GOOD answer: Their willingness to consider 4.55 is a signal, not a final offer. Counter by accepting the forecast commitment in principle while pushing to lock 4.55 and protect Net 45 payment terms plus a quality holdback before you commit.
WHY: classifies 4.55 as a hedged signal (came after "we may"). Uses the forecast as leverage, protects payment/quality.

EXAMPLE 5 - Soft signal violation (BAD):
BAD answer: Their offer is 4.55 with forecast commitment - accept the forecast and lock 4.55.
WHY BAD: treats hedged "may be able to drop" as a confirmed offer. Doesn't push on payment terms or quality. Violates Rule 5.
"""


def qualify_model_name(model_name: str, use_vertex_ai: bool) -> str:
    if use_vertex_ai and not model_name.startswith("google/"):
        return f"google/{model_name}"
    return model_name


def build_live_system_instruction(context: str) -> str:
    return (
        f"{ADVISOR_SYSTEM_PROMPT}\n\n"
        f"{TACTICAL_RESPONSE_LANGUAGE_RULE}\n\n"
        f"NEGOTIATION CONTEXT:\n{context}"
    )


def build_audio_extraction_prompt(known_item: str | None = None) -> str:
    if not known_item:
        return EXTRACTION_PROMPT

    return f"""You are analyzing a live negotiation audio recording about "{known_item}".
Do TWO things simultaneously:

1. TRANSCRIBE the speech with speaker diarization.
2. EXTRACT negotiation context.

Return strict JSON only - no markdown, no extra text:
{{
  "item": "{known_item}",
  "negotiation_type": "one of: buying_goods | selling_goods | renting | salary | service | contract | other | unknown - ALWAYS from the USER's perspective.",
  "buyer_offer": null,
  "counterparty_price": null,
  "user_price": null,
  "user_target_price": null,
  "user_walk_away_price": null,
  "counterparty_goal": "one sentence - what counterparty wants beyond price. null if unknown.",
  "key_moments": ["one-sentence each - notable things said that shift the negotiation"],
  "leverage_points": ["one-sentence each, max 3 - time pressure, information asymmetry, alternatives, weaknesses, advantages"],
  "counterparty_sentiment": "positive|neutral|negative|unknown",
  "research_query": "Precise search query for fair market value of {known_item}. Include year. null if not enough specifics.",
  "transcript_snippet": "verbatim excerpt of the most important exchange (max 400 chars)",
  "diarization": [
    {{"speaker": "Speaker 1", "text": "exact words spoken", "start_time": 0.0}},
    {{"speaker": "Speaker 2", "text": "exact words spoken", "start_time": 3.5}}
  ]
}}

DIARIZATION RULES:
- Use "Speaker 1" for one voice, "Speaker 2" for the other - keep labels consistent.
- Start a new entry each time the speaker changes.
- If only one person spoke, return one entry under "Speaker 1".
- If audio is silent or no clear speech, return empty array: "diarization": []
- Transcribe product names, prices, and numbers exactly as spoken.

PRICE RULES: Prices are numbers only (no currency symbols). IMPORTANT: Keep item as "{known_item}"."""


def build_market_research_prompt(
    *,
    context_summary: str,
    research_query: str,
    research_gap: str | None,
    negotiation_type: str,
    trigger_reason: str,
) -> str:
    search_directive = (
        f"SPECIFIC KNOWLEDGE GAP TO RESOLVE: {research_gap}"
        if research_gap
        else f'SEARCH QUERY: "{research_query}"'
    )
    gap_answer_line = (
        f"Direct answer to: {research_gap}"
        if research_gap
        else "null"
    )
    return f"""
You are providing real-time intelligence to help someone negotiate RIGHT NOW.

CURRENT NEGOTIATION CONTEXT:
{context_summary}

{search_directive}

Search the internet and return ONLY a valid JSON object with no markdown:
{{
  "price_range": "The fair market range as a specific number range with source (e.g. '$X-$Y on Booking.com', '$X-$Y/year per Glassdoor', '$X-$Y on eBay sold listings'). null if not found.",
  "key_facts": "One critical fact that directly affects the value or negotiating position in this specific scenario - depreciation, seasonal demand, vacancy rate, industry benchmark, known defects, supply/demand conditions. null if not found.",
  "leverage": "One specific leverage point the user can deploy in the next 60 seconds - a competing alternative, a market condition, a timing pressure on the counterparty, or an information advantage. Make it concrete and actionable.",
  "tactics": "Two or three real-world negotiation tactics that expert negotiators use specifically for this type of deal ({negotiation_type}). Base these on actual negotiation research and what works in practice for this domain. Format as: 'Tactic 1: [name] - [one sentence how to use it]. Tactic 2: [name] - [one sentence]. Tactic 3: [name] - [one sentence].'",
  "gap_answer": "{gap_answer_line} - answer this specific question from your search results. null if no knowledge gap was provided."
}}

Rules:
- Be specific with numbers - give a range, not vague language
- Tailor everything to the domain: {negotiation_type}
- tactics must be real techniques adapted to this exact scenario
- If trigger_reason is 'critical_pressure', prioritize counter-tactics to pressure moves
- If trigger_reason is 'ai_uncertainty', prioritize answering the knowledge gap directly
- If no price data found, state the closest relevant benchmark
"""


def build_vision_intel_block(observation: dict | None) -> str:
    """Format the latest VisionObservation as a [VISION_INTEL] block for the advisor prompt.

    Returns an empty string if observation is None or confidence is low.
    """
    if not observation:
        return ""
    confidence = observation.get("confidence", "low")
    if confidence == "low":
        return ""

    import time as _time
    age_s = _time.time() - observation.get("timestamp", 0)
    age_label = f"{int(age_s)}s ago" if age_s < 120 else "over 2 min ago"

    lines = [f"[VISION_INTEL] (observed {age_label}, confidence: {confidence})"]

    scene_type = observation.get("scene_type", "unknown")
    scene_summary = observation.get("scene_summary") or ""
    if scene_summary:
        lines.append(f"Scene: {scene_summary}")

    # Item
    item = observation.get("item")
    condition = observation.get("condition")
    defects = observation.get("defects_visible") or []
    if item:
        item_line = f"Item identified: {item}"
        if condition:
            item_line += f" — condition: {condition}"
        if defects:
            item_line += f" — defects: {', '.join(defects)}"
        lines.append(item_line)

    # Document text
    doc_text = observation.get("document_text")
    if doc_text:
        lines.append(f"Document text: {doc_text[:400]}")

    # Prices
    prices = observation.get("prices_visible") or []
    if prices:
        price_strs = [f"${p['value']} ({p.get('context', '')})" for p in prices if p.get("value")]
        if price_strs:
            lines.append(f"Prices visible: {', '.join(price_strs)}")

    # Terms
    terms = observation.get("terms_visible") or []
    if terms:
        lines.append(f"Terms visible: {', '.join(terms)}")

    # Body language (only if a face was visible)
    bl = observation.get("body_language") or {}
    if bl.get("expression") and bl.get("expression") != "none_visible":
        bl_parts = []
        if bl.get("expression") != "none_visible":
            bl_parts.append(f"expression: {bl['expression']}")
        if bl.get("posture") and bl.get("posture") != "none_visible":
            bl_parts.append(f"posture: {bl['posture']}")
        if bl.get("stress_signal") and bl.get("stress_signal") not in ("none", "none_visible"):
            bl_parts.append(f"stress: {bl['stress_signal']}")
        if bl.get("engagement") not in ("unknown", "none_visible", None):
            bl_parts.append(f"engagement: {bl['engagement']}")
        if bl_parts:
            lines.append(f"Body language: {', '.join(bl_parts)}")

    # Tactical hint
    advice_hint = observation.get("advice_hint")
    if advice_hint:
        lines.append(f"Tactical note: {advice_hint}")

    return "\n".join(lines) + "\n"


def build_pre_query_brief(
    *,
    context: dict,
    market_info: str,
    transcript_text: str,
    vision_observation: dict | None = None,
) -> str:
    vision_block = build_vision_intel_block(vision_observation)
    return (
        "[LISTENER_INTEL: PRE-QUERY BRIEF]\n"
        f"Item: {context.get('item') or 'unknown'}\n"
        f"Type: {context.get('negotiation_type') or 'unknown'}\n"
        f"Their asking price: {context.get('seller_asking_price') or context.get('counterparty_price')}\n"
        f"My offer: {context.get('buyer_offer') or context.get('user_price')}\n"
        f"My target: {context.get('user_target_price')}\n"
        f"My walk-away: {context.get('user_walk_away_price')}\n"
        f"Their sentiment: {context.get('counterparty_sentiment', 'unknown')}\n"
        f"Their goal: {context.get('counterparty_goal', 'unknown')}\n"
        f"Key moments: {_join_text(context.get('key_moments', []), '; ') or 'none'}\n"
        f"Leverage: {_join_text(context.get('leverage_points', []), '; ') or 'none'}\n"
        f"Market research: {market_info}\n"
        + (f"\n{vision_block}" if vision_block else "")
        + f"\nCONVERSATION SO FAR:\n{transcript_text}\n"
        "[/LISTENER_INTEL]\n"
        "INSTRUCTION: Stay silent. Do not respond yet. Wait for the user to speak."
    )


def build_mode_activation_instruction(response_mode: str) -> str:
    if response_mode == "advice":
        return (
            "[SYSTEM: ADVICE MODE ACTIVE]\n"
            "The user is about to ask you a specific question. "
            "Your response MUST directly answer their exact question. "
            "Use the intel above as background context only. "
            "Do not ignore their question or give a generic strategy overview. "
            "Their question is coming now - wait for it."
        )
    return (
        "[SYSTEM: COMMAND MODE ACTIVE]\n"
        "The user is about to ask you a specific question. "
        "Give ONE direct tactical command that answers their exact question. "
        "Use the intel above as context only - do not recite it. "
        "Start with: Ask / Say / Counter / Tell / Push / Walk / Stay / Offer. "
        "Their question is coming now - wait for it."
    )


def build_copilot_priming_text(
    *,
    context: dict,
    market_info: str,
    accumulated_transcript: str,
) -> str:
    return (
        "[LISTENER_INTEL: PRIMING]\n"
        f"Negotiation Type: {context.get('negotiation_type') or 'unknown'}\n"
        f"Item: {context.get('item') or 'unknown'}\n"
        f"Counterparty Goal: {context.get('counterparty_goal') or 'unknown'}\n"
        f"Seller Asking Price: {context.get('seller_asking_price')}\n"
        f"Buyer Offer: {context.get('buyer_offer')}\n"
        f"Counterparty Price: {context.get('counterparty_price')}\n"
        f"User Price: {context.get('user_price')}\n"
        f"User Target Price: {context.get('user_target_price')}\n"
        f"User Walk-Away Price: {context.get('user_walk_away_price')}\n"
        f"{market_info}\n"
        f"Sentiment: {context.get('counterparty_sentiment', 'unknown')}\n"
        f"Key Moments: {_join_text(context.get('key_moments', []), ', ')}\n"
        f"Leverage Points: {_join_text(context.get('leverage_points', []), ', ')}\n"
        f"Full Conversation Transcript:\n{accumulated_transcript}\n"
        "[/LISTENER_INTEL]"
    )


def build_listener_intel_block(
    *,
    context: dict,
    negotiation_type: str,
    user_role: str,
    user_price_label: str,
    user_price_val: object,
    counterparty_price_label: str,
    counterparty_price_val: object,
    market_info: str,
    events_text: str,
    accumulated_transcript: str,
) -> str:
    return (
        "[LISTENER_INTEL]\n"
        f"Item: {context.get('item') or 'unknown'}\n"
        f"Negotiation Type: {negotiation_type}\n"
        f"User Role: {user_role}\n"
        "ROLE RULE: You are advising the USER. If the counterparty says they want to SELL, "
        "the user is BUYING. If the counterparty says they want to BUY, the user is SELLING. "
        "Always respond from the User's perspective.\n"
        f"{counterparty_price_label}: {counterparty_price_val}\n"
        f"{user_price_label}: {user_price_val}\n"
        f"User Target Price: {context.get('user_target_price')}\n"
        f"User Walk-Away Price: {context.get('user_walk_away_price')}\n"
        f"Counterparty Sentiment: {context.get('counterparty_sentiment', 'unknown')}\n"
        f"Counterparty Goal: {context.get('counterparty_goal', 'unknown')}\n"
        f"Key moments: {_join_text(context.get('key_moments', []), '; ') or 'none'}\n"
        f"Leverage points: {_join_text(context.get('leverage_points', []), '; ') or 'none'}\n"
        f"Market research: {market_info}"
        f"{events_text}\n"
        f"\nCONVERSATION (User: = person you advise, Counterparty: = other party):\n{accumulated_transcript}\n"
        "[/LISTENER_INTEL]"
    )


def build_single_context_intel_text(
    *,
    context: dict,
    market_info: str,
    transcript_text: str,
) -> str:
    return (
        "[LISTENER_INTEL]\n"
        f"Negotiation Type: {context.get('negotiation_type') or 'unknown'}\n"
        f"Item: {context.get('item') or 'unknown'}\n"
        f"Counterparty Goal: {context.get('counterparty_goal') or 'unknown'}\n"
        f"Seller Asking Price: {context.get('seller_asking_price') or context.get('seller_price')}\n"
        f"Buyer Offer: {context.get('buyer_offer') or context.get('user_offer')}\n"
        f"Counterparty Price: {context.get('counterparty_price') or context.get('seller_price')}\n"
        f"User Price: {context.get('user_price') or context.get('user_offer')}\n"
        f"User Target Price: {context.get('user_target_price')}\n"
        f"User Walk-Away Price: {context.get('user_walk_away_price')}\n"
        f"{market_info}\n"
        f"Sentiment: {context.get('counterparty_sentiment', context.get('sentiment', 'unknown'))}\n"
        f"Key Moments: {_join_text(context.get('key_moments', []), ', ')}\n"
        f"Leverage Points: {_join_text(context.get('leverage_points', []), ', ')}\n"
        f"Transcript:\n{transcript_text}\n"
        "[/LISTENER_INTEL]"
    )


def build_critical_event_block(*, event_type: str, detail: object, transcript_text: str) -> str:
    return (
        "[LISTENER_INTEL: CRITICAL]\n"
        f"Event: {event_type}\n"
        f"Detail: {detail}\n"
        f"Recent Transcript: {transcript_text}\n"
        "[/LISTENER_INTEL]"
    )


def build_perfect_listener_transcription_prompt(speaker: str) -> str:
    return (
        f"Transcribe the speech in this audio clip from speaker '{speaker}'. "
        "Return ONLY the spoken words verbatim. "
        "No labels, no timestamps, no formatting, no commentary."
    )


def build_response_correction_prompt(violation_messages: Iterable[str]) -> str:
    return (
        f"STOP. Rule violations: {', '.join(violation_messages)}. "
        "Respond again following ALL rules. "
        "Start with an action word. End with a command, not a question."
    )


def _join_text(values: list[object], separator: str) -> str:
    return separator.join(str(value) for value in values if str(value).strip())
