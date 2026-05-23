# AI Negotiation Copilot Full System Spec

## Purpose

This document defines the full end-to-end goal of the AI Negotiation Copilot system so another AI agent, engineer, designer, or product builder can understand exactly what is being built.

This product is not a generic meeting assistant.

It is a real-time negotiation copilot whose job is to help one user perform better in a live negotiation by:

- listening to the conversation
- understanding what is happening
- tracking numbers, terms, concessions, and leverage
- giving private, fast, usable negotiation guidance
- helping the user decide what to say next
- producing a clean summary after the session ends

The product must support two operating modes that share one backend intelligence system:

- `in_person_web`
- `virtual_companion_desktop`

## Core Product Goal

The system should act like a private negotiation strategist sitting beside the user during a live conversation.

The user should feel that the system:

- understands the negotiation in real time
- tracks the deal state better than the user can manually
- catches important signals and tradeoffs
- gives short, context-aware advice fast enough to use live
- never silently fails
- never pretends certainty when confidence is low

## Product Scope

### In Scope

- one user
- one counterparty
- live negotiation support
- browser mode for in-person or same-device live conversation
- Windows desktop companion mode for virtual meetings
- live transcript
- live negotiation state extraction
- live private AI advice when explicitly requested
- live research support when useful
- post-session summary
- session persistence for transcript, state, research, and advice timeline

### Out of Scope For This Spec

- multi-party negotiation support
- automatic AI speaking without user request
- raw audio persistence by default
- raw video persistence by default
- browser-mode vision analysis
- post-session email drafting, CRM output, or workflow automation

## Hard Product Rules

These are non-negotiable constraints.

1. AI must never speak automatically.
2. AI may speak only when the user explicitly asks it to speak.
3. The system is single-user and single-counterparty only in v1.
4. Browser mode does not use vision now.
5. Vision or screen analysis is only for the virtual desktop companion mode.
6. Post-session output is summary only.
7. The system must preserve a fallback path when automation quality is weak.
8. The system must show degraded states explicitly instead of hiding failure.

## Product Modes

## Mode 1: `in_person_web`

This is the current browser product shape.

It is for:

- in-room negotiation
- face-to-face negotiation
- user speaking directly into browser mic
- situations where browser is the fastest and simplest interface

Browser mode should use:

- browser microphone capture
- browser UI
- transcript
- negotiation state extraction
- research support
- explicit user-triggered AI advice

Browser mode should not use:

- automatic AI voice interruptions
- screen or vision analysis
- virtual meeting system-audio capture

Current reliable operating path:

- consent
- optional enrollment
- manual speaker buttons
- start session
- start copilot/listener
- switch between `Advice` and `Command`
- press and hold to ask AI

## Mode 2: `virtual_companion_desktop`

This is the Windows desktop sidecar for virtual meetings.

It is for:

- Zoom
- Google Meet
- Microsoft Teams
- browser-based meetings
- native desktop meeting apps

Desktop companion mode should:

- run beside the actual meeting app
- privately advise the user
- capture local microphone
- capture remote meeting audio
- optionally analyze meeting window/screen content when vision is enabled
- persist transcript, research, advice, and session state
- recover from reconnects and source loss gracefully

Desktop companion mode should not:

- join meetings as a bot in v1
- auto-speak without request
- store raw meeting media by default

## Primary User Outcome

The user wants help during a real negotiation, not after the fact.

The user should be able to:

- know the current price and term position
- know what the other side just conceded or refused
- know what leverage exists right now
- know whether to push, hold, trade, or close
- ask the AI for tactical help privately
- get a fast answer they can actually use in conversation

## What The System Must Understand

The system should continuously maintain a live internal model of:

- who is speaking
- what is being negotiated
- what prices were mentioned
- what terms were mentioned
- what concessions happened
- what objections happened
- what the other side seems to want
- what the user's likely target, cap, floor, or walk-away point is
- what risks are emerging
- what leverage is emerging
- whether momentum is improving or worsening

## Intelligence Outputs

The system must convert live conversation into structured intelligence.

### Transcript Output

- live transcript updates
- speaker labels
- source labels where relevant
- confidence-aware behavior
- no false precision when speaker certainty is low

### Negotiation State Output

- item or deal being discussed
- negotiation type
- latest quoted price
- previous quoted prices
- user offer
- counterparty offer
- target price if known
- walk-away if known
- important terms
- unresolved terms
- objections
- concessions
- stage of negotiation
- current momentum

### Strategy Output

- what changed
- what matters most right now
- what the user should say next
- what the user should avoid saying
- what the user should hold firm on
- what can be traded
- whether to push, hold, reframe, trade, or close

### Research Output

- comparable prices
- relevant benchmarks
- supporting evidence
- negotiation-supporting context

Research must help the negotiation, not distract from it.

### Post-Session Summary Output

The system should produce only summary after the meeting ends.

That summary should include:

- what negotiation happened
- key numbers mentioned
- key terms discussed
- concession path
- major turning points
- final position if reached
- whether the user improved the outcome
- short recap of AI advice given during the session

## AI Response Modes

The system supports two response styles.

### `Advice`

Use when the user wants brief reasoning plus recommended action.

Output should be:

- short
- specific
- grounded in the actual live deal state
- immediately usable

### `Command`

Use when the user wants a single tactical line to say next.

Output should be:

- one tight sentence or very short script
- concrete
- context-aware
- safe to use live

## Critical Behavioral Rule For AI Voice

AI must not proactively speak during the meeting.

That means:

- no automatic interruptions
- no auto-played coaching
- no speaking because the system detected a key moment

The system may still:

- detect key moments
- show text alerts
- prepare guidance

But it may only produce spoken audio when the user explicitly asks for it.

## End-To-End Browser Workflow

1. User opens browser app.
2. User grants privacy consent.
3. User optionally completes voice enrollment if enabled.
4. User enters optional negotiation context.
5. User starts the session.
6. Browser captures microphone audio.
7. Backend creates live session state.
8. User identifies speaker manually in the reliable current path.
9. Transcript updates arrive live.
10. Listener extracts numbers, terms, leverage, and momentum.
11. Research triggers when enough structured context exists.
12. UI shows transcript, state, strategy, and research.
13. User chooses `Advice` or `Command`.
14. User explicitly presses and holds to ask AI.
15. AI returns text and optionally spoken response because the user asked.
16. User ends session.
17. System persists transcript, state, research, advice timeline, and summary.

## End-To-End Desktop Companion Workflow

1. User opens Windows desktop companion.
2. User selects `Virtual Meeting Companion`.
3. App checks:
   - backend reachability
   - microphone availability
   - system audio availability
   - capture source availability
   - optional helper availability
4. User selects active meeting window or source.
5. User selects listening output.
6. User selects meeting-route output if private routing is used.
7. App starts local mic capture.
8. App starts remote meeting audio capture.
9. App optionally starts frame or screen analysis when vision is enabled.
10. Backend starts `virtual_companion_desktop` session.
11. Transcript, state, and research update live.
12. User explicitly asks AI for help when needed.
13. AI returns private guidance.
14. Session survives reconnects or source rebinding where possible.
15. User ends session explicitly.
16. System persists session data and produces summary.

## Browser UX Requirements

- clear consent gate
- clear start and end controls
- manual speaker controls
- visible live transcript
- visible current negotiation state
- visible research panel
- visible response mode selector
- clear press-and-hold ask-AI control
- visible AI state indicators
- visible degraded state notices

Browser UX should feel:

- lightweight
- reliable
- fast
- easy to operate mid-conversation

## Desktop Companion UX Requirements

- startup mode selector
- source selector
- mic selector
- system-audio status
- capture-helper status
- listening-output selector
- quality preset selector
- transcript panel
- advice panel
- research panel
- session history panel
- privacy indicator
- reconnect indicator
- degraded-mode banner
- source-loss warning
- speaker-vs-headset quality warning

Desktop UX should feel:

- like a private sidecar
- stable
- operationally clear
- safe to use during a real meeting

## Vision Requirements

Vision is not for browser mode now.

Vision is only for virtual meeting desktop mode.

Desktop vision should be able to:

- inspect the selected meeting window
- read pricing or contract details visible on shared screen
- read listing, product, proposal, or package information
- produce derived observations that help negotiation

Desktop vision should not:

- persist raw continuous video by default
- do people analytics
- become a requirement for the main negotiation flow

Vision is assistive, not foundational.

Audio reliability remains more important than vision.

## Audio And Capture Requirements

### Browser Mode

- mic capture only
- low-latency PCM pipeline
- reliable turn handling
- manual speaker labeling as dependable path

### Desktop Mode

- local mic capture
- remote meeting audio capture
- optional frame capture
- optional helper fallback
- clear source binding
- low-latency normalized PCM

Desktop mode should support:

- headset mode as best quality
- speaker mode as supported but lower-certainty quality

## Latency Targets

These are target product expectations.

- first activity feedback: under `300ms`
- first partial transcript: `0.5s` to `1s` after speech start
- finalized turn transcript: `3s` to `4s` after speech start in the improved path
- listener intelligence injection: `4s` to `5s` after speech start
- total useful pipeline: under `6s`
- explicit ask-AI response start: ideally under `2s` after user finishes asking

Research may complete later, but first tactical guidance must not wait for research completion.

## Reliability Requirements

The system must degrade visibly, not silently.

Required degraded states include:

- `advisor_reconnecting`
- `stt_reconnecting`
- `capture_degraded`
- `source_missing`
- `manual_only`

Failure handling requirements:

- backend disconnect should reconnect and restore session
- renderer crash should allow reopen and restore
- source loss should prompt rebinding
- mic loss should trigger retry or reselect
- system-audio failure should offer fallback path
- vision failure should disable vision only
- speaker-ID weakness should fall back to safer labeling behavior

## Speaker Handling Requirements

### Browser Mode

Reliable current path:

- manual speaker buttons
- user marks `Me` or `Counterparty`

Automatic speaker paths may exist, but browser mode must not rely on them as the only dependable path today.

### Desktop Mode

Desktop mode should be source-aware.

- local mic turns should default to `user`
- remote captured meeting audio should default to `counterparty` when clear
- if uncertain, remote speech should become `remote_unknown`
- the system must not force uncertain turns into false confident labels

## Persistence Requirements

Persist:

- sessions
- transcript turns
- research events
- advisor events
- state snapshots
- source metadata
- quality and degraded-mode transitions
- final summary

Do not persist by default:

- raw audio
- raw continuous video

Persistence must support:

- reconnect restore
- past-session reopening
- transcript review
- strategy review
- research review
- summary review

## Privacy And Security Requirements

- explicit consent before live monitoring
- visible capture indicator at all times
- explicit session start
- explicit session end
- minimal stored data
- no raw media storage by default
- clear labeling of what is being captured
- secure desktop architecture with isolated renderer and validated IPC

## What Success Looks Like

The product succeeds when one user in a real negotiation can use it without breaking conversational flow.

A good session should feel like:

- the system heard the important parts
- the system tracked the real price path
- the system understood the important terms
- the system identified leverage and risk
- the user could privately ask for help
- the AI answered fast enough to matter
- the guidance was specific and usable
- the final summary accurately reflects what happened

## What Failure Looks Like

The product fails if:

- transcript arrives too late to be useful
- advice is generic or not grounded in actual numbers and terms
- the system speaks without user request
- the system silently loses source binding or capture
- the system overclaims speaker certainty
- the system makes the user think it is working when it is actually degraded

## Product Output Contract

Another AI agent or implementation team should build toward this output contract:

- one shared backend intelligence layer
- one browser mode for in-person negotiation
- one Windows desktop companion mode for virtual meetings
- no automatic AI speech
- single user plus single counterparty only
- no browser vision
- desktop-only screen analysis when useful
- summary-only post-session output
- fast, confidence-aware, user-triggered tactical negotiation help

## Final Product Positioning

This system is a live private negotiation copilot.

It is not mainly a transcription app.
It is not mainly a meeting summary app.
It is not mainly a research app.

It is a system that helps the user negotiate better in real time, with two delivery surfaces:

- browser for in-person use
- desktop sidecar for virtual meetings

Both surfaces should feel like one product with one intelligence core.
