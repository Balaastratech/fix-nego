@AGENTS.md

# Claude Code additions

For `[Agent: Claude Code]` in this repository:

- Read the imported `AGENTS.md` instructions and the current `HANDOFF.md` before doing work.
- Treat `HANDOFF.md` as shared context/history, not as the relay policy file.
- When updating `HANDOFF.md`, preserve exact command lines, exact key terminal errors, verification outcomes, edited files, and the next concrete command or action the incoming agent should take.
Do not delete writeover existent content you can refer it if mistake poit it out but do not rewrite file contant you can add not rewrite content of file 
- update `HANDOFF.md` after:
  - a completed phase
  - a failed command or blocker
  - a major file edit batch
  - a successful test or build
  - a pause
  - a tool switch
  - low remaining budget near 10 percent
