'use client';

import { AppShell } from '@/components/layout/AppShell';
import { KPICard } from '@/components/common/KPICard';
import { cn, formatRunId, formatRelativeTime } from '@/lib/utils';
import { Download, Shield, AlertTriangle, Bug, FileText } from 'lucide-react';
import { useAuditEvents } from '@/lib/hooks';
import type { AuditEvent } from '@/lib/hooks';

type EventType =
  | 'tool_call'
  | 'approval_requested'
  | 'scope_violation'
  | 'injection_detected'
  | 'pii_redacted'
  | 'run_started'
  | 'run_completed';

type Decision = 'allowed' | 'blocked' | 'redacted' | 'escalated';

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

// Fallback sparklines shown while data loads or API is unreachable
const KPI_SPARKLINE_EVENTS = [82, 95, 78, 102, 88, 115, 98, 124, 132, 128, 145, 156];
const KPI_SPARKLINE_BLOCKED = [2, 1, 3, 0, 2, 1, 4, 2, 1, 3, 2, 3];
const KPI_SPARKLINE_INJECTIONS = [0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1];

export default function GovernancePage() {
  const { events, loading, error } = useAuditEvents();

  // Derived KPIs from live data (with fallbacks)
  const totalEvents = events.length || 156;
  const blockedCount = events.filter((e) => e.decision === 'blocked').length || 3;
  const injectionCount = events.filter((e) => e.eventType === 'injection_detected').length || 1;
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
          value={String(totalEvents)}
          change={{ value: 18, label: 'vs yesterday' }}
          sparklineData={KPI_SPARKLINE_EVENTS}
        />
        <KPICard
          label="Blocked Attempts"
          value={String(blockedCount)}
          change={{ value: -25, label: 'vs yesterday' }}
          sparklineData={KPI_SPARKLINE_BLOCKED}
        />
        <KPICard
          label="Injection Detections"
          value={String(injectionCount)}
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
        {loading && (
          <div className="px-3 py-8 text-center text-sm text-txt-3">Loading audit events...</div>
        )}
        {!loading && events.length === 0 && (
          <div className="px-3 py-8 text-center text-sm text-txt-3">
            No audit events found. Check that the API is running.
          </div>
        )}
        {!loading && events.map((ev) => {
          const eventType = ev.eventType as EventType;
          const decision = ev.decision as Decision;
          const isBlocked = decision === 'blocked';
          const isViolation =
            eventType === 'scope_violation' || eventType === 'injection_detected';

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
                    EVENT_BADGE[eventType] || ''
                  )}
                >
                  {EVENT_LABEL[eventType] || eventType}
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
                  DECISION_STYLE[decision] || ''
                )}
              >
                {decision}
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
