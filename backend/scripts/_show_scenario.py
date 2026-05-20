import json
import sys

sid = sys.argv[1]
d = json.load(open("evals/copilot_scenarios.json", "r", encoding="utf-8"))
for s in d["scenarios"]:
    if s["id"] == sid:
        print("ID:", s["id"])
        print("CONTEXT:", s["context"])
        print("NUMBERS:", s["must_track_numbers"])
        print("TERMS:", s["must_track_terms"])
        print()
        print("TURNS:")
        for i, t in enumerate(s["turns"]):
            print(f'  {i+1}. {t["speaker"]}: {t["text"]}')
        print()
        print("QUERIES:")
        for q in s.get("queries", []):
            print(f'  after_turn={q["after_turn"]} mode={q["mode"]}')
            print(f'    Q: {q["text"]}')
            print(f'    EXP: {q["expected_direction"]}')
        break
