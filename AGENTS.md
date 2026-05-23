# AGENTS.md

This repository is co-authored by three agents:

- `[Agent: Claude Code]`
- `[Agent: Codex]`
- `[Agent: Antigravity]`

## Relay entrypoint

Read `HANDOFF.md` before planning, editing, running commands, testing, resuming work, or continuing another agent's unfinished task.

`HANDOFF.md` is shared execution context and history. It is not the place for the relay protocol itself.

## What belongs in HANDOFF.md

Write whatever the next agent genuinely needs in order to continue without re-discovering the repo state. That usually includes:

- what the current objective is
- what changed
- what succeeded
- what failed
- exact important command failures or runtime errors
- important decisions and why they were made
- verification status and confidence level
- warm files and logs
- what remains risky or ambiguous
- what should happen next
- enough history from the current and prior relevant sessions that another agent can reconstruct the path accurately

Do not force a rigid schema if a richer narrative is the more accurate handoff.

## Required update triggers
Do not delete writeover existent content you can refer it if mistake poit it out but do not rewrite file contant you can add not rewrite content of file 

update `HANDOFF.md` as a full fresh snapshot whenever any of the following happens:

- a work phase completes
- a blocker or failure occurs
- a pause or stop is requested
- you are about to hand off to another tool or agent
- a successful test or build materially changes confidence
- a major file edit batch lands
- you know or suspect remaining context or rate-limit budget is getting low, especially near 10 percent

## Required handoff writing rules

- Preserve exact attribution tags:
  - `[Agent: Claude Code]`
  - `[Agent: Codex]`
  - `[Agent: Antigravity]`
- Use timestamps on entries.
- Keep full history unless the user explicitly asks to trim it.
- Preserve important context from the current conversation if it affects future work.
- Never rewrite another agent's prior work under your own tag.
- If you retry, supersede, or repair another agent's failed step, record that explicitly.

## Tool-specific entrypoints

### Codex

- This `AGENTS.md` file is the primary repo instruction surface for Codex.
- Codex should record architectural reasoning, cross-file implications, verification outcomes, and unresolved risks in `HANDOFF.md`.

### Claude Code

- Claude Code should read `CLAUDE.md`, which imports this file through `@AGENTS.md`.
- Claude-oriented handoffs should preserve exact commands run, exact key terminal errors, verification outcomes, edited files, and the next command or next action.

### Antigravity

- Antigravity should use `.agents/rules/handoff-relay.md` as the workspace relay rule.
- Antigravity-oriented handoffs should preserve workspace-level mapping context, indexing discoveries, macroscale repo risks, and the next area to inspect when that is the active task.

## Cross-agent safety rule

If the current handoff looks stale, wrong, or incomplete:

- do not silently trust it
- re-check the repo, logs, runtime state, or instruction files
- then rewrite `HANDOFF.md` with corrected context and preserve the fact that a prior handoff was wrong
