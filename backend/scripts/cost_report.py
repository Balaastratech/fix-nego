"""Real per-session cost report from session_traces.

Reads every session_traces/*/trace.jsonl, finds the `session_finalized` metrics
event, and prices it using current Vertex AI / Deepgram public rates (May 2026).

Run from backend/:
    venv\Scripts\python.exe scripts\cost_report.py
"""
from __future__ import annotations
import json, glob, os, sys
from pathlib import Path
from datetime import datetime

# --- Pricing (USD), from official docs May 2026 ---
PRICE = {
    # Gemini Live native audio (per 1M tokens)
    "live_audio_in": 3.00 / 1_000_000,
    "live_audio_out": 12.00 / 1_000_000,
    # Gemini 2.5 Pro (per 1M tokens, <=200k context)
    "pro_in": 1.25 / 1_000_000,
    "pro_out": 10.00 / 1_000_000,
    # Gemini 2.5 Flash (per 1M tokens)
    "flash_text_in": 0.30 / 1_000_000,
    "flash_audio_in": 1.00 / 1_000_000,
    "flash_out": 2.50 / 1_000_000,
    # STT (per minute)
    "deepgram_multi_per_min": 0.0058,
    "google_stt_per_min": 0.016,
}

# --- Per-call token assumptions for things we don't directly meter ---
# (conservative; based on prompt sizes in ai_assets.py / negotiation_engine.py)
ASSUMED = {
    "pro_ask_input_tokens": 4500,    # ask context + history + brief
    "pro_ask_output_tokens": 800,    # tactical answer
    "flash_vision_input_tokens": 1200,  # 2-4 image tiles + prompt (~258 tok/img)
    "flash_vision_output_tokens": 200,
    "flash_research_input_tokens": 1500,
    "flash_research_output_tokens": 600,
}

BASE = Path(r"D:/Balaastra/hackothon/project code/backend/data/logs/session_traces")

def load_trace(trace_path: Path) -> tuple[dict | None, float | None]:
    """Return (final_metrics, duration_seconds) or (None, None)."""
    metrics = None
    first_ts = last_ts = None
    final_ts = None
    for line in trace_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = d.get("timestamp_ms")
        if ts:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
        if d.get("name") == "session_finalized":
            metrics = d["data"].get("metrics", {})
            final_ts = ts
    if metrics is None:
        return None, None
    # Prefer span up to session_finalized
    end = final_ts or last_ts
    dur = (end - first_ts) / 1000.0 if first_ts and end else None
    return metrics, dur


def price_session(m: dict, dur_s: float | None) -> dict:
    # --- Gemini Live ---
    live_in_tok = m.get("gemini_live_input_tokens", 0)
    live_out_tok = m.get("gemini_live_output_tokens", 0)
    live_in_cost = live_in_tok * PRICE["live_audio_in"]
    live_out_cost = live_out_tok * PRICE["live_audio_out"]

    # --- STT ---
    dg_min = m.get("deepgram_stt_minutes", 0.0)
    gs_min = m.get("google_stt_minutes", 0.0)
    dg_cost = dg_min * PRICE["deepgram_multi_per_min"]
    gs_cost = gs_min * PRICE["google_stt_per_min"]

    # --- Gemini Pro asks ---
    asks = m.get("ask_attempts", 0)
    pro_in_cost = asks * ASSUMED["pro_ask_input_tokens"] * PRICE["pro_in"]
    pro_out_cost = asks * ASSUMED["pro_ask_output_tokens"] * PRICE["pro_out"]

    # --- Gemini Flash vision + research ---
    vis = m.get("vision_pro_call_count", 0)
    vis_in_cost = vis * ASSUMED["flash_vision_input_tokens"] * PRICE["flash_text_in"]
    vis_out_cost = vis * ASSUMED["flash_vision_output_tokens"] * PRICE["flash_out"]

    res = m.get("research_calls", 0)
    res_in_cost = res * ASSUMED["flash_research_input_tokens"] * PRICE["flash_text_in"]
    res_out_cost = res * ASSUMED["flash_research_output_tokens"] * PRICE["flash_out"]

    total = (live_in_cost + live_out_cost + dg_cost + gs_cost
             + pro_in_cost + pro_out_cost
             + vis_in_cost + vis_out_cost
             + res_in_cost + res_out_cost)

    per_min = (total / (dur_s / 60.0)) if dur_s and dur_s > 0 else None

    return {
        "duration_s": dur_s,
        "live_in_tok": live_in_tok,
        "live_out_tok": live_out_tok,
        "live_cost": live_in_cost + live_out_cost,
        "dg_min": dg_min,
        "dg_cost": dg_cost,
        "gs_min": gs_min,
        "gs_cost": gs_cost,
        "asks": asks,
        "pro_cost": pro_in_cost + pro_out_cost,
        "vis_calls": vis,
        "vis_cost": vis_in_cost + vis_out_cost,
        "res_calls": res,
        "res_cost": res_in_cost + res_out_cost,
        "total": total,
        "per_min": per_min,
    }


def main():
    rows = []
    for trace in sorted(BASE.glob("*/trace.jsonl")):
        sid = trace.parent.name
        m, dur = load_trace(trace)
        if not m:
            continue
        r = price_session(m, dur)
        r["sid"] = sid
        rows.append(r)

    if not rows:
        print("No session_finalized events found.")
        return

    # Per-session table
    print(f"\n=== Per-session cost ({len(rows)} sessions) ===\n")
    hdr = (f"{'session':10} {'dur_s':>8} {'live_in_tok':>12} {'live_out_tok':>12} "
           f"{'dg_min':>7} {'asks':>5} {'vis':>4} {'total$':>9} {'$/min':>8}")
    print(hdr)
    print("-" * len(hdr))
    tot_total = tot_dur = 0.0
    tot_live_in = tot_live_out = 0
    tot_dg = tot_gs = 0.0
    tot_asks = tot_vis = tot_res = 0
    tot_live_cost = tot_pro_cost = tot_vis_cost = tot_res_cost = tot_dg_cost = tot_gs_cost = 0.0
    for r in rows:
        dm = f"{r['per_min']:.4f}" if r['per_min'] is not None else "  n/a"
        dur = f"{r['duration_s']:.0f}" if r['duration_s'] else "n/a"
        print(f"{r['sid'][:8]:10} {dur:>8} {r['live_in_tok']:>12} {r['live_out_tok']:>12} "
              f"{r['dg_min']:>7.2f} {r['asks']:>5} {r['vis_calls']:>4} "
              f"{r['total']:>9.5f} {dm:>8}")
        tot_total += r['total']
        if r['duration_s']: tot_dur += r['duration_s']
        tot_live_in += r['live_in_tok']; tot_live_out += r['live_out_tok']
        tot_dg += r['dg_min']; tot_gs += r['gs_min']
        tot_asks += r['asks']; tot_vis += r['vis_calls']; tot_res += r['res_calls']
        tot_live_cost += r['live_cost']; tot_pro_cost += r['pro_cost']
        tot_vis_cost += r['vis_cost']; tot_res_cost += r['res_cost']
        tot_dg_cost += r['dg_cost']; tot_gs_cost += r['gs_cost']

    print("\n=== TOTALS across all sessions ===")
    print(f"  total wall duration:       {tot_dur:.1f} s ({tot_dur/60:.2f} min)")
    print(f"  Gemini Live input tokens:  {tot_live_in:,}")
    print(f"  Gemini Live output tokens: {tot_live_out:,}")
    print(f"  Deepgram minutes billed:   {tot_dg:.3f}")
    print(f"  Google STT minutes billed: {tot_gs:.3f}")
    print(f"  Pro asks:                  {tot_asks}")
    print(f"  Vision Pro calls:          {tot_vis}")
    print(f"  Research calls:            {tot_res}")
    print()
    print(f"  Gemini Live cost:   ${tot_live_cost:.5f}")
    print(f"  Deepgram cost:      ${tot_dg_cost:.5f}")
    print(f"  Google STT cost:    ${tot_gs_cost:.5f}")
    print(f"  Pro ask cost (est): ${tot_pro_cost:.5f}")
    print(f"  Vision cost (est):  ${tot_vis_cost:.5f}")
    print(f"  Research cost (est):${tot_res_cost:.5f}")
    print(f"  ------------------------------")
    print(f"  TOTAL across all sessions: ${tot_total:.5f}")
    if tot_dur > 0:
        print(f"  Blended cost / active minute: ${tot_total/(tot_dur/60):.5f}")
        print(f"  Implied cost / hour:          ${tot_total/(tot_dur/3600):.4f}")

    print("\nNote: Pro/Vision/Research are estimated from call counts × assumed token sizes;")
    print("Gemini Live + Deepgram/Google STT are from actual logged metrics.")


if __name__ == "__main__":
    main()
