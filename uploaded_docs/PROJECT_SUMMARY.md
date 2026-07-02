# AuditAI — Comprehensive Project Summary
> **Purpose:** Research-grade overview of the entire AuditAI codebase as of June 26, 2026 (branch: `v2-dev-backup`)

---

## 1. Product Overview

**AuditAI** is a multi-tenant, AI-powered call-center auditing SaaS platform. It replaces manual QA review (which typically covers only ~2% of calls) with an automated pipeline that processes every uploaded call recording and produces:

- A **speaker-labeled transcript** with per-segment emotion, gender, and language detection
- A **0–100 quality score** broken across 5 domain-specific pillars
- **Compliance flags** with exact transcript snippets (HIGH/MEDIUM/LOW severity)
- **Coaching insights** for the individual agent
- **Aggregate dashboards** for managers, admins, and platform super-admins

Production URL: `conversa-iq.thevertical.ai`

### Four Verticals (Scoring Engines)

| Vertical | Engine | Key Pillars |
|---|---|---|
| **Sales** | SES — Sales Effectiveness Score | Greeting, Need ID, Product Pitch, Objection Handling, Closing, Compliance |
| **Support** | SQS — Support Quality Score | Issue Resolution, Response Time, Empathy, Process Adherence, FCR, Compliance |
| **Collections** | RES — Recovery Effectiveness Score | Payment Recovery, Negotiation, Empathy, Disclosure Compliance, Commitment, Compliance |
| **Talent** | TES — Talent Evaluation Score | Core Skill Eval, Candidate Engagement, Evaluation Depth, Candidate Experience, Recruitment Compliance |

---

## 2. System Architecture — 6 Services

```
Client Browser
    React 19 + Vite (port 5173 / 4000)
         |
         | HTTP / WebSocket
         v
Node.js API — Express 5 (port 5000)
Auth · CRUD · Upload · Dashboards · Billing · Admin
Prisma ORM → PostgreSQL (port 5433/5432)
         |
         | BullMQ job enqueue
         v
   Redis (port 6380/6379)
         |
         v
Node.js Worker (separate process)
         |
    [Parallel sub-calls]
    |                       |
Soniox/Deepgram/Sarvam    Python Orchestrator — FastAPI (port 8002/8000)
(external ASR)             /preprocess  (enhance + LID)
                           /classify    (emotion + gender)
                           /voice       (voice identity)
         |
         v
LLM Dispatcher (inside Worker)
  ├── Gemini Direct SDK
  ├── OpenRouter (GPT-4o, Claude, Gemma, LLaMA)
  ├── Groq
  ├── NVIDIA NIM
  └── Sarvam LLM

Insights Service — FastAPI gateway + SQL MCP (port 8500)
```

### Service Table

| Service | Language | Framework | Dev Port | Docker Port | Entry |
|---|---|---|---|---|---|
| API | Node.js 20 | Express 5 | 5000 | 5000 | `backend/index.js` |
| Worker | Node.js 20 | BullMQ | — | — | `backend/src/worker/index.js` |
| Frontend | React 19 | Vite 7 | 5173 | 4000 | `frontend/src/App.jsx` |
| Orchestrator | Python 3.9+ | FastAPI/Uvicorn | 8000 | 8002 | `audit_bot_refactor/orchestrator/src/api/app.py` |
| Insights | Python | FastAPI + MCP | — | 8500 | `insights/run.py` |
| PostgreSQL | — | — | 5432 | 5433 | — |
| Redis | — | — | 6379 | 6380 | — |

---

## 3. Call Processing Pipeline (End-to-End)

```
1. AGENT uploads audio (mp3/wav ≤50 MB)
   POST /api/upload → Call row (status: QUEUED) → BullMQ job

2. WORKER picks up job
   ├── PARALLEL:
   │   ├── ASR (Soniox/Deepgram/Sarvam) → word timestamps + diarization
   │   └── Orchestrator /preprocess → audio enhance + language ID
   │
   ├── Orchestrator /classify → per-segment emotion + gender
   │
   ├── Speaker Role Mapping (Node, deterministic heuristic)
   │   "Speaker 1/2" → AGENT/CUSTOMER via greeting-pattern scoring
   │   Fallback: first-in-time = AGENT
   │
   ├── Prosody Extraction (OpenSMILE-style)
   │   F0 mean/sigma, loudness, rate_wpm, jitter, shimmer, HNR
   │   Stored as JSON on each Transcript row
   │
   ├── LLM Evaluation
   │   ├── PII Redaction (phone/email/account/names → placeholders)
   │   ├── Build prompt: transcript + script + compliance rules + vertical rubric
   │   ├── Call LLM (Gemini / OpenRouter / Groq / NVIDIA-NIM / Sarvam-LLM)
   │   ├── Ajv JSON schema validation
   │   ├── Repair-retry loop (AI_MAX_RETRIES=3, then fallback chain)
   │   └── Returns: overall_score, kpi_scores, insights, compliance_violations,
   │               sentiment_journey, key_moments, next_steps, outcome, ai_coaching
   │
   ├── Vertical Scoring Engine (deterministic)
   │   SES/SQS/RES/TES: pillar weights × KPI scores ± compliance penalties
   │   Weight overrides from EvaluationTemplate.criteria.weights (per-customer)
   │
   └── Persist: EvaluationResult + CallScore + ComplianceFlag[] + AgentInsight[]
               + AgentDailyMetrics upsert

3. Socket.io status push → Frontend real-time update
4. Call status → COMPLETED (or FAILED/INVALID)
```

**Typical latency:** 30–90 seconds (ASR 5–30s + orchestrator 3–15s + LLM 5–20s)

---

## 4. Database Schema (~40 tables, PostgreSQL/Prisma)

### Core Call Data
| Table | Key Columns | Purpose |
|---|---|---|
| `calls` | callId, userId, clientId, status, callType (Vertical), durationSeconds, voiceConfidence, pipelineStage | Central call record |
| `transcripts` | speakerLabel, emotion, gender, language, startTime, endTime, text, prosodyFeatures (JSON) | Per-segment transcript with ML signals |
| `evaluation_results` | overallScore, scoreType, fullJsonOutput, modelVersion, tokensIn/Out, costUsd, latencyMs | Raw LLM output + cost tracking |
| `call_scores` | overallScore, pillars (JSON), sentimentScore, conversionStatus | Parsed pillar scores |
| `compliance_flags` | flagType, severity, description, transcription, transcriptTimestamp, ruleId | Per-violation rows |
| `agent_insights` | type (IMPROVEMENT/COMPLIANCE/SUGGESTION/COACHING), title, description, severity | Coaching tips |
| `media_files` | s3Key | Audio file pointer |
| `processing_jobs` | stage, status, startedAt, completedAt, errorMessage | Pipeline stage tracking |

### Aggregation
| Table | Key Columns | Purpose |
|---|---|---|
| `agent_daily_metrics` | agentId, date, vertical, avgScore, languageDistribution, customerAngerRate, agentCalmRate | Dashboard rollup — dashboards read this NOT transcripts |

### Multi-Tenant / Users
| Table | Key Columns | Purpose |
|---|---|---|
| `clients` | name, plan, verticals[], secondsLimit/Used/Credit, mrr/arr | Tenant (organization) |
| `users` | role, clientId, teamId, managerId | All users — no vertical column (removed) |
| `teams` | name, vertical, managerId, templateId | Vertical source of truth for agents |
| `user_sessions` | refreshTokenHash, isRevoked, expiresAt | Revocable refresh tokens |

### Platform Config
| Table | Purpose |
|---|---|
| `feature_flags` | Platform-wide toggles |
| `role_permissions` | RBAC matrix (JSON per role) |
| `ai_model_states` | LLM model enable/disable/fallback |
| `platform_config` | Key-value store |
| `announcements` | Broadcast messages (BANNER/MODAL/TOAST) |
| `audit_logs` | Immutable event log (30+ action types) |

### Billing (Complete Schema, No Stripe Yet)
| Table | Purpose |
|---|---|
| `client_subscriptions` | Tier, billing type (prepaid/postpaid), wallet/minute balances |
| `billing_configurations` | GST/TDS applicability |
| `usage_pricing` | Per-minute + overage rates |
| `usage_limits` | Max users/calls/storage/RPM |
| `otc_charges` + `otc_payments` | One-time charges with partial payment |
| `postpaid_payments` | Invoice payments |
| `prepaid_recharges` | Wallet top-ups |
| `invoices` | Invoice records with GST fields (18% default) |
| `payment_transactions` | Payment log |
| `tax_configurations` | GST (18%) + TDS (2%) per client |
| `usage_tracking` | Per-billing-period records |

### AI & Voice Identity
| Table | Purpose |
|---|---|
| `client_ai_providers` | Per-tenant encrypted AI/ASR keys (AES-256-GCM). Slots: transcriber, primary, script_parser, mentor, insights |
| `ai_configurations` | Per-client AI feature toggles |
| `evaluation_templates` | Custom scoring templates with criteria weights + scripts |
| `compliance_rules` | Per-client rules fed into LLM prompt |
| `knowledge_base_documents/folders` | File/URL/text KB linked to templates |
| `voice_enrollment_samples` | Agent Resemblyzer embeddings |
| `voice_match_attempts` | Per-call voice matching results |
| `voice_match_reviews` | Human corrections of AI speaker ID |

### Key Enums
```
Role:             AGENT | MANAGER | ADMIN | SUPER_ADMIN | KAM
Vertical:         SALES | SUPPORT | COLLECTIONS | TALENT
CallStatus:       READY | QUEUED | PROCESSING | COMPLETED | FAILED | INVALID
SpeakerRole:      AGENT | CUSTOMER
Severity:         LOW | MEDIUM | HIGH
ConversionStatus: CONVERTED | NO_SALE | FOLLOW_UP | AT_RISK
PipelineStage:    LEAD | DISCOVERY | DEMO_PROPOSAL | NEGOTIATION | CLOSED_WON | CLOSED_LOST
InsightType:      IMPROVEMENT | COMPLIANCE | SUGGESTION | COACHING
```

---

## 5. Backend — Node.js API

**Entry:** `backend/index.js` → `backend/src/app.js` | **Type:** CommonJS | **Port:** 5000

### 29 Backend Modules (`backend/src/modules/`)

| Module | Key Files | Responsibility |
|---|---|---|
| `auth` | auth.controller.js, auth.service.js | JWT login/logout, refresh, password reset, 2FA/OTP |
| `upload` | upload.service.js | Multer handling, call creation, BullMQ dispatch |
| `processing` | processing.service.js (59 KB), orchestrator.client.js, transcribers/ | Full pipeline; multi-ASR (Soniox/Deepgram/Sarvam) |
| `ai` | providers/dispatcher.js, gemini.client.js, openrouter.provider.js, model.registry.js | LLM routing, provider SDKs, prompt builders, Ajv validation |
| `scoring` | scoring.service.js | SES/SQS/RES/TES vertical engines |
| `evaluation` | evaluation.service.js | Persists LLM output to DB |
| `dashboard` | dashboard.controller.js | Agent/Manager/Admin/SuperAdmin dashboards |
| `analytics` | — | AgentDailyMetrics rollup + trend charts |
| `compliance` | compliance.service.js | ComplianceRule CRUD + per-call resolver |
| `calls` | call.service.js, call.controller.js | Call CRUD + library queries |
| `billing` | 16 files: billing.service.js, prepaid-recharge.service.js, postpaid-billing-calculation.service.js, gst-calculator.service.js, invoice-generation.service.js, otc.service.js | Full billing: prepaid/postpaid/OTC, GST, invoices |
| `mentor` | mentor.service.js, mentorCoaching.service.js, mentorMoments.service.js | AI coaching chat (separate prompt/model) |
| `admin` | — | Super-admin: clients, users, feature flags, AI models, health, audit logs |
| `knowledge` | — | Knowledge base CRUD |
| `templates` | — | EvaluationTemplate CRUD + LLM script condensation |
| `voice` | voice.service.js (29 KB) | Voice enrollment (Resemblyzer), matching, review |
| `notifications` | — | In-app notification center |
| `activity` | — | Audit log feed |
| `training` | — | Training module + progress |
| `insights` | — | InsightsChat CRUD → Insights service bridge |
| `tickets` | — | Support ticket system |
| `integration` | — | CRM/telephony webhook (Employee-ID → User mapping) |
| `users` | — | User CRUD + team assignment |
| `team` | — | Team CRUD |
| `profile` | — | Profile data |
| `feedback` | — | Manager → agent call comments |
| `export` | — | CSV/Excel export |
| `scoring` | — | Per-vertical scoring engines |
| `processing` | — | Pipeline execution |

### AI Provider Architecture

```
dispatcher.js (single entrypoint: evaluateCall / generateJson / generateChat)
    |
    ├── model.registry.js  (60+ models: Gemini 3.x/2.5, Claude, GPT-4o/4.1,
    |                        Gemma 4, LLaMA 4, Qwen 3, Mistral, NVIDIA NIM, Sarvam)
    |
    ├── gemini.client.js        → Google AI SDK (direct)
    ├── openrouter.provider.js  → OpenRouter REST API
    ├── groq.provider.js        → Groq REST API
    ├── nvidia-nim.provider.js  → NVIDIA NIM REST API
    └── sarvam-llm.provider.js  → Sarvam AI API
```

**Fallback chain:** `AI_FALLBACK_CHAIN` env var — automatic cross-provider fallback on error/timeout.
**Per-tenant keys:** `client_ai_providers` table, AES-256-GCM encrypted, resolved by `keyResolver.js`.

---

## 6. Python Orchestrator (FastAPI)

**Location:** `audit_bot_refactor/orchestrator/` | **Port:** 8000/8002 | **Auth:** Internal bearer token

### ML Stack
| Library | Role |
|---|---|
| PyTorch ≥2.0 + torchaudio | ML backbone + audio I/O |
| SpeechBrain ≥1.1 | Language ID (ECAPA-TDNN), gender classification |
| librosa ≥0.10 | Audio feature extraction |
| Resemblyzer ≥0.1.4 | Speaker voice embeddings (cosine similarity) |
| DeepFilterNet ≥0.5 (optional) | Audio noise reduction |

### Pipeline Stages (`src/pipeline/stages/`)
| File | Route | Purpose |
|---|---|---|
| `ingest.py` | /preprocess | Audio normalization, VAD |
| `enhance.py` | /preprocess | DeepFilterNet noise reduction |
| `lid.py` | /preprocess | Language ID per segment |
| `classify.py` | /classify | Emotion + gender per segment |
| `merge.py` | — | Merge ASR tokens with classifications |
| `voice.py` | /voice | Resemblyzer embeddings + cosine matching |
| `prosody.py` | — | F0, shimmer, jitter, HNR, speaking rate |

**First boot:** ~60–90s (downloads ~800 MB models from HuggingFace). Subsequent boots: <30s.

---

## 7. Insights Service

**Location:** `insights/` | **Port:** 8500
- FastAPI **gateway** + **SQL MCP server** (Model Context Protocol)
- `insights/gateway/` — accepts natural-language queries
- `insights/mcp_servers/sql_mcp/` — translates to SQL over AuditAI DB
- `insights/shared/semantic/auditai.yml` — semantic schema for MCP

Allows Admin/Manager to ask natural-language questions about call data.

---

## 8. Frontend (React 19 + Vite 7)

**Entry:** `frontend/src/App.jsx` | **Type:** ESM | **Dev:** 5173 | **Docker:** 4000

### Core Libraries
| Library | Version | Role |
|---|---|---|
| React | 19.2.0 | UI |
| React Router | 7.13.1 | Routing |
| Zustand | 5.x | Auth state (persisted: `auditai-auth-v2`) |
| TanStack Query | 5.x | Server state |
| Tailwind CSS | 4.x | Styling (custom design tokens) |
| Framer Motion | 12.x | Page transitions + animations |
| Recharts | 3.x | Data charts |
| WaveSurfer.js | 7.x | Audio waveform playback |
| Socket.io Client | 4.x | Real-time call status |
| xlsx + jsPDF | — | Excel + PDF export |
| Playwright | 1.59 | E2E tests |

### Route Architecture
```
/login, /register, /forgot-password  →  publicRoutes.jsx
/agent/*                             →  agentRoutes.jsx
/manager/*                           →  managerRoutes.jsx
/admin/*                             →  adminRoutes.jsx
/super-admin/*                       →  superAdminRoutes.jsx
/kam/*                               →  kamRoutes.jsx
/sales/*, /support/*, /collections/*, /talent/*  →  verticalRoutes.jsx
/no-team                             →  NoTeamPage.jsx
```

### Vertical Context System
`User.vertical` was **removed** from the schema (migration `20260625000000`). Vertical now comes from `User.Team.vertical`.

**Resolution without switch permission:** `team.vertical → /no-team (if no team)`
**Resolution with switch permission:** `localStorage('active_vertical') → team.vertical → client.verticals[0] → 'sales'`

Key files: `useAuthStore.js:resolveActiveVertical`, `verticalRoutes.jsx:VerticalValidator`, `VerticalSwitcher.jsx`

### Frontend Module Structure
```
features/         (shared cross-vertical features)
  admin/          Super Admin + Admin pages
  analytics/      Analytics services
  billing/        Billing pages (AdminBilling, PrepaidBilling)
  calls/          Call detail, transcript viewer, compliance, score badges
  dashboard/      Shared dashboard components

modules/          (per-vertical modules)
  sales/
    agent/        SES dial, my calls, profile
    manager/      Analytics, compliance heatmap, agent comparison
  support/
    manager/      Support analytics
  collections/
    manager/      Collections analytics
  talent/
    admin/        Talent admin analytics
    agent/        Talent dashboard
    manager/      Talent analytics
```

---

## 9. RBAC — 5 Roles

| Role | Scope | Key Capabilities |
|---|---|---|
| SUPER_ADMIN | All tenants | Clients, cross-tenant users, AI models, feature flags, system health, audit export |
| KAM | All tenants | Same data access as SUPER_ADMIN + billing oversight |
| ADMIN | Own tenant | Analytics, compliance, user mgmt, templates, billing |
| MANAGER | Own tenant (team) | Calls library, compliance heatmap, coaching assignment |
| AGENT | Own calls | Upload, transcript+scores, mentor chat, training |

**Auth:** JWT in HttpOnly cookies. Access: 15min (prod)/24h (dev). Refresh: 7 days, DB-stored (`user_sessions`, revocable).

---

## 10. AI Signal Catalog

### From ASR (Soniox/Deepgram/Sarvam)
- Word-level timestamps + confidence
- Speaker diarization (Speaker 1/2 → AGENT/CUSTOMER via greeting heuristic)

### From Orchestrator ML (per segment)
- **Emotion:** calm, angry, sad, happy, neutral, disgust, fearful, surprised (WavLM)
- **Gender:** male/female (SpeechBrain)
- **Language:** ISO code — en, hi, ta, te, etc. (ECAPA-TDNN LID)
- **Prosody:** F0 mean/sigma Hz, loudness sigma, speaking rate WPM, jitter%, shimmer%, HNR dB

### From LLM (per call)
- **KPI Scores (0–100):** cqs, ecs, phs, dis, ros
- **Compliance Flags:** policy name, severity, snippet, timestamp
- **Sentiment Journey:** progression + distribution
- **Key Moments:** timestamped event labels
- **Insights/Coaching:** severity-tagged improvement suggestions
- **Outcome:** CONVERTED / NO_SALE / FOLLOW_UP / AT_RISK
- **Summary:** free-text

### Computed / Aggregated
- **De-escalation Score:** agentCalmRate × 100
- **Customer Anger Rate:** % customer segments tagged "angry"
- **Language Mix:** JSON distribution across segments
- **Percentile Rank:** agent vs. tenant peers
- **Score Trend:** delta vs. prior period

---

## 11. Billing System

### Modes
| Mode | Description |
|---|---|
| Prepaid | Wallet loaded with minutes; deducted per call |
| Postpaid | Monthly invoice based on usage |
| OTC | One-time charges (setup, professional services) |

### Implemented
- GST (18% default, configurable) + TDS (2% default) calculation
- Prepaid wallet recharge + balance tracking
- Postpaid billing calculation (v1 + v2)
- Invoice generation with line items
- Payment recording (all modes)
- ARR/MRR tracking on Client

### Not Yet Implemented (Production Gap)
- Stripe payment processor integration
- Automatic invoice generation trigger
- Webhook event handling
- Hard quota enforcement middleware

---

## 12. CI / CD

### CI (`ci.yml`)
Triggers: PR to `main-dev`/`production`, push to `main-dev`
1. Backend ESLint + `npm run test:unit`
2. Frontend ESLint + `vite build`
3. Docker build smoke (no push)

### Deploy (`deploy.yml`)
Triggers: push to `production`
1. Build 5 Docker images → push to GHCR
2. SSH to VPS → `docker compose pull && docker compose up -d`

### Docker Images
| Image | Dockerfile Target | Build Context |
|---|---|---|
| `api` | `backend/Dockerfile` (api) | `backend/` |
| `worker` | `backend/Dockerfile` (worker) | `backend/` |
| `frontend` | `frontend/Dockerfile` | `frontend/` |
| `orchestrator` | `audit_bot_refactor/orchestrator/Dockerfile` | `audit_bot_refactor/` |
| `insights` | `insights/Dockerfile` | `insights/` |

---

## 13. Known Fragility Patterns

| Pattern | Symptom | Cause |
|---|---|---|
| Unexpected API shape | Blank page, `Cannot read ... of undefined` | Frontend assumes shape; empty data returns different structure |
| 401 on multipart upload | "No token provided" | Access token expired (15 min prod); FormData is one-shot |
| PROCESSING stuck | Call never completes | Worker crashed: orchestrator down / schema mismatch / LLM auth / quota |
| Dashboard zeros | SES=0 despite scored calls | Field name mismatch in aggregation writer vs reader |
| Sidebar layout break | Sidebar covers content | Tailwind token under `width` but missing from `margin`/`padding` |
| Nodemon mid-upload restart | "socket hang up" | Fixed via `nodemon.json` ignoring `uploads/**` |

---

## 14. Architectural Conventions

- **Backend:** CommonJS (`require()`). **Frontend:** ESM (`import`).
- **State:** Zustand for auth, TanStack Query for server state, Socket.io for real-time.
- **PII Redaction:** `backend/src/shared/redact.js` — phone/email/account/name → placeholders (before any LLM call).
- **Error handling:** Worker try/catch per stage + FAILED write; API global crash handlers; Frontend ErrorBoundary.
- **Multi-language:** Soniox/Sarvam handle code-switching (Hinglish, Tamil-English). LID per segment. Conduct rules cover Indian languages.
- **Storage:** Dev = local disk. Prod = Cloudflare R2/S3 (signed URLs already implemented, `STORAGE_MODE` switch ready).

---

## 15. Test Coverage

| Layer | Framework | Scope |
|---|---|---|
| Backend unit | Jest | Fast, no external APIs (`tests/unit/`) |
| Backend integration | Jest + Supertest | Needs real Soniox + LLM keys |
| Backend E2E | Jest | Mocked AI, needs full stack |
| Frontend E2E | Playwright | Browser automation (`frontend/e2e/`) |
| Orchestrator | pytest | Python ML pipeline (`audit_bot_refactor/tests/`) |
| CI | — | Unit + docker build only |

---

## 16. Production Readiness

### ✅ V1 Complete
- Full pipeline (upload → ASR → orchestrator → LLM → scoring → dashboards)
- Multi-tenant isolation (RBAC + clientId scoping everywhere)
- JWT auth + refresh + session revocation
- 5-role portals wired to real data
- LLM scoring with cost + latency tracking
- Per-segment emotion/gender/language, speaker mapping
- Compliance flags + heatmap, coaching assignment
- Voice identity enrollment + matching + human review
- Knowledge base + template system
- Billing schema (prepaid/postpaid/OTC/GST)
- Feature flags, role permissions, AI model management
- System health metrics, audit log
- Support ticket system, goal settings
- Insights AI chat (SQL-backed NL queries)
- Export: CSV, Excel, PDF
- CI/CD: GitHub Actions → GHCR → VPS

### ⚠️ Rough Edges
- Some frontend components crash on unexpected API shape
- Orchestrator first-boot: 60–90s
- Redis rate limiter disabled in dev (in-memory fallback)

### 🚧 V2 / Not Built
- Stripe integration (billing processor)
- Real-time streaming transcription
- Telephony adapters (Twilio/RingCentral)
- Persistent training simulations
- Prompt A/B testing
- Sentry observability
- Secrets manager (currently .env files)
- Cloud object storage (code ready, bucket not configured)

---

## 17. Environment Variables (Key)

| Variable | Default | Purpose |
|---|---|---|
| DATABASE_URL | — | PostgreSQL |
| REDIS_URL | — | BullMQ + rate limiting |
| JWT_SECRET | — | Token signing |
| SONIOX_API_KEY | — | **Required at boot** (placeholder OK for boot-only) |
| GEMINI_API_KEY | — | Primary LLM (Google direct) |
| OPENROUTER_API_KEY | — | Secondary LLM |
| LLM_MODEL | gemini-2.5-flash | Active model key |
| AI_FALLBACK_CHAIN | gemini-2.5-flash-lite,gemma-4-26b-a4b | Ordered fallback |
| AI_MODE | live | `live` or `mock` (dev) |
| AI_PII_REDACTION | true | PII scrubbing before LLM |
| ORCHESTRATOR_URL | http://localhost:8000 | Orchestrator endpoint |
| ORCHESTRATOR_INTERNAL_TOKEN | — | API ↔ Orchestrator shared secret |
| STORAGE_MODE | local | `cloudflare-r2` or `s3` for prod |
| CORS_ORIGIN | http://localhost:5173 | Frontend origin |
| ACCESS_TOKEN_EXPIRES_IN | 24h (dev) / 15m (prod) | JWT TTL |
| EVAL_SCRIPT_MAX_CHARS | 8000 | Max script in LLM prompt |
| EVAL_COMPLIANCE_MAX_RULES | 20 | Max compliance rules per call |
| WORKER_CONCURRENCY | 2 | BullMQ concurrent jobs |
| AI_MAX_RETRIES | 3 | LLM repair-retry attempts |
| SECRETS_KEY | — | AES-256-GCM key for ClientAIProvider |

---

## 18. Developer Quick Reference

```bash
# All 4 app services in one terminal
./start-dev.sh

# Individual services
cd backend && npm run dev            # API (port 5000)
cd backend && npm run worker:dev     # Worker
cd frontend && npm run dev           # Vite (port 5173)
cd audit_bot_refactor/orchestrator
source .venv/bin/activate && uvicorn src.api.app:app --reload

# Seed
cd backend && npm run seed:dev

# Docker
docker compose up -d
docker compose exec api npm run seed:dev
```

### Test Accounts (post-seed)
| Role | Email | Password |
|---|---|---|
| Super Admin | from .env SUPER_ADMIN_EMAIL | from .env |
| Admin | admin@demo.auditai.local | dev-password-123 |
| Manager | manager@demo.auditai.local | dev-password-123 |
| Agent 1 | agent1@demo.auditai.local | dev-password-123 |
| Agent 2 | agent2@demo.auditai.local | dev-password-123 |

---

## 19. Recent Significant Changes (v2-dev-backup, 63 commits)

- **User.vertical removed** — vertical derived entirely from `User.Team.vertical`
- **/no-team page added** — MANAGER/AGENT without teamId get blocking "Not Assigned to a Team" page
- **FollowUps module removed** — ScheduleFollowUpModal, followups.* backend files, followUpsApi.js deleted
- **INVALID CallStatus added** — migration `20260626101500_add_invalid_to_call_status`
- **Calls Library enhanced** — manager + super-admin versions significantly expanded
- **Goal Settings expanded** — GoalSettings.jsx +97 lines with new KPI controls
- **TalentAdminView added** — new component for admin talent dashboard
- **AgentDailyMetrics.vertical added** — enables per-vertical rollup
- **Billing GST fields** — added to Invoice, PostpaidPayment, PrepaidRecharge
- **SecurityPolicy vertical switch flags** — allowManagerVerticalSwitch / allowAgentVerticalSwitch
- **ClientAIProvider table added** — encrypted per-tenant ASR/LLM keys
- **Voice Identity system added** — enrollment, matching, human review workflow
- **227 files changed, 3423 insertions, 3969 deletions** in this branch

---

*Generated: June 26, 2026 | Branch: v2-dev-backup | Workspace: /Users/harishraghavender/Public/Audit_AI*
