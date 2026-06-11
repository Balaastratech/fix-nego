@AGENTS.md

# Claude Code additions

For `[Agent: Claude Code]` in this repository:

- Before exploring/searching the codebase, check `docs/code_map/00_INDEX.md`. It is a maintained reference map of the entire repo (backend services/API/models/providers/config/prompts, frontend, desktop Electron app, and a doc/test/deploy catalog) with `path:line` references and a "where do I go for X" lookup table. Use it to jump directly to the relevant file(s) instead of re-discovering structure from scratch. If you make a significant structural change (new/renamed/deleted module, new settings flag category, new dead code), update the relevant `docs/code_map/0N_*.md` file so it stays accurate.
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
