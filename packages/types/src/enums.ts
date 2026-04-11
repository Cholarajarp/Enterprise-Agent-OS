import { z } from 'zod';

// ─── Primitives ──────────────────────────────────────────
export const UUIDv7 = z.string().uuid();
export const Timestamp = z.string().datetime();
export const SemVer = z.string().regex(/^\d+\.\d+\.\d+$/);

// ─── Enums ───────────────────────────────────────────────
export const WorkflowStatus = z.enum(['draft', 'staging', 'production', 'archived']);
export type WorkflowStatus = z.infer<typeof WorkflowStatus>;

export const RunStatus = z.enum([
  'queued', 'running', 'awaiting_approval',
  'completed', 'failed', 'cancelled', 'timed_out',
]);
export type RunStatus = z.infer<typeof RunStatus>;

export const ApprovalStatus = z.enum([
  'pending', 'approved', 'rejected', 'expired', 'auto_approved',
]);
export type ApprovalStatus = z.infer<typeof ApprovalStatus>;

export const ActorType = z.enum(['agent', 'human', 'system']);
export type ActorType = z.infer<typeof ActorType>;

export const ToolHealthStatus = z.enum(['healthy', 'degraded', 'down']);
export type ToolHealthStatus = z.infer<typeof ToolHealthStatus>;

export const EventType = z.enum([
  'tool_call', 'approval_requested', 'approval_decided',
  'injection_detected', 'scope_violation', 'pii_redacted',
  'run_started', 'run_completed', 'run_failed',
  'budget_exceeded', 'loop_detected', 'model_refusal',
]);
export type EventType = z.infer<typeof EventType>;

export const DecisionType = z.enum([
  'allowed', 'blocked', 'redacted', 'escalated',
]);
export type DecisionType = z.infer<typeof DecisionType>;

export const TriggerType = z.enum([
  'webhook', 'schedule', 'manual', 'event',
]);
export type TriggerType = z.infer<typeof TriggerType>;

export const StepType = z.enum([
  'llm_call', 'tool_call', 'approval_gate', 'branch',
  'loop', 'sub_agent', 'transform', 'delay', 'notify',
]);
export type StepType = z.infer<typeof StepType>;

// ─── Error Codes ─────────────────────────────────────────
export const ErrorCode = z.enum([
  'tool_error', 'timeout_error', 'model_refusal',
  'approval_timeout', 'budget_exceeded', 'injection_detected',
  'scope_violation', 'loop_detected', 'data_error',
  'auth_error', 'rate_limited', 'internal_error',
]);
export type ErrorCode = z.infer<typeof ErrorCode>;
