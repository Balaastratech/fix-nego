"""Quick smoke test that bypasses the full eval/websocket harness.

Calls generate_tactical_advice() with a minimal fake session for one query
from salary_equity_001 and prints the result so we can verify the truncation
fix and see the full Pro answer.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.services.gemini_client import generate_tactical_advice


class _StubListenerAgent:
    def __init__(self, context_dict, transcript_text):
        self.last_context = context_dict
        self.accumulated_transcript = transcript_text


class _StubSession:
    def __init__(self):
        self.session_id = "smoke-test"
        self.context = "Senior product manager offer negotiation"
        self.language = "en-US"
        self.response_language = "en-US"
        self.user_context = {
            "item": "senior product manager offer",
            "target_price": "205000",
            "max_price": None,
        }
        ctx = {
            "item": "senior product manager offer",
            "negotiation_type": "salary",
            "user_target_price": "205000",
            "user_walk_away_price": None,
            "counterparty_price": None,
            "counterparty_goal": "fill role within band",
            "counterparty_sentiment": "neutral",
            "key_moments": [],
            "leverage_points": [],
            "market_data": None,
        }
        transcript = (
            "User: I appreciate the offer.\n"
            "Counterparty: The current offer is 185000 base, 20000 sign-on, 60000 annual equity.\n"
            "User: For this scope, my target is 205000 base.\n"
            "Counterparty: 205 is above band midpoint, that will be difficult.\n"
            "User: If base cannot reach 205, I need total package to close the gap.\n"
            "Counterparty: We might be able to discuss 195 base if the rest stays unchanged.\n"
            "User: 195 helps but I would need 35000 sign-on and 80000 annual equity.\n"
            "Counterparty: Equity has more flexibility than base, sign-on above 25 will require approval.\n"
        )
        self.listener_agent = _StubListenerAgent(ctx, transcript)
        # Eval / session metrics shape
        self.session_metrics = {
            "gemini_live_input_tokens": 0,
            "gemini_live_output_tokens": 0,
        }


async def main():
    print("Model:", settings.effective_advice_model)
    print("Max tokens:", settings.ADVICE_GENERATION_MAX_TOKENS)
    print("Temp:", settings.ADVICE_GENERATION_TEMPERATURE)
    print("=" * 60)

    queries = [
        ("advice", "They may move base to one ninety five but want the rest unchanged. What should I push next?"),
        ("command", "Give me one sentence that asks for equity and sign-on without sounding inflexible."),
    ]

    for mode, q in queries:
        print(f"\n[{mode.upper()}] QUERY: {q}")
        print("-" * 60)
        session = _StubSession()
        text = await generate_tactical_advice(session=session, user_query=q, response_mode=mode)
        if text is None:
            print("(no response — check log)")
        else:
            print("LENGTH:", len(text), "chars")
            print("FULL TEXT:")
            print(text)


if __name__ == "__main__":
    asyncio.run(main())
