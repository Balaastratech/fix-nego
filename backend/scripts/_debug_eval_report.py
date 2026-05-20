import json
import sys

path = sys.argv[1]
r = json.load(open(path, "r", encoding="utf-8"))
pairs = r.get("ai_pairs", [])
print("=== REPORT:", path, "===")
print("score:", r.get("score"), "passed:", r.get("passed"))
print("Total pairs:", len(pairs))
print()
for i, p in enumerate(pairs):
    mode = p.get("mode")
    print("--- PAIR", i + 1, "mode=", mode, "---")
    print("QUERY:", (p.get("query") or "")[:300])
    print()
    print("RESPONSE:")
    print(repr((p.get("response") or ""))[:1200])
    print()
    det = p.get("deterministic_score") or {}
    print("DET SCORE:", det.get("score"), "CHECKS:", det.get("checks"))
    j = p.get("judge") or {}
    print("JUDGE AVG:", j.get("average"), "PASSED:", j.get("passed"))
    print("JUDGE SCORES:", j.get("scores"))
    print("RATIONALE:", (j.get("rationale") or "")[:500])
    print("BEST FIX:", (j.get("best_fix") or "")[:300])
    print()
    print("=" * 60)
