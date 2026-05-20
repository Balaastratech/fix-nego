# Project Overview: AI Negotiation Copilot

**Project Identity**

AI Negotiation Copilot is a real-time negotiation assistant that listens during a live negotiation, understands the conversation context, and gives the user timely coaching through voice and on-screen guidance.

The product solves a common problem: most people negotiate only occasionally, but the moments are high stakes. Whether the user is buying a car, negotiating salary, discussing a contract, or handling a sales conversation, they often need expert guidance in the moment, not after the conversation is over.

This project turns the browser into a live negotiation command center. It captures audio, tracks who is speaking, extracts prices and leverage points, researches market context when needed, and helps the user decide what to say next.

**Core Capabilities**

- **Live AI coaching during an active conversation**
  - The system connects to Gemini Live and can respond with spoken advice while the negotiation is happening.
  - The user can activate proactive monitoring or directly ask the AI for help during the session.

- **Dual-model intelligence loop**
  - One AI path handles live conversation and voice responses.
  - A separate background listener analyzes the negotiation for prices, sentiment, leverage points, market context, and critical events.
  - This keeps the live advisor informed without forcing the user to repeat details.

- **Speaker-aware transcript and context tracking**
  - The interface separates the user's statements, the counterparty's statements, and the AI advisor's responses.
  - Manual speaker buttons provide the most reliable current speaker labeling path.
  - Optional automatic speaker recognition is implemented through voice enrollment, Google Speech-to-Text diarization, and SpeechBrain verification when enabled.

- **Negotiation state dashboard**
  - The frontend shows detected item, role, counterparty price, user offer, target price, walk-away price, sentiment, leverage points, market research, and recent conversation snippets.
  - This gives the user an immediate view of what the AI believes is happening.

**The Workflow**

1. **User opens the web app**
   - The app establishes a WebSocket connection to the FastAPI backend.
   - The user must accept the privacy consent screen before any audio capture begins.

2. **Optional voice enrollment**
   - If automatic speaker recognition is enabled, the user can enroll their voice by reading a guided passage.
   - The system checks audio quality and builds a session-only voice reference.
   - The user can skip enrollment and use manual speaker selection instead.

3. **User starts a negotiation session**
   - The frontend begins microphone capture through a browser audio worklet.
   - Audio is streamed to the backend as low-latency PCM audio.
   - The backend opens a Gemini Live session and moves the negotiation into an active state.

4. **Conversation is captured and labeled**
   - The user can identify speakers with "Me" and "Counterparty" buttons in manual mode.
   - In automatic mode, the backend can use diarization and speaker verification to classify turns when the required providers are enabled.
   - Transcript updates are sent back to the UI in real time.

5. **Background intelligence is extracted**
   - The ListenerAgent reviews the live conversation and identifies useful negotiation context.
   - It extracts items, prices, offers, sentiment, counterparty goals, key moments, and leverage points.
   - When there is enough detail, it can trigger market research using Gemini with Google Search grounding.

6. **AI coaching is delivered**
   - In Copilot Mode, the AI can be primed with listener intelligence and alert the user at important moments.
   - In Ask AI Mode, the user can hold the AI button and ask a direct question such as "What should I offer?"
   - The system supports a detailed advice mode and a short command mode for live tactical guidance.

7. **Session ends with a summary**
   - When the negotiation ends, the backend cleans up live AI, listener, speaker recognition, and enrollment resources.
   - The UI receives an outcome summary with deal status, prices, savings fields, effectiveness score, and transcript summary fields.

**System Architecture**

**Frontend: Next.js, React, TypeScript, and TailwindCSS**

- Next.js and React provide a browser-based interface that can run on desktop or mobile.
- TypeScript is used because the app depends on many real-time message types and state transitions.
- TailwindCSS supports a fast, responsive dashboard UI.
- The Web Audio API and AudioWorklet pipeline give the app direct control over microphone capture, voice activity, and audio streaming.

**Backend: FastAPI and WebSockets**

- FastAPI is well suited for an async, real-time Python backend.
- WebSockets allow the system to send binary audio frames and structured control messages over the same live connection.
- The backend owns the negotiation state machine so invalid actions, such as sending audio before consent, can be rejected cleanly.

**AI and Speech Stack**

- **Gemini Live** is used for real-time multimodal conversation and spoken responses.
- **Gemini Flash** is used for faster background analysis, structured extraction, and market research prompts.
- **Google Speech-to-Text** supports higher-quality utterance transcription and diarization.
- **SpeechBrain** supports optional speaker verification from enrolled voice samples.
- **Pyannote, WeSpeaker, Conv-TasNet, and related audio tooling** are present as an experimental/roadmap path for more advanced diarization, overlap handling, and speech separation.

**State and Data Storage**

- The current application is intentionally session-oriented.
- Sensitive voice data, embeddings, audio buffers, and speaker state are kept in memory for the active session and cleaned up when the session ends.
- There is no traditional persistent database in the main runtime path today, which fits the privacy requirement for live negotiation audio.

**Deployment**

- The project includes Docker and Google Cloud Run deployment assets for frontend and backend services.
- Cloud Run is a practical fit because the app needs scalable HTTP/WebSocket services without managing servers directly.
- Configuration is environment-driven, which allows AI providers, speech providers, model names, CORS origins, and feature flags to change per deployment.

**Unique Value**

- **It is built for live decisions, not post-call summaries.** The system focuses on in-the-moment coaching while the user is still negotiating.

- **It separates conversation from intelligence extraction.** Gemini Live can focus on natural interaction, while the ListenerAgent continuously builds the negotiation picture in the background.

- **It keeps the user in control.** Manual speaker mode is available when automatic recognition is not reliable enough, and direct AI questions are gated behind an intentional hold-to-talk interaction.

- **It favors privacy by design.** Voice enrollment and negotiation audio are treated as session data rather than long-term stored records.

- **It exposes the AI's understanding.** The dashboard shows detected prices, sentiment, leverage, and market research so the user can see what the system is using to make recommendations.

**Current Status**

**Fully functional in the current codebase**

- Browser-based negotiation dashboard with privacy consent, session controls, transcript panels, AI state indicators, and negotiation context cards.
- FastAPI WebSocket backend with a clear state machine for consent, session start, active negotiation, and session end.
- Gemini Live session creation, audio streaming, AI response playback, response transcription handling, reconnect handling, and keepalive support.
- Background ListenerAgent for extracting negotiation context and pushing updates to both the frontend and Live AI session.
- Manual speaker identification with turn-based audio buffering, which is the most dependable speaker labeling path currently implemented.
- Optional voice enrollment and automatic speaker recognition infrastructure using SpeechBrain and Google STT when configured.
- Market research flow through Gemini Flash with Google Search grounding when the listener has enough specific item context.
- Test coverage across speaker services, enrollment, manual-mode compatibility, frontend integration, WebSocket flow, and PerfectListener audio pipeline experiments.

**Known maturity boundaries**

- Automatic speaker recognition is implemented but should be treated as an advanced configurable mode, not the primary reliability path yet.
- The advanced PerfectListener path for overlap handling and speech separation exists in code and documentation, but remains feature-flagged and experimental.
- The standalone marketplace/forum research service is still a placeholder; the active research path is Gemini with Google Search grounding.
- Session summaries have the structure in place, but richer post-negotiation analytics are still a roadmap item.

**Roadmap**

**Milestone 1: Production-grade speaker and transcript reliability**

- Move from mixed polling and experimental paths toward one reliable turn-based audio pipeline.
- Improve automatic turn boundaries, speaker attribution, overlap handling, and short-utterance capture.
- Make automatic mode trustworthy enough that manual buttons become a fallback instead of the default reliable path.

**Milestone 2: Stronger negotiation intelligence and post-session value**

- Expand market research beyond search-grounded summaries into more structured comparable listings and evidence.
- Add richer post-negotiation reports: tactic breakdown, missed opportunities, stronger counteroffers, savings analysis, and coaching recommendations.
- Add reusable scenarios such as salary negotiation, vehicle purchase, contract renewal, and B2B sales workflows.

**Bottom Line**

AI Negotiation Copilot is already a working real-time negotiation assistant with live AI coaching, background context extraction, speaker-aware transcripts, and a stakeholder-friendly dashboard. Its strongest current path is live coaching with manual speaker control. The next major product push is to harden automatic speaker recognition and convert session output into deeper post-negotiation intelligence.
