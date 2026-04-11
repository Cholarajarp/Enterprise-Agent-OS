<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14-000?style=flat-square&logo=next.js" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi" />
  <img src="https://img.shields.io/badge/Go-1.22-00ADD8?style=flat-square&logo=go" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql" />
  <img src="https://img.shields.io/badge/AI%20Providers-9-FF6F00?style=flat-square" />
  <img src="https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?style=flat-square&logo=github-actions" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" />
</p>

# Enterprise Agent OS

A production-grade governed multi-agent runtime platform. Not a chatbot. Not an AI wrapper. An **operating system for AI agents** with full auditability, human-in-the-loop controls, multi-tenancy, multi-provider model routing, 41 tool connectors, cost governance, and measurable ROI.

**Think:** Linear for workflow execution · Stripe for reliability guarantees · Google Cloud Console for operational depth.

---

## What's Built

| Part | Description | Status |
|------|-------------|--------|
| **0** | Multi-provider AI model router (9 providers, 4 routing modes) 
| **1** | Orchestration engine — plan/act/observe loop, loop detection 
| **2** | Go governance proxy — scope, PII, injection, audit, rate limits 
| **3** | 41 tool connectors with registry and semantic search 
| **4** | Knowledge (Qdrant + BM25) & memory (Redis + PostgreSQL) services 
| **5** | NATS JetStream workers — RunWorker, KPIWorker, HealthWorker 
| **6** | SSE event streaming via Redis pub/sub 
| **7** | Complete API routers — knowledge, KPI, webhooks 
| **8** | Frontend wired to real API — all pages use live data hooks 
| **9** | IT Incident Triage seed workflow — 16 steps, 17 edges 
| **10** | Test suites — pytest, Go race tests, Vitest 
| **11** | GitHub Actions CI/CD — 5-job CI pipeline + deploy workflow 
| **12** | Dockerfiles with HEALTHCHECK, full docker-compose stack 

---

## Architecture — 7 Layers

```
┌──────────────────────────────────────────────────────────────┐
│                     Agent Studio (UI)                        │  Next.js 14
│       Canvas · Runs · Approvals · Audit · KPI Dashboard      │  TypeScript
├──────────────────────────────────────────────────────────────┤
│                  Orchestration Engine                        │  FastAPI
│         plan → act → observe → loop detect → repeat          │  Python 3.12
├──────────────────────────────────────────────────────────────┤
│                     Tool Fabric                              │  41 connectors
│   Jira · PagerDuty · Slack · Datadog · K8s · GitHub · ...    │
├─────────────────┬────────────────────┬───────────────────────┤
│ Memory &        │  Event Streaming   │  Governance Proxy     │  Go 1.22
│ Knowledge       │  (SSE + NATS)      │  (the moat)           │  <5ms p99
│ Qdrant · Redis  │  JetStream workers │  Scope·PII·Inj·Audit  │
├─────────────────┴────────────────────┴───────────────────────┤
│                      Data Fabric                             │
│       PostgreSQL 16 · Redis 7 · Qdrant · NATS JetStream      │
├──────────────────────────────────────────────────────────────┤
│                    Model Router                              │
│  Anthropic · OpenAI · Gemini · Mistral · Cohere · Groq       │
│  Together · Azure OpenAI · Ollama  —  4 routing modes        │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Components

### Governance Proxy (Go 1.22)
Every tool call passes through before execution — <5ms p99 overhead:
- **Scope enforcement** — per-workflow tool allowlists with `service:action` and `service:*` patterns
- **PII detection & redaction** — SSN, emails, phone numbers, credit cards, IPs
- **Prompt injection detection** — regex patterns + structural analysis + confidence scoring
- **Immutable audit log** — SHA-256 hash-chained events, PostgreSQL triggers block UPDATE/DELETE
- **Rate limiting** — per-agent sliding windows via Redis counters
- **Human approval gate** — pause execution, create review request, async resume

### Model Router (Python)
9 providers with unified interface, `LLMResult` cost tracking, and fallback chains:

| Provider | Role: Planner | Role: Worker | Role: Classifier |
|----------|--------------|-------------|-----------------|
| **Anthropic** | claude-opus-4-6 | claude-sonnet-4-6 | claude-haiku-4-5 |
| **OpenAI** | gpt-4o | gpt-4o | gpt-4o-mini |
| **Gemini** | gemini-2.5-pro | gemini-2.5-flash | gemini-2.5-flash-lite |
| **Mistral** | mistral-large | mistral-small | mistral-small |
| **Cohere** | command-r-plus | command-r | command-r |
| **Groq** | llama-3.3-70b | llama-3.3-70b | llama-3.1-8b |
| **Together** | Meta-Llama-3.1-405B | Meta-Llama-3.1-70B | Meta-Llama-3.1-8B |
| **Azure OpenAI** | gpt-4o (deployment) | gpt-4o | gpt-4o-mini |
| **Ollama** | qwen3-coder | qwen3-coder | gemma3 |

Routing modes: `single` · `hybrid` (default) · `cost` · `latency`

### Orchestration Engine
Plan/act/observe loop with full workflow DAG execution:
- 9 step types: `llm` `tool` `approval` `branch` `loop` `sub_agent` `transform` `delay` `notify`
- BFS step traversal with `LoopDetector` (MD5 window + threshold)
- Per-run constraints: `max_steps` · `max_tokens` · `max_wall_time_seconds` · `max_tool_calls`
- SSE `RunEvent` emission at every step boundary

### Tool Connectors (41 total)

| Category | Tools |
|----------|-------|
| **Ticketing** (9) | Jira, ServiceNow, Linear, Zendesk, Freshdesk, GitHub Issues, GitLab Issues, Asana, Monday |
| **Comms** (8) | Slack, Teams, Gmail, Outlook, PagerDuty, OpsGenie, Twilio, Discord |
| **Code** (5) | GitHub, GitLab, Bitbucket, SonarQube, Snyk |
| **Infra** (9) | AWS CloudWatch, Datadog, Grafana, Prometheus, Kubernetes, Terraform, Ansible, Vault, Consul |
| **Data** (4) | PostgreSQL, MySQL, BigQuery, Snowflake |
| **Utility** (5) | HTTP, Python eval, Shell, File, Regex |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js ≥ 20 + pnpm 9
- Python 3.12 (API only, for local dev)
- Go 1.22 (governance proxy only, for local dev)

### 1. Clone & configure

```bash
git clone https://github.com/Cholarajarp/Enterprise-Agent-OS
cd Enterprise-Agent-OS
cp .env.example .env
# Edit .env — minimum: set GEMINI_API_KEY or ANTHROPIC_API_KEY
```

### 2. Start infrastructure

```bash
docker compose up -d postgres redis nats qdrant
```

### 3. Start services (local dev)

```bash
# Terminal 1 — API
cd apps/api && pip install -e . && uvicorn app.main:app --reload --port 8000

# Terminal 2 — Governance Proxy
cd apps/worker/governance && go run ./cmd

# Terminal 3 — Frontend
pnpm install && pnpm --filter web dev      # http://localhost:3000
```

### Or — full Docker stack

```bash
docker compose up -d              # all services
docker compose --profile ollama up -d  # + local Ollama
```

---

## Project Structure

```
Enterprise-Agent-OS/
├── apps/
│   ├── web/                          # Next.js 14 Agent Studio
│   │   ├── src/app/                  # 11 pages (dashboard, workflows, runs …)
│   │   ├── src/components/           # UI components
│   │   ├── src/lib/hooks.ts          # 10 API data hooks
│   │   ├── __tests__/                # Vitest tests
│   │   └── Dockerfile
│   ├── api/                          # FastAPI backend
│   │   ├── app/core/                 # Config (9 providers), database, security
│   │   ├── app/services/             # llm · orchestrator · tools · knowledge
│   │   │                             # memory · workers · events  (7 services)
│   │   ├── app/routers/              # 8 routers
│   │   ├── app/workflows/            # IT triage seed workflow
│   │   ├── tests/                    # pytest suite (5 files)
│   │   └── Dockerfile
│   └── worker/governance/            # Go governance proxy
│       ├── cmd/                      # Entry point + pg/redis stores
│       ├── internal/                 # audit · pii · injection · scope · ratelimit
│       ├── pkg/models/               # Shared types
│       └── Dockerfile
├── packages/
│   ├── types/                        # Shared Zod schemas
│   ├── config/                       # ESLint, TypeScript config
│   └── db/                           # init.sql (10 tables + seed data)
├── .github/workflows/                # ci.yml · deploy.yml
├── docker-compose.yml                # Full production stack
├── docker-compose.dev.yml            # Hot-reload dev overrides
└── .env.example                      # All 40+ env vars documented
```

---

## API Reference

Base URL: `http://localhost:8000/v1` — Interactive docs at `/docs`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness + readiness |
| `POST` | `/workflows` | Create workflow |
| `GET` | `/workflows` | List (cursor pagination) |
| `POST` | `/workflows/:id/promote` | `draft → staging → production` |
| `POST` | `/runs` | Trigger a run |
| `GET` | `/runs/:id/stream` | **SSE** real-time run events |
| `GET` | `/approvals` | Pending approvals |
| `POST` | `/approvals/:id/decide` | Approve or reject |
| `GET` | `/audit` | Immutable audit log |
| `GET` | `/tools` | Tool registry |
| `POST` | `/tools/search` | Semantic tool search |
| `POST` | `/knowledge/ingest` | Ingest docs to vector store |
| `GET` | `/knowledge/search` | Hybrid search (vector + BM25) |
| `GET` | `/kpi/dashboard` | KPI summary |
| `GET` | `/kpi/workflows/:id` | Per-workflow KPI |
| `POST` | `/webhooks/pagerduty` | HMAC-verified webhook |
| `POST` | `/webhooks/jira` | HMAC-verified webhook |
| `POST` | `/webhooks/github` | HMAC-verified webhook |

Auth: JWT RS256 · Org-scoped via RLS · Cursor pagination · RFC 7807 errors

---

## IT Incident Triage Workflow

Seeded automatically. **Target:** MTTR 45 min → 8 min.

```
PagerDuty Alert
      │
      ▼
Acknowledge PD ──► Enrich Metrics (Datadog)
               ──► Enrich Pods (K8s) ──► Enrich Logs
                                               │
                                           Diagnose (LLM)
                                               │
                                         Branch Decision
                                          ┌───┴───┐
                                    auto_resolve  escalate
                                         │           │
                                   Approval Gate  Create Jira
                                         │         Notify Engineer
                                   Execute (K8s)       │
                                         │             │
                                   Verify Recovery ────┘
                                         │
                                   Close + Notify Slack
                                         │
                                     KPI Update
```

Budget: 15 steps · 20 tool calls · 300s wall time · $2.00 · SLA 15 min

---

## CI / CD

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `ci.yml` | push/PR → main | Python tests · Go race tests · Next.js build · Docker build check · Schema validation |
| `deploy.yml` | `v*` tag / manual | GHCR image push (api + governance) · Kubernetes rollout |

---

## Database Schema

10 tables, all with UUID PKs · `org_id` scoping · Row-Level Security:

| Table | Purpose |
|-------|---------|
| `orgs` | Multi-tenant organizations |
| `users` | Role-based access |
| `workflows` | Versioned DAG definitions |
| `agent_runs` | Execution records + cost tracking |
| `audit_events` | **Append-only**, hash-chained |
| `approval_requests` | Human-in-the-loop queue |
| `tools` | Registry with pgvector embeddings |
| `kpi_snapshots` | MTTR, error rate, cost per period |
| `ingestion_jobs` | Knowledge ingestion tracking |
| `memory_store` | Long-term agent memory (TTL + JSONB) |

---

## Design System

**Aesthetic:** Precision-Industrial Dark (Linear + Stripe + GCP Console)

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-void` | `#05050A` | Page background |
| `--bg-surface` | `#0F0F17` | Cards, panels |
| `--accent` | `#5B6AF5` | Primary actions |
| `--txt-1` | `#EEEEF5` | Primary text |
| `--txt-2` | `#8888A8` | Secondary text |

Fonts: **Syne** (display) · **DM Sans** (body) · **JetBrains Mono** (code)

---

## Security

- Zero direct tool API access — all calls route through the Governance Proxy
- Immutable audit trail — SHA-256 hash chains with tamper detection
- Row-Level Security — PostgreSQL RLS on every org-scoped table
- PII redaction — detected and masked before any tool execution
- Prompt injection prevention — regex + structural analysis + confidence threshold
- Scope enforcement — per-workflow `service:action` allowlists

---

## License

MIT
