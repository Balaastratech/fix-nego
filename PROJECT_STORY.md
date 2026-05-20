# AI Negotiation Copilot - Project Story

## About the Project

### The Inspiration

Have you ever walked into a negotiation feeling unprepared? Maybe you're buying a car and don't know if $25,000 is fair. Or negotiating a salary and wondering if you should counter-offer. That moment of uncertainty inspired this project.

I wanted to build something that levels the playing field—a real-time AI coach that sits in your pocket during negotiations, listening to the conversation, researching market data on the fly, and whispering strategic advice when you need it most.

The **Gemini Live API** made this possible. Its ability to handle real-time audio, process interruptions naturally, and respond with voice made it the perfect foundation for a negotiation copilot that feels like having an expert advisor in the room.

### What I Built

The **AI Negotiation Copilot** is a multimodal live agent that transforms how people negotiate. It combines:

- **Real-time voice interaction** via Gemini Live API for natural conversation
- **Dual-model architecture** where Gemini Flash runs in the background extracting prices, sentiment, and leverage points
- **Proactive coaching** that alerts you to critical moments automatically
- **Market research integration** using Google Search to validate prices and terms
- **Visual context awareness** through image uploads for documents, receipts, or product photos

The system operates in two modes:

1. **Copilot Mode** — The AI monitors passively and only speaks when it detects critical moments (price anchoring, pressure tactics, good opportunities)
2. **Ask AI Mode** — Hold a button to directly ask the AI questions mid-negotiation ("Should I accept this offer?" "What's a fair counteroffer?")

### How I Built It

The architecture follows a **dual-model pattern** that maximizes Gemini's capabilities:

**Frontend (Next.js 15 + React 19)**
- Built with TypeScript for type safety across 15+ WebSocket message types
- Custom AudioWorklet implementation for 16kHz PCM audio capture
- Real-time state management using React hooks with a finite state machine (IDLE → CONSENTED → ACTIVE → ENDING)
- TailwindCSS for responsive UI that works on mobile during real negotiations

**Backend (Python + FastAPI)**
- WebSocket server handling both binary audio frames and JSON control messages
- **Gemini Live API** integration for real-time voice conversation with barge-in support
- **ListenerAgent** using Gemini 2.0 Flash running continuously in background
- Circular audio buffer (30 seconds) for context extraction
- Market research service using Google Search API
- Structured logging with python-json-logger for debugging production issues

**The Dual-Model Innovation**

The breakthrough was realizing one model can't do everything optimally:


- **Gemini Live** handles the conversational interface—responding to user questions, providing coaching, maintaining context
- **Gemini Flash (ListenerAgent)** analyzes the negotiation audio every 10 seconds, extracting structured data:
  - Current and historical prices mentioned
  - Sentiment analysis (confident, hesitant, aggressive)
  - Leverage points and pressure tactics detected
  - Recommended strategies

The ListenerAgent injects its findings as `LISTENER_INTEL` messages into the Live session, so the AI coach always has fresh context without the user needing to repeat information.

**Key Technical Decisions**

1. **Manual speaker identification** — Instead of complex voice fingerprinting, users tap "User" or "Counterparty" buttons. Simple, reliable, works in noisy environments.

2. **WebSocket binary frames** — Audio streams as raw PCM in binary frames (low latency), while control messages use JSON text frames (easy debugging).

3. **Automatic reconnection** — Gemini Live sessions can drop. The system detects disconnections and seamlessly reconnects with a fallback model, preserving conversation history.

4. **Response validation** — AI responses are validated before sending to prevent hallucinations or inappropriate advice during high-stakes negotiations.

### What I Learned

**Multimodal is harder than it looks**


Coordinating audio capture, WebSocket streaming, AI processing, and audio playback requires precise timing. I learned:

- Browser audio APIs require user gestures before playback—solved with a consent flow
- Audio sample rate mismatches cause corrupted output—standardized on 16kHz input, 24kHz output
- WebSocket backpressure can cause audio stuttering—implemented buffering and flow control

**Real-time AI has unique UX challenges**

Users need to know what the AI is doing at all times. I built visual indicators for:
- `AI_CONNECTING` — Establishing Gemini Live session
- `AI_LISTENING` — Processing audio input
- `AI_THINKING` — Analyzing and formulating response
- `AI_SPEAKING` — Playing audio response

Without these, users felt lost during the 2-3 second processing delays.

**Context is everything in negotiations**

Early versions gave generic advice. The breakthrough came from:
- Extracting specific prices and terms from conversation
- Running market research in background (Google Search)
- Analyzing sentiment to detect pressure tactics
- Tracking negotiation history to identify patterns

Now the AI says "That $28,000 offer is 12% above market average for a 2020 Honda Civic with 45k miles" instead of "That seems high."

**Testing real-time systems is complex**


I built comprehensive test suites:
- **Frontend**: Vitest with property-based testing using fast-check for state machine validation
- **Backend**: pytest with mocked Gemini API responses
- **Integration**: Simulated negotiation scenarios with scripted conversations

The hardest bugs were race conditions in WebSocket message ordering—solved with sequence numbers and acknowledgments.

### The Challenges I Faced

**Challenge 1: Audio Codec Hell**

Gemini Live expects 16kHz PCM audio, but browsers capture at 48kHz by default. The Web Audio API's resampling introduced artifacts. Solution: Custom AudioWorklet processor with proper downsampling and anti-aliasing filters.

**Challenge 2: Session Stability**

Gemini Live sessions would randomly drop after 5-10 minutes. Root cause: the API has undocumented timeout behavior. Solution: Implemented heartbeat pings, automatic reconnection with exponential backoff, and seamless session migration to a fallback model.

**Challenge 3: Latency Management**

Initial version had 5-7 second delays between user speech and AI response. Unacceptable for real-time coaching. Optimizations:
- Reduced audio chunk size from 1 second to 250ms
- Implemented streaming responses (AI starts speaking before finishing analysis)
- Moved market research to background thread
- Added response caching for common questions

Got it down to 1.5-2 seconds—feels natural in conversation.

**Challenge 4: Privacy and Ethics**


Recording conversations raises serious privacy concerns. Solutions implemented:
- Explicit consent flow before any audio capture
- Clear visual indicators when recording is active
- No audio storage—everything processed in real-time and discarded
- User controls to pause/stop at any time
- Transparent about AI limitations (not legal advice, can make mistakes)

**Challenge 5: Making AI Advice Actionable**

Early versions gave long explanations. In a live negotiation, you need quick tactical guidance. Solution: Two response modes:
- **Advice Mode**: Detailed explanation with reasoning (for preparation)
- **Command Mode**: One tactical sentence (for live use)

Example Command: "Counter at $23,500 and mention the CarFax report shows previous damage."

### What Makes This Special

**It's actually usable in real negotiations**

Most AI demos are impressive but impractical. This works on your phone during an actual car purchase or salary negotiation. The mobile-responsive UI, low latency, and voice interface make it genuinely useful.

**It demonstrates Gemini Live's unique capabilities**

- Natural interruption handling (barge-in)
- Multimodal input (voice + vision for documents)
- Real-time audio streaming
- Context-aware responses

**It solves a real problem**


Negotiation skills are learned through experience, but most people negotiate rarely (job offers, major purchases). This gives everyone access to expert-level coaching when they need it most.

### Technical Architecture Highlights

The system uses a **finite state machine** for session management:

```
IDLE → (consent granted) → CONSENTED → (start negotiation) → ACTIVE → (end negotiation) → ENDING → IDLE
```

Each state has specific allowed transitions and message types, preventing invalid operations.

**Message Flow Example**

1. User speaks: "I'm looking at a 2020 Honda Civic for $28,000"
2. Frontend captures audio → sends binary WebSocket frames to backend
3. Backend forwards to Gemini Live API
4. Gemini Live transcribes → sends `TRANSCRIPT_UPDATE`
5. ListenerAgent analyzes → extracts price ($28,000) and item (2020 Honda Civic)
6. Market research service queries Google Search → finds average price $24,500
7. Backend sends `STATE_UPDATE` with extracted data
8. Backend sends `RESEARCH_COMPLETE` with market data
9. Gemini Live generates coaching advice
10. Backend sends `AI_RESPONSE` (text) + binary audio frames
11. Frontend plays audio response through speakers

All in under 2 seconds.

### Future Enhancements

If I continue this project:


- **Automatic speaker identification** using voice embeddings
- **Post-negotiation analysis** with detailed breakdown of tactics used
- **Training mode** where users practice negotiations against AI opponents
- **Multi-language support** for international negotiations
- **Integration with CRM systems** for B2B sales negotiations
- **Wearable support** (smartwatch interface for discrete coaching)

### Mathematical Modeling

The system uses several mathematical concepts:

**Sentiment Analysis Score**

The ListenerAgent computes a sentiment score \\( S \in [-1, 1] \\) where:

$$S = \frac{\sum_{i=1}^{n} w_i \cdot s_i}{\sum_{i=1}^{n} w_i}$$

Where:
- \\( s_i \\) is the sentiment of utterance \\( i \\)
- \\( w_i \\) is the recency weight (more recent utterances weighted higher)
- \\( n \\) is the number of utterances in the analysis window

**Price Deviation Metric**

To assess offer fairness:

$$D = \frac{P_{offered} - P_{market}}{P_{market}} \times 100\%$$

Where:
- \\( P_{offered} \\) is the current offer price
- \\( P_{market} \\) is the market average from research

The AI flags offers with \\( |D| > 15\% \\) as requiring immediate attention.

**Confidence Scoring**


Each AI recommendation includes a confidence score \\( C \in [0, 1] \\) based on:

$$C = \alpha \cdot C_{data} + \beta \cdot C_{context} + \gamma \cdot C_{model}$$

Where:
- \\( C_{data} \\) = data quality (market research availability)
- \\( C_{context} \\) = conversation context completeness
- \\( C_{model} \\) = model's self-assessed confidence
- \\( \alpha + \beta + \gamma = 1 \\) (weights sum to 1)

Recommendations with \\( C < 0.6 \\) are flagged as uncertain.

---

## Built With

### Languages & Frameworks

- **Python 3.11+** — Backend API and AI integration
- **TypeScript** — Type-safe frontend development
- **JavaScript** — Web Audio API and browser interactions
- **Next.js 15** — React framework with App Router
- **React 19** — UI component library
- **FastAPI** — High-performance async Python web framework
- **TailwindCSS** — Utility-first CSS framework

### AI & Machine Learning

- **Google Gemini Live API** — Real-time multimodal AI conversation
- **Gemini 2.0 Flash** — Background context extraction and analysis
- **Google GenAI SDK** — Python client for Gemini API integration

### Cloud Services & Infrastructure

- **Google Cloud Run** — Serverless container deployment
- **Google Cloud Platform** — Cloud infrastructure
- **Docker** — Containerization for consistent deployment


### Real-Time Communication

- **WebSockets** — Bidirectional real-time communication
- **Web Audio API** — Browser audio capture and playback
- **AudioWorklet** — Low-latency audio processing
- **Uvicorn** — ASGI server with WebSocket support

### APIs & External Services

- **Google Search API** — Market research and price validation
- **Gemini API** — AI model access

### Development Tools & Libraries

- **Pydantic** — Data validation and settings management
- **Pydantic Settings** — Environment configuration
- **python-dotenv** — Environment variable management
- **Pillow (PIL)** — Image processing for visual context
- **python-json-logger** — Structured logging
- **asgi-correlation-id** — Request tracing
- **Pino** — Fast JSON logger for Node.js
- **pino-pretty** — Human-readable log formatting
- **Lucide React** — Icon library
- **UUID** — Unique identifier generation

### Testing & Quality Assurance

- **Vitest** — Fast unit testing framework for frontend
- **@vitest/ui** — Interactive test UI
- **pytest** — Python testing framework
- **fast-check** — Property-based testing for TypeScript
- **Coverage tools** — Code coverage analysis

### Build & Development Tools

- **Autoprefixer** — CSS vendor prefix automation
- **PostCSS** — CSS transformation
- **ESLint** — JavaScript/TypeScript linting
- **TypeScript Compiler** — Type checking and compilation

---

## Project Statistics

- **Total Lines of Code**: ~8,500
- **Frontend Components**: 15+
- **Backend Services**: 8 core services
- **WebSocket Message Types**: 25+
- **Test Coverage**: 85%+ (frontend), 90%+ (backend)
- **Average Response Latency**: 1.5-2 seconds
- **Supported Audio Formats**: PCM 16kHz (input), PCM 24kHz (output)

---

*Built for the Gemini Live Agent Challenge 2026*
