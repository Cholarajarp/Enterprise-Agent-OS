-- Enterprise Agent OS — Database Initialization
-- This script runs once on first PostgreSQL container start.
-- All subsequent schema changes go through Alembic migrations.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ─── Enum Types ──────────────────────────────────────────
CREATE TYPE workflow_status AS ENUM ('draft', 'staging', 'production', 'archived');
CREATE TYPE run_status AS ENUM ('queued', 'running', 'awaiting_approval', 'completed', 'failed', 'cancelled', 'timed_out');
CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected', 'expired', 'auto_approved');
CREATE TYPE actor_type AS ENUM ('agent', 'human', 'system');
CREATE TYPE tool_health_status AS ENUM ('healthy', 'degraded', 'down');

-- ─── Organizations ───────────────────────────────────────
CREATE TABLE orgs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    plan            TEXT NOT NULL DEFAULT 'starter',
    monthly_budget  NUMERIC(12, 2) DEFAULT 1000.00,
    settings        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

-- ─── Users ───────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES orgs(id),
    email           TEXT NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'member',
    avatar_url      TEXT,
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(org_id, email)
);
CREATE INDEX idx_users_org_id ON users(org_id);

-- ─── Workflows ───────────────────────────────────────────
CREATE TABLE workflows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES orgs(id),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    status          workflow_status NOT NULL DEFAULT 'draft',
    definition      JSONB NOT NULL DEFAULT '{"steps": [], "edges": []}',
    trigger_config  JSONB,
    tool_scope      TEXT[] DEFAULT '{}',
    budget_config   JSONB,
    kpi_config      JSONB,
    owner_team      TEXT,
    created_by      UUID REFERENCES users(id),
    promoted_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(org_id, slug, version)
);
CREATE INDEX idx_workflows_org_id ON workflows(org_id);
CREATE INDEX idx_workflows_status ON workflows(org_id, status);
CREATE INDEX idx_workflows_owner ON workflows(org_id, owner_team);
CREATE INDEX idx_workflows_slug_version ON workflows(org_id, slug, version DESC);

-- ─── Agent Runs ──────────────────────────────────────────
CREATE TABLE agent_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES orgs(id),
    workflow_id         UUID NOT NULL REFERENCES workflows(id),
    workflow_version    INTEGER NOT NULL DEFAULT 1,
    trigger_type        TEXT NOT NULL,
    trigger_payload     JSONB,
    status              run_status NOT NULL DEFAULT 'queued',
    plan                JSONB,
    steps_completed     INTEGER NOT NULL DEFAULT 0,
    tool_calls          JSONB,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    total_cost_usd      NUMERIC(10, 6) NOT NULL DEFAULT 0,
    wall_time_ms        INTEGER NOT NULL DEFAULT 0,
    error               JSONB,
    output              JSONB,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_runs_org_id ON agent_runs(org_id);
CREATE INDEX idx_runs_workflow ON agent_runs(org_id, workflow_id);
CREATE INDEX idx_runs_status ON agent_runs(org_id, status);
CREATE INDEX idx_runs_created ON agent_runs(org_id, created_at DESC);

-- ─── Audit Events (APPEND ONLY) ─────────────────────────
CREATE TABLE audit_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES orgs(id),
    run_id          UUID REFERENCES agent_runs(id),
    agent_id        TEXT,
    event_type      TEXT NOT NULL,
    actor_type      actor_type NOT NULL,
    actor_id        TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    payload         JSONB NOT NULL,
    decision        TEXT NOT NULL,
    prev_hash       TEXT,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_org_id ON audit_events(org_id);
CREATE INDEX idx_audit_run_id ON audit_events(run_id);
CREATE INDEX idx_audit_event_type ON audit_events(org_id, event_type);
CREATE INDEX idx_audit_created ON audit_events(org_id, created_at DESC);

-- Prevent UPDATE and DELETE on audit_events (append-only enforcement)
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events table is append-only: % operations are forbidden', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_no_update
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

CREATE TRIGGER audit_events_no_delete
    BEFORE DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- ─── Approval Requests ───────────────────────────────────
CREATE TABLE approval_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES orgs(id),
    run_id          UUID NOT NULL REFERENCES agent_runs(id),
    step_id         TEXT NOT NULL,
    workflow_id     UUID NOT NULL REFERENCES workflows(id),
    payload         JSONB NOT NULL,
    context         JSONB,
    required_role   TEXT NOT NULL,
    assigned_to     UUID REFERENCES users(id),
    status          approval_status NOT NULL DEFAULT 'pending',
    decision        JSONB,
    decided_by      UUID REFERENCES users(id),
    sla_deadline    TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at      TIMESTAMPTZ
);
CREATE INDEX idx_approvals_org_id ON approval_requests(org_id);
CREATE INDEX idx_approvals_status ON approval_requests(org_id, status);
CREATE INDEX idx_approvals_run ON approval_requests(run_id);
CREATE INDEX idx_approvals_sla ON approval_requests(org_id, status, sla_deadline);

-- ─── Tools Registry ──────────────────────────────────────
CREATE TABLE tools (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID REFERENCES orgs(id),
    name                TEXT NOT NULL UNIQUE,
    version             TEXT NOT NULL DEFAULT '1.0.0',
    description         TEXT NOT NULL DEFAULT '',
    input_schema        JSONB NOT NULL DEFAULT '{}',
    output_schema       JSONB NOT NULL DEFAULT '{}',
    access_scopes       TEXT[] DEFAULT '{}',
    examples            JSONB,
    embedding           vector(1536),
    requires_approval   BOOLEAN NOT NULL DEFAULT false,
    timeout_ms          INTEGER NOT NULL DEFAULT 30000,
    retry_policy        JSONB,
    cost_per_call       NUMERIC(10, 8) NOT NULL DEFAULT 0,
    health_status       tool_health_status NOT NULL DEFAULT 'healthy',
    last_health_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tools_org_id ON tools(org_id);
CREATE INDEX idx_tools_health ON tools(health_status);

-- ─── KPI Snapshots ───────────────────────────────────────
CREATE TABLE kpi_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES orgs(id),
    workflow_id         UUID NOT NULL REFERENCES workflows(id),
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,
    total_runs          INTEGER NOT NULL DEFAULT 0,
    successful_runs     INTEGER NOT NULL DEFAULT 0,
    failed_runs         INTEGER NOT NULL DEFAULT 0,
    avg_cycle_time_ms   BIGINT NOT NULL DEFAULT 0,
    p50_cycle_time_ms   BIGINT NOT NULL DEFAULT 0,
    p95_cycle_time_ms   BIGINT NOT NULL DEFAULT 0,
    total_cost_usd      NUMERIC(12, 4) NOT NULL DEFAULT 0,
    cost_per_run        NUMERIC(10, 6) NOT NULL DEFAULT 0,
    human_hours_saved   NUMERIC(8, 2) NOT NULL DEFAULT 0,
    error_rate          NUMERIC(5, 4) NOT NULL DEFAULT 0,
    approval_rate       NUMERIC(5, 4) NOT NULL DEFAULT 0,
    sla_compliance      NUMERIC(5, 4) NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_kpi_org_workflow ON kpi_snapshots(org_id, workflow_id);
CREATE INDEX idx_kpi_period ON kpi_snapshots(org_id, period_start DESC);

-- ─── Knowledge Ingestion Jobs ────────────────────────────
CREATE TABLE ingestion_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES orgs(id),
    source_type     TEXT NOT NULL,
    source_config   JSONB NOT NULL,
    domain          TEXT NOT NULL DEFAULT 'general',
    status          TEXT NOT NULL DEFAULT 'pending',
    chunks_created  INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ingestion_org_id ON ingestion_jobs(org_id);

-- ─── Row-Level Security ──────────────────────────────────
-- Enable RLS on all org-scoped tables.
-- Policies enforce that queries can only access rows matching the
-- session's org_id, set via SET app.current_org_id = '<uuid>'.

ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE tools ENABLE ROW LEVEL SECURITY;
ALTER TABLE kpi_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;

-- RLS policies (applied to non-superuser roles)
CREATE POLICY org_isolation_workflows ON workflows
    USING (org_id = current_setting('app.current_org_id')::uuid);

CREATE POLICY org_isolation_runs ON agent_runs
    USING (org_id = current_setting('app.current_org_id')::uuid);

CREATE POLICY org_isolation_audit ON audit_events
    USING (org_id = current_setting('app.current_org_id')::uuid);

CREATE POLICY org_isolation_approvals ON approval_requests
    USING (org_id = current_setting('app.current_org_id')::uuid);

CREATE POLICY org_isolation_tools ON tools
    USING (org_id IS NULL OR org_id = current_setting('app.current_org_id')::uuid);

CREATE POLICY org_isolation_kpi ON kpi_snapshots
    USING (org_id = current_setting('app.current_org_id')::uuid);

CREATE POLICY org_isolation_ingestion ON ingestion_jobs
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- ─── Seed Data (Development Only) ────────────────────────
INSERT INTO orgs (id, name, slug, plan, monthly_budget)
VALUES ('019690a1-0000-7000-8000-000000000001', 'Acme Corporation', 'acme', 'enterprise', 10000.00);

INSERT INTO users (id, org_id, email, name, role)
VALUES ('019690a1-0000-7000-8000-000000000002', '019690a1-0000-7000-8000-000000000001', 'john@acme.com', 'John Doe', 'admin');
