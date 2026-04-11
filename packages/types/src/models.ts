import { z } from 'zod';
import {
  UUIDv7, Timestamp, SemVer,
  WorkflowStatus, RunStatus, ApprovalStatus,
  ActorType, ToolHealthStatus, EventType,
  DecisionType, TriggerType, StepType,
} from './enums';

// ─── Budget Config ───────────────────────────────────────
export const BudgetConfig = z.object({
  max_cost_usd: z.number().positive(),
  max_tokens: z.number().int().positive(),
  max_steps: z.number().int().positive().default(25),
  max_wall_time_seconds: z.number().int().positive().default(600),
  max_tool_calls: z.number().int().positive().default(50),
});
export type BudgetConfig = z.infer<typeof BudgetConfig>;

// ─── KPI Config ──────────────────────────────────────────
export const KPIMetric = z.object({
  metric_name: z.string(),
  measurement_fn: z.string(),
});
export type KPIMetric = z.infer<typeof KPIMetric>;

// ─── Workflow Step ───────────────────────────────────────
export const WorkflowStep = z.object({
  id: z.string(),
  type: StepType,
  name: z.string(),
  config: z.record(z.unknown()),
  next: z.union([z.string(), z.record(z.string())]).optional(),
  requires_approval: z.boolean().default(false),
  timeout_ms: z.number().int().positive().optional(),
});
export type WorkflowStep = z.infer<typeof WorkflowStep>;

// ─── Workflow ────────────────────────────────────────────
export const Workflow = z.object({
  id: UUIDv7,
  org_id: UUIDv7,
  name: z.string().min(1).max(200),
  slug: z.string().regex(/^[a-z0-9-]+$/),
  version: z.number().int().positive().default(1),
  status: WorkflowStatus,
  definition: z.object({
    steps: z.array(WorkflowStep),
    edges: z.array(z.object({
      from: z.string(),
      to: z.string(),
      condition: z.string().optional(),
    })),
  }),
  trigger_config: z.object({
    type: TriggerType,
    config: z.record(z.unknown()),
  }).optional(),
  tool_scope: z.array(z.string()),
  budget_config: BudgetConfig.optional(),
  kpi_config: z.array(KPIMetric).optional(),
  owner_team: z.string().optional(),
  created_by: UUIDv7,
  promoted_at: Timestamp.nullable().optional(),
  created_at: Timestamp,
  updated_at: Timestamp,
});
export type Workflow = z.infer<typeof Workflow>;

// ─── Tool Call Record ────────────────────────────────────
export const ToolCallRecord = z.object({
  tool: z.string(),
  params: z.record(z.unknown()),
  result: z.unknown(),
  latency_ms: z.number().int(),
  status: z.enum(['success', 'error', 'blocked']),
});
export type ToolCallRecord = z.infer<typeof ToolCallRecord>;

// ─── Agent Run ───────────────────────────────────────────
export const AgentRun = z.object({
  id: UUIDv7,
  org_id: UUIDv7,
  workflow_id: UUIDv7,
  workflow_version: z.number().int().positive(),
  trigger_type: z.string(),
  trigger_payload: z.record(z.unknown()).optional(),
  status: RunStatus,
  plan: z.array(z.record(z.unknown())).optional(),
  steps_completed: z.number().int().default(0),
  tool_calls: z.array(ToolCallRecord).optional(),
  input_tokens: z.number().int().default(0),
  output_tokens: z.number().int().default(0),
  total_cost_usd: z.number().default(0),
  wall_time_ms: z.number().int().default(0),
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.unknown()).optional(),
  }).nullable().optional(),
  output: z.record(z.unknown()).nullable().optional(),
  started_at: Timestamp.nullable().optional(),
  completed_at: Timestamp.nullable().optional(),
  created_at: Timestamp,
});
export type AgentRun = z.infer<typeof AgentRun>;

// ─── Audit Event (immutable) ─────────────────────────────
export const AuditEvent = z.object({
  id: UUIDv7,
  org_id: UUIDv7,
  run_id: UUIDv7.nullable(),
  agent_id: z.string().nullable(),
  event_type: EventType,
  actor_type: ActorType,
  actor_id: z.string(),
  payload_hash: z.string(),
  payload: z.record(z.unknown()),
  decision: DecisionType,
  latency_ms: z.number().int(),
  created_at: Timestamp,
});
export type AuditEvent = z.infer<typeof AuditEvent>;

// ─── Approval Request ────────────────────────────────────
export const ApprovalRequest = z.object({
  id: UUIDv7,
  org_id: UUIDv7,
  run_id: UUIDv7,
  step_id: z.string(),
  workflow_id: UUIDv7,
  payload: z.record(z.unknown()),
  context: z.record(z.unknown()).optional(),
  required_role: z.string(),
  assigned_to: UUIDv7.nullable().optional(),
  status: ApprovalStatus,
  decision: z.object({
    verdict: z.enum(['approved', 'rejected']),
    reason: z.string(),
    modified_params: z.record(z.unknown()).optional(),
  }).nullable().optional(),
  decided_by: UUIDv7.nullable().optional(),
  sla_deadline: Timestamp,
  created_at: Timestamp,
  decided_at: Timestamp.nullable().optional(),
});
export type ApprovalRequest = z.infer<typeof ApprovalRequest>;

// ─── Tool ────────────────────────────────────────────────
export const Tool = z.object({
  id: UUIDv7,
  org_id: UUIDv7.nullable().optional(),
  name: z.string().min(1),
  version: SemVer,
  description: z.string(),
  input_schema: z.record(z.unknown()),
  output_schema: z.record(z.unknown()),
  access_scopes: z.array(z.string()),
  examples: z.array(z.object({
    input: z.record(z.unknown()),
    output: z.record(z.unknown()),
  })).optional(),
  requires_approval: z.boolean().default(false),
  timeout_ms: z.number().int().positive().default(30000),
  retry_policy: z.object({
    max_retries: z.number().int().default(3),
    backoff_ms: z.number().int().default(1000),
  }).optional(),
  cost_per_call: z.number().default(0),
  health_status: ToolHealthStatus.default('healthy'),
  last_health_at: Timestamp.nullable().optional(),
  created_at: Timestamp,
});
export type Tool = z.infer<typeof Tool>;

// ─── KPI Snapshot ────────────────────────────────────────
export const KPISnapshot = z.object({
  id: UUIDv7,
  org_id: UUIDv7,
  workflow_id: UUIDv7,
  period_start: Timestamp,
  period_end: Timestamp,
  total_runs: z.number().int(),
  successful_runs: z.number().int(),
  failed_runs: z.number().int(),
  avg_cycle_time_ms: z.number().int(),
  p50_cycle_time_ms: z.number().int(),
  p95_cycle_time_ms: z.number().int(),
  total_cost_usd: z.number(),
  cost_per_run: z.number(),
  human_hours_saved: z.number(),
  error_rate: z.number(),
  approval_rate: z.number(),
  sla_compliance: z.number(),
  created_at: Timestamp,
});
export type KPISnapshot = z.infer<typeof KPISnapshot>;
