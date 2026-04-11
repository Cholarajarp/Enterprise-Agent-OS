'use client';

import { AppShell } from '@/components/layout/AppShell';
import { KPICard } from '@/components/common/KPICard';
import { cn, formatRunId, formatRelativeTime } from '@/lib/utils';
import { Download, Shield, AlertTriangle, Bug, FileText } from 'lucide-react';

type EventType =
  | 'tool_call'
  | 'approval_requested'
  | 'scope_violation'
  | 'injection_detected'
  | 'pii_redacted'
  | 'run_started'
  | 'run_completed';

type Decision = 'allowed' | 'blocked' | 'redacted' | 'escalated';

interface AuditEvent {
  id: string;
  timestamp: string;
  eventType: EventType;
  actor: string;
  runId: string;
  decision: Decision;
  payloadHash: string;
  latencyMs: number;
  detail?: string;
}

const EVENT_BADGE: Record<EventType, string> = {
  tool_call: 'bg-accent/10 text-accent',
  approval_requested: 'bg-warning/10 text-warning',
  scope_violation: 'bg-danger/10 text-danger',
  injection_detected: 'bg-danger/10 text-danger font-bold',
  pii_redacted: 'bg-purple/10 text-purple',
  run_started: 'bg-success/10 text-success',
  run_completed: 'bg-success/10 text-success',
};

const EVENT_LABEL: Record<EventType, string> = {
  tool_call: 'tool_call',
  approval_requested: 'approval_requested',
  scope_violation: 'scope_violation',
  injection_detected: 'injection_detected',
  pii_redacted: 'pii_redacted',
  run_started: 'run_started',
  run_completed: 'run_completed',
};

const DECISION_STYLE: Record<Decision, string> = {
  allowed: 'text-success',
  blocked: 'text-danger font-semibold',
  redacted: 'text-purple',
  escalated: 'text-warning',
};

const MOCK_EVENTS: AuditEvent[] = [
  { id: 'ev-001', timestamp: '2026-04-11T10:23:12Z', eventType: 'run_started', actor: 'system:scheduler', runId: '01968f2a-3b4c-7def-8901-234567890abc', decision: 'allowed', payloadHash: 'sha256:a3f8…e91c', latencyMs: 2 },
  { id: 'ev-002', timestamp: '2026-04-11T10:23:14Z', eventType: 'tool_call', actor: 'agent:incident-triage-v3', runId: '01968f2a-3b4c-7def-8901-234567890abc', decision: 'allowed', payloadHash: 'sha256:b4c9…f02d', latencyMs: 8 },
  { id: 'ev-003', timestamp: '2026-04-11T10:23:18Z', eventType: 'tool_call', actor: 'agent:incident-triage-v3', runId: '01968f2a-3b4c-7def-8901-234567890abc', decision: 'allowed', payloadHash: 'sha256:c5d0…a13e', latencyMs: 12 },
  { id: 'ev-004', timestamp: '2026-04-11T10:23:22Z', eventType: 'pii_redacted', actor: 'guardian:pii-filter', runId: '01968f2a-3b4c-7def-8901-234567890abc', decision: 'redacted', payloadHash: 'sha256:d6e1…b24f', latencyMs: 3 },
  { id: 'ev-005', timestamp: '2026-04-11T10:23:26Z', eventType: 'approval_requested', actor: 'agent:incident-triage-v3', runId: '01968f2a-3b4c-7def-8901-234567890abc', decision: 'escalated', payloadHash: 'sha256:e7f2…c35a', latencyMs: 5 },
  { id: 'ev-006', timestamp: '2026-04-11T10:20:05Z', eventType: 'scope_violation', actor: 'agent:cost-anomaly-v2', runId: '01968f2a-2b3c-6def-7890-123456789abc', decision: 'blocked', payloadHash: 'sha256:f8a3…d46b', latencyMs: 1 },
  { id: 'ev-007', timestamp: '2026-04-11T10:15:00Z', eventType: 'run_started', actor: 'user:john.doe', runId: '01968f2a-1a2b-5cde-6789-012345678abc', decision: 'allowed', payloadHash: 'sha256:a9b4…e57c', latencyMs: 3 },
  { id: 'ev-008', timestamp: '2026-04-11T10:15:45Z', eventType: 'tool_call', actor: 'agent:deploy-rollback-v2', runId: '01968f2a-1a2b-5cde-6789-012345678abc', decision: 'allowed', payloadHash: 'sha256:b0c5…f68d', latencyMs: 7 },
  { id: 'ev-009', timestamp: '2026-04-11T10:16:02Z', eventType: 'injection_detected', actor: 'guardian:prompt-shield', runId: '01968f2a-1a2b-5cde-6789-012345678abc', decision: 'blocked', payloadHash: 'sha256:c1d6…a79e', latencyMs: 2 },
  { id: 'ev-010', timestamp: '2026-04-11T10:16:10Z', eventType: 'tool_call', actor: 'agent:deploy-rollback-v2', runId: '01968f2a-1a2b-5cde-6789-012345678abc', decision: 'allowed', payloadHash: 'sha256:d2e7…b80f', latencyMs: 9 },
  { id: 'ev-011', timestamp: '2026-04-11T10:16:55Z', eventType: 'run_completed', actor: 'system:runtime', runId: '01968f2a-1a2b-5cde-6789-012345678abc', decision: 'allowed', payloadHash: 'sha256:e3f8…c91a', latencyMs: 1 },
  { id: 'ev-012', timestamp: '2026-04-11T10:00:00Z', eventType: 'run_started', actor: 'system:scheduler', runId: '01968f29-fa0a-3abc-4567-890123456abc', decision: 'allowed', payloadHash: 'sha256:f4a9…d02b', latencyMs: 2 },
  { id: 'ev-013', timestamp: '2026-04-11T10:00:12Z', eventType: 'tool_call', actor: 'agent:knowledge-sync-v1', runId: '01968f29-fa0a-3abc-4567-890123456abc', decision: 'allowed', payloadHash: 'sha256:a5b0…e13c', latencyMs: 15 },
  { id: 'ev-014', timestamp: '2026-04-11T09:45:30Z', eventType: 'scope_violation', actor: 'agent:ticket-enrichment-v3', runId: '01968f29-e90f-2abc-3456-789012345abc', decision: 'blocked', payloadHash: 'sha256:b6c1…f24d', latencyMs: 1 },
  { id: 'ev-015', timestamp: '2026-04-11T09:30:00Z', eventType: 'pii_redacted', actor: 'guardian:pii-filter', runId: '01968f29-d80e-1abc-2345-678901234abc', decision: 'redacted', payloadHash: 'sha256:c7d2…a35e', latencyMs: 4 },
];

const KPI_SPARKLINE_EVENTS = [82, 95, 78, 102, 88, 115, 98, 124, 132, 128, 145, 156];
const KPI_SPARKLINE_BLOCKED = [2, 1, 3, 0, 2, 1, 4, 2, 1, 3, 2, 3];
const KPI_SPARKLINE_INJECTIONS = [0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1];

export default function GovernancePage() {
  return (
    <AppShell>
      {/* Page header */}
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-txt-1">
          Governance & Audit
        </h1>
        <p className="text-sm text-txt-2 mt-1">Immutable audit trail</p>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <KPICard
          label="Total Events (Today)"
          value="156"
          change={{ value: 18, label: 'vs yesterday' }}
          sparklineData={KPI_SPARKLINE_EVENTS}
        />
        <KPICard
          label="Blocked Attempts"
          value="3"
          change={{ value: -25, label: 'vs yesterday' }}
          sparklineData={KPI_SPARKLINE_BLOCKED}
        />
        <KPICard
          label="Injection Detections"
          value="1"
          change={{ value: 0, label: 'vs yesterday' }}
          sparklineData={KPI_SPARKLINE_INJECTIONS}
        />
      </div>

      {/* Export buttons */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-display text-lg font-semibold text-txt-1">Audit Log</h2>
        <div className="flex items-center gap-2">
          <button className="btn-secondary text-xs">
            <Download size={12} />
            Export CSV
          </button>
          <button className="btn-secondary text-xs">
            <FileText size={12} />
            Export JSON
          </button>
        </div>
      </div>

      {/* Audit log table */}
      <div className="border border-border rounded-lg overflow-hidden mb-4">
        {/* Header */}
        <div className="grid grid-cols-[140px_150px_180px_100px_88px_140px_72px] items-center h-8 px-3 bg-surface text-2xs font-medium tracking-wider text-txt-3 uppercase border-b border-border">
          <div>Timestamp</div>
          <div>Event Type</div>
          <div>Actor</div>
          <div>Run ID</div>
          <div>Decision</div>
          <div>Payload Hash</div>
          <div>Latency</div>
        </div>

        {/* Rows */}
        {MOCK_EVENTS.map((ev) => {
          const isBlocked = ev.decision === 'blocked';
          const isViolation =
            ev.eventType === 'scope_violation' || ev.eventType === 'injection_detected';

          return (
            <div
              key={ev.id}
              className={cn(
                'table-row grid grid-cols-[140px_150px_180px_100px_88px_140px_72px] items-center px-3',
                (isBlocked || isViolation) && 'bg-danger/5'
              )}
            >
              <div className="font-mono text-2xs text-txt-3">
                {new Date(ev.timestamp).toLocaleTimeString('en-US', {
                  hour12: false,
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </div>
              <div>
                <span
                  className={cn(
                    'badge border-0 text-2xs',
                    EVENT_BADGE[ev.eventType]
                  )}
                >
                  {EVENT_LABEL[ev.eventType]}
                </span>
              </div>
              <div className="font-mono text-2xs text-txt-2 truncate">
                {ev.actor}
              </div>
              <div className="font-mono text-2xs text-txt-3">
                {formatRunId(ev.runId)}
              </div>
              <div
                className={cn(
                  'text-2xs font-mono',
                  DECISION_STYLE[ev.decision]
                )}
              >
                {ev.decision}
              </div>
              <div className="font-mono text-2xs text-txt-3 truncate">
                {ev.payloadHash}
              </div>
              <div className="font-mono text-2xs text-txt-3 text-right">
                {ev.latencyMs}ms
              </div>
            </div>
          );
        })}
      </div>

      {/* Tamper evidence footer */}
      <div className="flex items-center gap-2 text-xs text-success">
        <Shield size={12} />
        <span>Tamper evidence: hash chain validated</span>
      </div>
    </AppShell>
  );
}
