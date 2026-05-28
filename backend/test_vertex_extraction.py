"""Quick diagnostic: test cold vs warm Vertex AI calls.
Shows that the first call is slow (TLS + auth) but subsequent calls on the same client are fast.
"""
import asyncio
import time
import os

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = "ai-negotiation-copilot"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"

from google import genai
from google.genai import types as genai_types

PROMPT = 'Return only: {"status": "ok"}'


async def main():
    print("=" * 60)
    print("COLD vs WARM CLIENT TEST")
    print("=" * 60)

    # Single client, reused across calls
    client = genai.Client(
        vertexai=True,
        project="ai-negotiation-copilot",
        location="us-central1",
    )

    for i in range(5):
        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model="google/gemini-2.5-flash",
                    contents=PROMPT,
                    config=genai_types.GenerateContentConfig(temperature=0.0),
                ),
                timeout=30.0,
            )
            elapsed = time.perf_counter() - t0
            label = "COLD" if i == 0 else "WARM"
            print(f"  Call {i+1} [{label}]: {elapsed:.2f}s — {response.text[:50]}")
        except asyncio.TimeoutError:
            print(f"  Call {i+1}: TIMEOUT after {time.perf_counter() - t0:.2f}s")
        except Exception as e:
            print(f"  Call {i+1}: ERROR — {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print("DONE — if warm calls are 2-4s, the fix is client reuse")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
