'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api, APIError } from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Generic fetch-hook state
// ---------------------------------------------------------------------------
interface HookState<T> {
  data: T | null;
  loading: boolean;
  error: APIError | Error | null;
}

/**
 * Lightweight data-fetching hook (no TanStack Query dependency).
 * Returns { data, loading, error, refetch }.
 */
function useAPI<T>(
  fetcher: (() => Promise<T>) | null,
  deps: unknown[] = [],
  fallback: T | null = null,
) {
  const [state, setState] = useState<HookState<T>>({
    data: fallback,
    loading: !!fetcher,
    error: null,
  });

  // Keep latest fetcher in a ref so we can refetch without re-mounting.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(() => {
    const fn = fetcherRef.current;
    if (!fn) return;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    fn()
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((err: unknown) => {
        const error = err instanceof Error ? err : new Error(String(err));
        setState((prev) => ({ data: prev.data ?? fallback, loading: false, error }));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refetch]);

  return { ...state, refetch };
}

// ---------------------------------------------------------------------------
// Response types — mirrors the FastAPI schemas from the backend
// ---------------------------------------------------------------------------

export interface Workflow {
  id: string;
  name: string;
  status: 'draft' | 'staging' | 'production';
  description: string;
  totalRuns: number;
  total_runs?: number;
  avgCost: number;
  avg_cost?: number;
  lastRunAt: string;
  last_run_at?: string;
  stepsCount: number;
  steps_count?: number;
  [key: string]: unknown;
}

export interface Run {
  id: string;
  workflow: string;
  workflow_name?: string;
  status: string;
  trigger: string;
  steps: string;
  cost: number;
  duration: number;
  started: string;
  started_at?: string;
  [key: string]: unknown;
}

export interface ApprovalItem {
  id: string;
  runId: string;
  run_id?: string;
  workflowName: string;
  workflow_name?: string;
  status: string;
  urgency: 'urgent' | 'pending';
  requestedAt: string;
  requested_at?: string;
  slaDeadline: string;
  sla_deadline?: string;
  slaPercentRemaining: number;
  sla_percent_remaining?: number;
  proposedAction: Record<string, unknown>;
  proposed_action?: Record<string, unknown>;
  context: string;
  scopeBadges: string[];
  scope_badges?: string[];
  reversible: boolean;
  affectedSystems: string[];
  affected_systems?: string[];
  requestedBy: string;
  requested_by?: string;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  eventType: string;
  event_type?: string;
  actor: string;
  runId: string;
  run_id?: string;
  decision: string;
  payloadHash: string;
  payload_hash?: string;
  latencyMs: number;
  latency_ms?: number;
  detail?: string;
}

export interface Tool {
  id: string;
  name: string;
  version: string;
  description: string;
  health: 'running' | 'completed' | 'failed';
  healthLabel: string;
  health_label?: string;
  scopes: string[];
  costPerCall: number;
  cost_per_call?: number;
  timeoutMs: number;
  timeout_ms?: number;
  retryPolicy: string;
  retry_policy?: string;
  callsToday: number;
  calls_today?: number;
}

export interface KPIDashboard {
  active_runs: number;
  active_runs_change: number;
  avg_cycle_time: string;
  avg_cycle_time_change: number;
  cost_today: string;
  cost_today_change: number;
  pending_approvals: number;
  pending_approvals_change: number;
  sparkline_runs?: number[];
  sparkline_cycle?: number[];
  sparkline_cost?: number[];
  sparkline_approvals?: number[];
  [key: string]: unknown;
}

export interface KPIWorkflow {
  workflow_id: string;
  total_runs: number;
  success_rate: number;
  avg_cost: number;
  avg_duration: number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Normalizers — the API may return snake_case; the UI expects camelCase.
// These helpers merge both shapes so the rendering code always has a value.
// ---------------------------------------------------------------------------

function normalizeWorkflow(raw: Record<string, unknown>): Workflow {
  return {
    ...raw,
    id: (raw.id as string) || '',
    name: (raw.name as string) || '',
    status: ((raw.status as string) || 'draft') as Workflow['status'],
    description: (raw.description as string) || '',
    totalRuns: (raw.totalRuns ?? raw.total_runs ?? 0) as number,
    avgCost: (raw.avgCost ?? raw.avg_cost ?? 0) as number,
    lastRunAt: (raw.lastRunAt ?? raw.last_run_at ?? '') as string,
    stepsCount: (raw.stepsCount ?? raw.steps_count ?? 0) as number,
  } as Workflow;
}

function normalizeRun(raw: Record<string, unknown>): Run {
  return {
    ...raw,
    id: (raw.id as string) || '',
    workflow: (raw.workflow ?? raw.workflow_name ?? '') as string,
    status: (raw.status as string) || '',
    trigger: (raw.trigger as string) || '',
    steps: (raw.steps as string) || '',
    cost: (raw.cost ?? 0) as number,
    duration: (raw.duration ?? 0) as number,
    started: (raw.started ?? raw.started_at ?? '') as string,
  } as Run;
}

function normalizeApproval(raw: Record<string, unknown>): ApprovalItem {
  return {
    ...raw,
    id: (raw.id as string) || '',
    runId: (raw.runId ?? raw.run_id ?? '') as string,
    workflowName: (raw.workflowName ?? raw.workflow_name ?? '') as string,
    status: (raw.status as string) || 'awaiting_approval',
    urgency: ((raw.urgency as string) || 'pending') as ApprovalItem['urgency'],
    requestedAt: (raw.requestedAt ?? raw.requested_at ?? '') as string,
    slaDeadline: (raw.slaDeadline ?? raw.sla_deadline ?? '') as string,
    slaPercentRemaining: (raw.slaPercentRemaining ?? raw.sla_percent_remaining ?? 0) as number,
    proposedAction: (raw.proposedAction ?? raw.proposed_action ?? {}) as Record<string, unknown>,
    context: (raw.context as string) || '',
    scopeBadges: (raw.scopeBadges ?? raw.scope_badges ?? []) as string[],
    reversible: (raw.reversible ?? false) as boolean,
    affectedSystems: (raw.affectedSystems ?? raw.affected_systems ?? []) as string[],
    requestedBy: (raw.requestedBy ?? raw.requested_by ?? '') as string,
  } as ApprovalItem;
}

function normalizeAuditEvent(raw: Record<string, unknown>): AuditEvent {
  return {
    ...raw,
    id: (raw.id as string) || '',
    timestamp: (raw.timestamp as string) || '',
    eventType: (raw.eventType ?? raw.event_type ?? '') as string,
    actor: (raw.actor as string) || '',
    runId: (raw.runId ?? raw.run_id ?? '') as string,
    decision: (raw.decision as string) || '',
    payloadHash: (raw.payloadHash ?? raw.payload_hash ?? '') as string,
    latencyMs: (raw.latencyMs ?? raw.latency_ms ?? 0) as number,
    detail: (raw.detail as string) || undefined,
  } as AuditEvent;
}

function normalizeTool(raw: Record<string, unknown>): Tool {
  return {
    ...raw,
    id: (raw.id as string) || '',
    name: (raw.name as string) || '',
    version: (raw.version as string) || '',
    description: (raw.description as string) || '',
    health: ((raw.health as string) || 'completed') as Tool['health'],
    healthLabel: (raw.healthLabel ?? raw.health_label ?? 'Unknown') as string,
    scopes: (raw.scopes ?? []) as string[],
    costPerCall: (raw.costPerCall ?? raw.cost_per_call ?? 0) as number,
    timeoutMs: (raw.timeoutMs ?? raw.timeout_ms ?? 10000) as number,
    retryPolicy: (raw.retryPolicy ?? raw.retry_policy ?? '') as string,
    callsToday: (raw.callsToday ?? raw.calls_today ?? 0) as number,
  } as Tool;
}

// ---------------------------------------------------------------------------
// Public hooks
// ---------------------------------------------------------------------------

/** Fetch all workflows, optionally filtered by status. */
export function useWorkflows(status?: string) {
  const params: Record<string, string | number | undefined> = {};
  if (status && status !== 'all') params.status = status;

  const result = useAPI<Workflow[]>(
    () =>
      api
        .get<Record<string, unknown>[]>('/workflows', params)
        .then((rows) => rows.map(normalizeWorkflow)),
    [status],
    [],
  );

  return { workflows: result.data ?? [], ...result };
}

/** Fetch a single workflow by ID. */
export function useWorkflow(id: string | undefined) {
  const result = useAPI<Workflow>(
    id
      ? () =>
          api
            .get<Record<string, unknown>>(`/workflows/${id}`)
            .then(normalizeWorkflow)
      : null,
    [id],
  );

  return { workflow: result.data, ...result };
}

/** Fetch runs with optional query params (limit, status, workflow, etc.). */
export function useRuns(params?: Record<string, string | number | undefined>) {
  const key = JSON.stringify(params ?? {});

  const result = useAPI<Run[]>(
    () =>
      api
        .get<Record<string, unknown>[]>('/runs', params)
        .then((rows) => rows.map(normalizeRun)),
    [key],
    [],
  );

  return { runs: result.data ?? [], ...result };
}

/** Fetch a single run by ID. */
export function useRun(id: string | undefined) {
  const result = useAPI<Run>(
    id
      ? () =>
          api.get<Record<string, unknown>>(`/runs/${id}`).then(normalizeRun)
      : null,
    [id],
  );

  return { run: result.data, ...result };
}

/** Fetch the approval queue. */
export function useApprovals() {
  const result = useAPI<ApprovalItem[]>(
    () =>
      api
        .get<Record<string, unknown>[]>('/approvals')
        .then((rows) => rows.map(normalizeApproval)),
    [],
    [],
  );

  /** Approve a specific approval item. */
  const approve = useCallback(async (approvalId: string) => {
    await api.post(`/approvals/${approvalId}/approve`);
    result.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Reject a specific approval item. */
  const reject = useCallback(async (approvalId: string) => {
    await api.post(`/approvals/${approvalId}/reject`);
    result.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { approvals: result.data ?? [], ...result, approve, reject };
}

/** Fetch audit events with optional filters. */
export function useAuditEvents(params?: Record<string, string | number | undefined>) {
  const key = JSON.stringify(params ?? {});

  const result = useAPI<AuditEvent[]>(
    () =>
      api
        .get<Record<string, unknown>[]>('/audit', params)
        .then((rows) => rows.map(normalizeAuditEvent)),
    [key],
    [],
  );

  return { events: result.data ?? [], ...result };
}

/** Fetch all registered tools. */
export function useTools() {
  const result = useAPI<Tool[]>(
    () =>
      api
        .get<Record<string, unknown>[]>('/tools')
        .then((rows) => rows.map(normalizeTool)),
    [],
    [],
  );

  return { tools: result.data ?? [], ...result };
}

/** Fetch the KPI dashboard summary. */
export function useKPIDashboard() {
  const result = useAPI<KPIDashboard>(
    () => api.get<KPIDashboard>('/kpi/dashboard'),
    [],
  );

  return { dashboard: result.data, ...result };
}

/** Fetch KPI data for a specific workflow. */
export function useKPIWorkflow(workflowId: string | undefined) {
  const result = useAPI<KPIWorkflow>(
    workflowId
      ? () => api.get<KPIWorkflow>(`/kpi/workflows/${workflowId}`)
      : null,
    [workflowId],
  );

  return { kpi: result.data, ...result };
}
