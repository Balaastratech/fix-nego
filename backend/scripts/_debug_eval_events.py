import json
import sys

path = sys.argv[1]
r = json.load(open(path, "r", encoding="utf-8"))
events = r.get("events", [])
print("Total events:", len(events))

# Show only TRANSCRIPT_UPDATE (speaker=ai) events
ai_transcripts = []
for i, e in enumerate(events):
    etype = e.get("type")
    p = e.get("payload") or {}
    if etype == "TRANSCRIPT_UPDATE" and p.get("speaker") == "ai":
        ai_transcripts.append((i, p))

print("AI transcript count:", len(ai_transcripts))
print()
for i, (idx, p) in enumerate(ai_transcripts):
    print("--- AI TRANSCRIPT", i + 1, " event#", idx, "---")
    print("source:", p.get("source"))
    print("response_mode:", p.get("response_mode"))
    print("text:", repr(p.get("text") or "")[:800])
    print()
