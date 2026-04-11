import { z } from 'zod';
import { UUIDv7 } from './enums';

// ─── API Request / Response schemas ──────────────────────

// RFC 7807 Problem Details
export const ProblemDetail = z.object({
  type: z.string().url(),
  title: z.string(),
  status: z.number().int(),
  detail: z.string(),
  instance: z.string().optional(),
  error_code: z.string(),
  trace_id: z.string().optional(),
});
export type ProblemDetail = z.infer<typeof ProblemDetail>;

// Cursor-based pagination
export const CursorParams = z.object({
  cursor: z.string().optional(),
  limit: z.number().int().min(1).max(100).default(25),
});
export type CursorParams = z.infer<typeof CursorParams>;

export const CursorResponse = <T extends z.ZodTypeAny>(itemSchema: T) =>
  z.object({
    items: z.array(itemSchema),
    next_cursor: z.string().nullable(),
    has_more: z.boolean(),
  });

// ─── Workflow endpoints ──────────────────────────────────
export const CreateWorkflowRequest = z.object({
  name: z.string().min(1).max(200),
  slug: z.string().regex(/^[a-z0-9-]+$/),
  definition: z.object({
    steps: z.array(z.any()),
    edges: z.array(z.any()),
  }),
  trigger_config: z.object({
    type: z.enum(['webhook', 'schedule', 'manual', 'event']),
    config: z.record(z.unknown()),
  }).optional(),
  tool_scope: z.array(z.string()).default([]),
  budget_config: z.object({
    max_cost_usd: z.number().positive(),
    max_tokens: z.number().int().positive(),
    max_steps: z.number().int().positive().default(25),
    max_wall_time_seconds: z.number().int().positive().default(600),
    max_tool_calls: z.number().int().positive().default(50),
  }).optional(),
  kpi_config: z.array(z.object({
    metric_name: z.string(),
    measurement_fn: z.string(),
  })).optional(),
  owner_team: z.string().optional(),
});
export type CreateWorkflowRequest = z.infer<typeof CreateWorkflowRequest>;

// ─── Run endpoints ───────────────────────────────────────
export const TriggerRunRequest = z.object({
  workflow_id: UUIDv7,
  trigger_type: z.string().default('manual'),
  trigger_payload: z.record(z.unknown()).optional(),
  async: z.boolean().default(true),
});
export type TriggerRunRequest = z.infer<typeof TriggerRunRequest>;

// ─── Approval endpoints ──────────────────────────────────
export const ApprovalDecisionRequest = z.object({
  verdict: z.enum(['approved', 'rejected']),
  reason: z.string().min(1),
  modified_params: z.record(z.unknown()).optional(),
});
export type ApprovalDecisionRequest = z.infer<typeof ApprovalDecisionRequest>;

// ─── Tool endpoints ──────────────────────────────────────
export const RegisterToolRequest = z.object({
  name: z.string().min(1),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  description: z.string(),
  input_schema: z.record(z.unknown()),
  output_schema: z.record(z.unknown()),
  access_scopes: z.array(z.string()),
  requires_approval: z.boolean().default(false),
  timeout_ms: z.number().int().positive().default(30000),
  cost_per_call: z.number().default(0),
});
export type RegisterToolRequest = z.infer<typeof RegisterToolRequest>;

export const ToolSearchRequest = z.object({
  query: z.string().min(1),
  limit: z.number().int().min(1).max(50).default(10),
});
export type ToolSearchRequest = z.infer<typeof ToolSearchRequest>;

// ─── Knowledge endpoints ─────────────────────────────────
export const IngestRequest = z.object({
  source_type: z.enum(['confluence', 'sharepoint', 'notion', 'upload', 'url']),
  source_config: z.record(z.unknown()),
  domain: z.string().default('general'),
});
export type IngestRequest = z.infer<typeof IngestRequest>;

// ─── SSE Event Types ─────────────────────────────────────
export const SSEEventType = z.enum([
  'run.started', 'step.planned', 'step.started',
  'tool.called', 'tool.returned',
  'approval.requested', 'approval.decided',
  'llm.reasoning', 'run.completed', 'run.failed',
]);
export type SSEEventType = z.infer<typeof SSEEventType>;

export const SSEEvent = z.object({
  event: SSEEventType,
  data: z.record(z.unknown()),
  timestamp: z.string().datetime(),
  run_id: UUIDv7,
});
export type SSEEvent = z.infer<typeof SSEEvent>;
