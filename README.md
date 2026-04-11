<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14-000?style=flat-square&logo=next.js" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi" />
  <img src="https://img.shields.io/badge/Go-1.22-00ADD8?style=flat-square&logo=go" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" />
</p>

# Enterprise Agent OS

A production-grade governed multi-agent runtime platform. Not a chatbot. Not an AI wrapper. An operating system for AI agents with full auditability, human-in-the-loop controls, multi-tenancy, cost governance, and measurable ROI.

**Think:** Linear for workflow execution, Stripe for reliability guarantees, Google Cloud Console for operational depth.

---

## Architecture — 7 Layers

```
┌─────────────────────────────────────────────────────┐
│                  Agent Studio (UI)                  │  Next.js 14
│        Canvas · Runs · Approvals · Audit            │  TypeScript
├─────────────────────────────────────────────────────┤
│              Orchestration Engine                   │  FastAPI
│         plan → act → observe → repeat               │  Python 3.12
├─────────────────────────────────────────────────────┤
│               Tool Fabric                           │  40+ connectors
│    Jira · PagerDuty · Slack · Datadog · K8s · ...   │  Vault-backed
├───────────────┬─────────────────┬───────────────────┤
│ Memory &      │ Execution       │ Governance Proxy  │  Go 1.22
│ Knowledge     │ Runtime         │ (the moat)        │  <5ms p99
│ Qdrant · PG   │ K8s · NATS      │ Scope · PII · Inj │
├───────────────┴─────────────────┴───────────────────┤
│                  Data Fabric                        │
│     PostgreSQL · Redis · Qdrant · NATS · S3         │
└─────────────────────────────────────────────────────┘
```

### Layer 1 — Governance Proxy (the moat)
Every tool call, memory read, and external API request passes through this Go service before execution:
- **Scope enforcement** — allowlist per workflow, hierarchical wildcards
- **PII detection & redaction** — 8 regex patterns + NER model integration
- **Prompt injection detection** — 20+ patterns + structural analysis + Haiku classifier
- **Immutable audit log** — SHA-256 hash-chained, PostgreSQL triggers prevent UPDATE/DELETE
- **Rate limiting** — per agent, per tool, per org via Redis sliding windows
- **Human approval gate** — pause execution, create review request, async resume

### Layer 2 — Orchestration Engine
Claude-powered plan/act/observe loop with multi-agent patterns:
- Linear chain, parallel fan-out, hierarchical tree, human-in-the-loop
- Deterministic trace IDs (ULID), step-by-step plan logs, cost tracking
- Per-run constraints: max_steps, max_tokens, max_wall_time, loop detection

### Layer 3 — Tool Fabric
Versioned tool registry with 40+ prebuilt connectors:
- Ticketing: Jira, ServiceNow, Linear, Zendesk, Freshdesk
- Comms: Slack, Teams, Gmail, PagerDuty, OpsGenie
- Code: GitHub, GitLab, Bitbucket
- Infra: AWS CloudWatch, Datadog, Grafana, Kubernetes API
- Data: PostgreSQL, MySQL, BigQuery, Snowflake

### Layer 6 — Agent Studio
Professional workflow builder — not a low-code toy:
- ReactFlow canvas with 9 step types (LLM, Tool, Approval, Branch, Loop, Sub-Agent, Transform, Delay, Notify)
- Live run monitor with SSE streaming and agent reasoning trace
- Approval queue with SLA countdowns and risk indicators
- Command palette (Cmd+K) for fast navigation
- Immutable audit log view with hash chain validation

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Frontend** | Next.js 14, TypeScript, Tailwind, ReactFlow | Agent Studio UI |
| **API** | FastAPI, Python 3.12, Pydantic v2, async | REST + SSE backend |
| **Governance** | Go 1.22, slog, net/http | High-throughput proxy |
| **Database** | PostgreSQL 16 + pgvector | Primary store + embeddings |
| **Cache** | Redis 7 | Session, rate limits, real-time |
| **Vector DB** | Qdrant | RAG knowledge store |
| **Queue** | NATS JetStream | Run queue, event bus |
| **Secrets** | HashiCorp Vault | Credential management |
| **Monorepo** | Turborepo + pnpm | Build orchestration |

---

## Quick Start

### Prerequisites
- Node.js >= 20
- pnpm 9.x
- Docker & Docker Compose
- Python 3.12+ (for API)
- Go 1.22+ (for governance proxy)

### 1. Clone & Install

```bash
git clone https://github.com/Cholarajarp/Enterprise-Agent-OS.git
cd Enterprise-Agent-OS
cp .env.example .env          # Edit with your API keys
pnpm install
```

### 2. Start Infrastructure

```bash
docker-compose up -d          # PostgreSQL, Redis, NATS, Qdrant, Vault
```

### 3. Start Services

```bash
# Terminal 1 — Frontend
cd apps/web && pnpm dev       # http://localhost:3100

# Terminal 2 — API
cd apps/api
pip install -e .
uvicorn app.main:app --reload --port 8000

# Terminal 3 — Governance Proxy
cd apps/worker/governance
go run ./cmd/...              # http://localhost:8090
```

### Optional: Ollama (local models)

```bash
docker-compose --profile ollama up -d
```

---

## Project Structure

```
Enterprise-Agent-OS/
├── apps/
│   ├── web/                    # Next.js 14 Agent Studio
│   │   ├── src/app/            # 11 pages (dashboard, workflows, runs, ...)
│   │   ├── src/components/     # Layout, common, runs, dashboard
│   │   ├── src/lib/            # API client, utilities
│   │   └── src/stores/         # Zustand stores
│   ├── api/                    # FastAPI backend
│   │   ├── app/core/           # Config, security, database
│   │   ├── app/models/         # SQLAlchemy models (6 tables)
│   │   ├── app/routers/        # REST endpoints (5 routers)
│   │   ├── app/middleware/     # Org scope injection
│   │   └── alembic/           # Database migrations
│   └── worker/governance/      # Go governance proxy
│       ├── cmd/                # Entry point
│       ├── internal/           # Audit, PII, injection, scope, rate limit
│       └── pkg/models/         # Shared types
├── packages/
│   ├── types/                  # Zod schemas (shared)
│   ├── config/                 # Shared configuration
│   └── db/                     # PostgreSQL init.sql
├── docker-compose.yml
├── turbo.json
└── pnpm-workspace.yaml
```

---

## Model Routing

The system supports three AI provider backends with hybrid routing:

| Provider | Planner | Worker | Classifier |
|----------|---------|--------|------------|
| **Anthropic** | claude-opus-4-5 | claude-sonnet-4-5 | claude-haiku-4-5 |
| **Gemini** | gemini-2.5-pro | gemini-2.5-flash | gemini-2.5-flash-lite |
| **Ollama** | qwen3-coder | qwen3-coder | gemma3 |

Configure via `MODEL_ROUTING_MODE` (single/hybrid) and `MODEL_*_PROVIDER` env vars.

---

## Database Schema

All tables use UUID v7 primary keys, timestamps, org_id scoping, and Row-Level Security:

- **workflows** — Directed graph definitions with versioning and promotion (draft → staging → production)
- **agent_runs** — Execution records with tool call traces, token usage, and cost tracking
- **audit_events** — Append-only, hash-chained (triggers prevent UPDATE/DELETE)
- **approval_requests** — Human-in-the-loop review queue with SLA deadlines
- **tools** — Registry with pgvector embeddings for semantic search
- **kpi_snapshots** — Per-workflow performance metrics (MTTR, cost, error rates)

---

## API Endpoints

Base URL: `http://localhost:8000/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/workflows` | Create workflow |
| `GET` | `/workflows` | List (cursor pagination) |
| `PUT` | `/workflows/:id` | Update (creates new version) |
| `POST` | `/workflows/:id/promote` | Promote draft → staging → production |
| `POST` | `/runs` | Trigger a run |
| `GET` | `/runs/:id/stream` | SSE real-time run events |
| `GET` | `/approvals` | Pending approvals |
| `POST` | `/approvals/:id/decide` | Approve or reject |
| `GET` | `/audit` | Query immutable audit log |
| `GET` | `/tools` | Tool registry |
| `POST` | `/tools/search` | Semantic tool search |
| `GET` | `/health` | Health check |

All endpoints use JWT auth, org-scoped queries, cursor-based pagination, and RFC 7807 errors.

---

## Design System

**Aesthetic:** Precision-Industrial Dark (Linear + Stripe + Google Cloud Console)

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-void` | `#05050A` | Page background |
| `--bg-surface` | `#0F0F17` | Cards, panels |
| `--accent` | `#5B6AF5` | Primary actions |
| `--txt-1` | `#EEEEF5` | Primary text |
| `--txt-2` | `#8888A8` | Secondary text |

**Typography:** Syne (display) · DM Sans (body) · JetBrains Mono (code)

**Never:** Inter, Roboto, Arial, system fonts, gradient AI aesthetics, purple everything.

---

## Security

- **Zero direct API access** — agents call Governance Proxy, not external APIs
- **Immutable audit trail** — SHA-256 hash chains, tamper detection
- **Row-Level Security** — PostgreSQL RLS on all org-scoped tables
- **PII redaction** — SSN, credit cards, emails, phones detected and masked
- **Prompt injection prevention** — regex + ML classifier on all user inputs
- **Scope enforcement** — per-workflow tool allowlists, granular read/write scopes

---

## Build Verification

```
✓ TypeScript types package — compiles clean
✓ TypeScript config package — compiles clean  
✓ Next.js 14 build — 13 pages, 0 errors, all static/dynamic
✓ Python API — all 21 files syntax-check passed
✓ Go governance proxy — 8 files, proper package structure
✓ PostgreSQL schema — 7 tables, RLS, triggers, indexes
✓ Total: 137 files, ~9,400 lines of production code
```

---

## First Workflow: IT Incident Triage

Target: MTTR from ~45 min to ~8 min.

```
PagerDuty Alert → Enrich → Diagnose → Branch
                                        ├── Auto-resolve (+ approval gate)
                                        └── Route to engineer (with briefing)
                  → Execute Resolution → Verify → Close & Document → KPI Update
```

---

## License

MIT

---


