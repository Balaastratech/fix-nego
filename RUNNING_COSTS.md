# Running Costs

**Scope:** Monthly operating budget for exactly **100 active users** of the AI Negotiation Copilot, using May 2026 public pricing and a 30-day month.

**Important codebase note:** The current project is deployed on **Google Cloud Run** and is wired primarily to **Gemini Live / Gemini Flash, Google Speech-to-Text, and local SpeechBrain speaker recognition**. DeepSeek, Qwen, Mistral OCR, Supabase, PostHog, and Sentry are included because they were requested for the FinOps scenario, but they are not all current runtime dependencies in the checked codebase.

**Usage assumptions:**

- **Users:** 100 active users.
- **Text/agentic usage:** 20 high-context interactions per user per day.
- **Monthly interactions:** 100 users x 20 interactions x 30 days = **60,000 interactions/month**.
- **Voice usage:** 15 minutes per user per day.
- **Monthly voice minutes:** 100 users x 15 minutes x 30 days = **45,000 minutes/month**.
- **Gemini audio tokenization:** 1 minute of audio = 1,920 tokens.
- **Live API output audio assumption:** the AI speaks back for 20% of user listening time, or **9,000 output-audio minutes/month**.
- **API retry / reconnect overhead:** 10% added to metered AI and speech API usage before the final safety margin.
- **Safety margin:** 15% added to the final subtotal for traffic spikes, retries, quota inefficiency, and pricing variance.

## Summary Table

| Component | Monthly Cost (100 Users) | Cost per User |
|---|---:|---:|
| Core infrastructure: Cloud Run hosting, network, build artifacts, and optional Supabase/Postgres persistence | **$245.00** | **$2.45** |
| LLM and agentic stack: DeepSeek-V3, Qwen, and Mistral OCR | **$92.78** | **$0.93** |
| Real-time multimodal: Gemini Live native audio, Google Speech-to-Text, and SpeechBrain | **$1,186.56** | **$11.87** |
| Operational overhead: Sentry, PostHog, Cloud Logging, backups/admin allowance | **$31.00** | **$0.31** |
| API rate-limit, retry, reconnect, and quota overhead at 10% of metered AI/speech usage | **$127.93** | **$1.28** |
| **Subtotal before safety margin** | **$1,683.28** | **$16.83** |
| **15% safety margin** | **$252.49** | **$2.52** |
| **Estimated monthly total** | **$1,935.77** | **$19.36** |

## Detailed Breakdown

### Core Infrastructure

**Current deployment pattern in this repository**

- Frontend: **Next.js 15 / React 19** container deployed to **Google Cloud Run**.
- Backend: **FastAPI / Uvicorn** container deployed to **Google Cloud Run**.
- Region: current docs and deployment files point to **us-central1**.
- Runtime shape from the deployment guide:
  - Backend: 2 vCPU, 2 GiB memory, minimum 1 warm instance for low-latency WebSocket and audio handling.
  - Frontend: 1 vCPU, 1 GiB memory, Cloud Run container serving the Next.js standalone build.

**Estimated Cloud Run compute**

- Backend warm baseline: approximately **$145/month** after applying the active/idle mix for a 2 vCPU / 2 GiB service.
- Frontend warm baseline: approximately **$65/month** for a 1 vCPU / 1 GiB service.
- Request charges: 60,000 high-context interactions plus WebSocket/control traffic remain well below the free monthly request tier in normal use.
- Build artifacts, Artifact Registry storage, and small outbound network allowance: **$10/month**.

**Hosting estimate:** $145 + $65 + $10 = **$220/month**.

**Database / persistence allowance**

The current codebase keeps negotiation session state in backend memory rather than relying on a production Postgres database. For a stakeholder operating budget, a minimal managed persistence layer should still be reserved for saved sessions, user accounts, audit history, analytics exports, and backups.

- Supabase Pro baseline: **$25/month**.
- At exactly 100 active users, usage fits inside the included Pro limits for monthly active users, storage, and egress under normal assumptions.
- The table reserves the full **$25/month** Supabase Pro baseline as the database/persistence line item.

**Core infrastructure total:** $220 hosting + $25 Supabase Pro = **$245/month**.

### LLM & Agentic Costs

This section models the requested agentic providers even though the current app runtime is Gemini-first.

#### DeepSeek-V3 / DeepSeek Chat

Assumption per high-context interaction:

- 8,000 input tokens.
- 1,000 output tokens.
- 85% of input tokens hit prompt/context cache because repeated system instructions, negotiation schemas, and tool instructions should be cacheable.
- 15% of input tokens are cache misses.

Monthly usage:

- 60,000 interactions x 8,000 input tokens = **480,000,000 input tokens**.
- 60,000 interactions x 1,000 output tokens = **60,000,000 output tokens**.
- Cache-hit input: 480M x 85% = **408M tokens**.
- Cache-miss input: 480M x 15% = **72M tokens**.

Pricing model:

- Cache-hit input: $0.028 per 1M tokens.
- Cache-miss input: $0.28 per 1M tokens.
- Output: $0.42 per 1M tokens.

Math:

- 408M x $0.028 / 1M = **$11.42**.
- 72M x $0.28 / 1M = **$20.16**.
- 60M x $0.42 / 1M = **$25.20**.

**DeepSeek monthly estimate:** **$56.78**.

#### Qwen

Assumption per high-context interaction:

- Qwen is used as a lower-cost routing, classification, summarization, or extraction model.
- 2,000 input tokens per interaction.
- 500 output tokens per interaction.

Monthly usage:

- 60,000 interactions x 2,000 input tokens = **120,000,000 input tokens**.
- 60,000 interactions x 500 output tokens = **30,000,000 output tokens**.

Pricing model:

- Qwen-Turbo international non-thinking input: $0.05 per 1M tokens.
- Qwen-Turbo international non-thinking output: $0.20 per 1M tokens.

Math:

- 120M x $0.05 / 1M = **$6.00**.
- 30M x $0.20 / 1M = **$6.00**.

**Qwen monthly estimate:** **$12.00**.

#### Mistral OCR

Mistral OCR is page-priced in common production planning, not token-priced. Because the current application is a real-time negotiation copilot rather than a document ingestion product, this model assumes documents or screenshots are attached in **20%** of high-context interactions.

Monthly usage:

- 60,000 interactions x 20% document/OCR usage = **12,000 OCR pages/month**.

Pricing model:

- Standard OCR planning price: **$2 per 1,000 pages**.
- Batch OCR can reduce this to roughly **$1 per 1,000 pages**, but live product usage should be budgeted at the standard rate.

Math:

- 12,000 pages / 1,000 x $2 = **$24.00**.

**Mistral OCR monthly estimate:** **$24.00**.

**LLM and agentic total:** $56.78 + $12.00 + $24.00 = **$92.78/month**.

### Real-Time Multimodal

#### Gemini Live API: Flash 2.5 Native Audio

Monthly audio input:

- 45,000 user voice minutes/month.
- Gemini audio tokenization: 1 minute = 1,920 audio tokens.
- 45,000 minutes x 1,920 tokens = **86,400,000 input audio tokens**.

Monthly audio output:

- AI speaks back for 20% of user voice time.
- 45,000 minutes x 20% = **9,000 output audio minutes**.
- 9,000 minutes x 1,920 tokens = **17,280,000 output audio tokens**.

Pricing model:

- Gemini 2.5 Flash Native Audio input: **$3.00 per 1M audio/video tokens**.
- Gemini 2.5 Flash Native Audio output: **$12.00 per 1M audio tokens**.

Math:

- 86.4M input audio tokens x $3.00 / 1M = **$259.20**.
- 17.28M output audio tokens x $12.00 / 1M = **$207.36**.

**Gemini Live monthly estimate:** **$466.56**.

#### Google Speech-to-Text

The backend includes Google Cloud Speech-to-Text dependencies and configuration for the Chirp-family STT path.

Monthly usage:

- 100 users x 15 minutes/day x 30 days = **45,000 minutes/month**.

Pricing model:

- Google Speech-to-Text V2 / Chirp 3 public price: **$0.016 per minute**.

Math:

- 45,000 minutes x $0.016/minute = **$720.00**.

**Google STT monthly estimate:** **$720.00**.

#### SpeechBrain Speaker Recognition

SpeechBrain is an open-source local inference dependency in this codebase. It does not introduce a per-minute external API fee.

Cost treatment:

- API cost: **$0**.
- Compute cost: included in the Cloud Run backend CPU/memory estimate.
- Scaling risk: if speaker recognition is moved to GPU-backed inference or a separate worker, this becomes a new compute line item.

**SpeechBrain monthly estimate:** **$0 external API cost**.

**Real-time multimodal total:** $466.56 + $720.00 + $0 = **$1,186.56/month**.

### Operational Overhead

#### Logging and Observability

**Cloud Logging**

- Expected structured application logs for 100 active users should stay below the 50 GiB/month free allotment if audio payloads are not logged.
- Budgeted amount: **$0/month** for normal operation.
- Risk: accidentally logging transcripts, audio payloads, or verbose per-frame events can quickly push this above the free tier.

**PostHog**

- Product analytics can stay inside the common free allowance if events are kept to session starts, session ends, feature actions, errors, and conversion milestones.
- Estimated events: approximately 300,000 to 700,000 events/month.
- Free tier assumption: **$0/month**.

**Sentry**

- Recommended production monitoring tier: **Team plan at $26/month**.
- Included quota is sufficient for normal error monitoring at 100 active users, assuming no runaway client-side error loop.

**Backups / exports / admin allowance**

- Because the current app does not yet use a production database, backups are mainly a future persistence reserve.
- Budgeted allowance for scheduled exports, backup storage, and small operational scripts: **$5/month**.

**Operational overhead total:** $0 Cloud Logging + $0 PostHog + $26 Sentry + $5 backups = **$31/month**.

### API Rate-Limit and Retry Overhead

This project uses real-time WebSockets, live audio, reconnection logic, and external AI services. A practical budget should account for reconnects, partial failed sessions, retries, warm-up calls, and quota inefficiencies.

Metered AI and speech usage:

- LLM and agentic APIs: **$92.78**.
- Real-time multimodal APIs: **$1,186.56**.
- Metered API subtotal: **$1,279.34**.

Math:

- $1,279.34 x 10% = **$127.93**.

**Rate-limit/retry overhead total:** **$127.93/month**.

## Free Tier Utilization

**Likely covered by free tiers at 100 users**

- **Cloud Run requests:** The app should remain under the free request allotment. Compute is still material because low-latency real-time audio benefits from warm backend capacity.
- **Cloud Logging:** Covered if logs stay below 50 GiB/month and the app avoids logging audio frames or full transcripts at high volume.
- **PostHog:** Covered if product analytics remain below roughly 1M monthly events and session replay is sampled conservatively.
- **Supabase Free:** Technically enough for very early demos if the project only needs small storage and no production backup guarantees. For a real operating budget, Pro is safer.
- **SpeechBrain:** No vendor API fee because it runs locally as open-source inference.

**Not realistically covered by free tiers at 100 users**

- **Gemini Live native audio:** 45,000 user voice minutes/month is production-scale usage and should be budgeted as paid API usage.
- **Google Speech-to-Text:** 45,000 minutes/month is the single largest predictable cost line.
- **DeepSeek/Qwen/Mistral OCR:** These may have small activation credits or trial quotas, but the modeled monthly usage should be treated as paid production traffic.
- **Sentry Team:** The free developer tier is useful for testing, but production monitoring across a team should use a paid plan.

## The Scaling Cliff: 100 Users to 1,000 Users

Most of this budget scales almost linearly with active users because the dominant costs are usage-based AI and speech APIs.

At **1,000 active users**, keeping the same behavior:

- Monthly high-context interactions become **600,000/month**.
- Monthly voice minutes become **450,000/month**.
- Gemini Live cost rises from **$466.56** to about **$4,665.60**.
- Google STT cost rises from **$720.00** to about **$7,200.00**.
- DeepSeek/Qwen/Mistral OCR costs rise from **$92.78** to about **$927.80**.
- API retry overhead rises from **$127.93** to about **$1,279.30**.
- Cloud Run infrastructure will not grow exactly 10x if concurrency is tuned, but the backend will need more warm instances and stronger autoscaling limits. A reasonable 1,000-user infrastructure allowance is **$800 to $1,500/month** before any GPU speaker-recognition worker.

**Projected 1,000-user monthly total with the same safety logic:** roughly **$16,500 to $18,000/month**, or **$16.50 to $18.00 per active user/month**. The per-user cost improves slightly only if Cloud Run and observability overhead are amortized well; it does not collapse because voice minutes and live AI tokens remain variable costs.

## Cost Control Recommendations

- **Avoid double-paying for transcription:** If Gemini Live provides sufficient transcription for a session, reduce or selectively trigger Google STT instead of running full parallel STT for every minute.
- **Use push-to-talk for AI voice replies:** Reducing AI spoken output from 20% to 10% of session time saves about **$103.68/month** at 100 users.
- **Cache DeepSeek prompts aggressively:** Repeated negotiation system prompts and schema instructions should be cache-friendly; lowering cache hits materially increases DeepSeek input cost.
- **Sample analytics and session replay:** Keep PostHog in the free tier by tracking product events, not raw audio or frame-level telemetry.
- **Do not log audio payloads:** Cloud Logging remains cheap only if logs are structured summaries, not media streams.
- **Set provider spend caps:** Use budget alerts and hard caps for Gemini, Google STT, DeepSeek, Qwen, and OCR providers before inviting 1,000-user traffic.

## Pricing Sources Checked

- Google Cloud Run pricing: https://cloud.google.com/run/pricing
- Gemini API pricing, including Gemini 2.5 Flash Native Audio / Live API: https://ai.google.dev/gemini-api/docs/pricing
- Gemini audio tokenization: https://ai.google.dev/gemini-api/docs/audio
- Google Speech-to-Text pricing: https://cloud.google.com/speech-to-text
- DeepSeek API pricing: https://api-docs.deepseek.com/quick_start/pricing
- Alibaba Cloud Model Studio / Qwen pricing: https://www.alibabacloud.com/help/en/model-studio/billing
- Mistral AI pricing page: https://mistral.ai/pricing
- Mistral OCR API docs: https://docs.mistral.ai/api/endpoint/ocr
- Supabase billing and quotas: https://supabase.com/docs/guides/platform/billing-on-supabase
- Supabase storage pricing: https://supabase.com/docs/guides/storage/pricing
- Google Cloud Observability / Logging pricing: https://cloud.google.com/stackdriver/pricing
- Sentry pricing: https://sentry.io/pricing
- PostHog public pricing/free-tier examples: https://posthog.com/posthug
