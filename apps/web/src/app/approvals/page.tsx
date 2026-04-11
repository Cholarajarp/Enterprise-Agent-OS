'use client';

import { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { cn, formatRunId, formatRelativeTime } from '@/lib/utils';
import {
  ShieldCheck,
  AlertTriangle,
  Clock,
  CheckCircle,
  XCircle,
  Edit3,
  ChevronDown,
  Users,
} from 'lucide-react';

type ApprovalUrgency = 'urgent' | 'pending';

interface ApprovalItem {
  id: string;
  runId: string;
  workflowName: string;
  status: 'awaiting_approval';
  urgency: ApprovalUrgency;
  requestedAt: string;
  slaDeadline: string;
  slaPercentRemaining: number;
  proposedAction: Record<string, unknown>;
  context: string;
  scopeBadges: string[];
  reversible: boolean;
  affectedSystems: string[];
  requestedBy: string;
}

const MOCK_APPROVALS: ApprovalItem[] = [
  {
    id: 'apr-001',
    runId: '01968f2a-3b4c-7def-8901-234567890abc',
    workflowName: 'IT Incident Triage',
    status: 'awaiting_approval',
    urgency: 'urgent',
    requestedAt: '2026-04-11T10:20:00Z',
    slaDeadline: '2026-04-11T10:35:00Z',
    slaPercentRemaining: 12,
    proposedAction: {
      action: 'kubernetes:rollback_deployment',
      target: 'payment-gateway',
      namespace: 'production',
      from_version: 'v2.14.3',
      to_version: 'v2.14.2',
      reason: 'Error rate spike detected (12.4% vs 0.1% baseline)',
    },
    context:
      'PagerDuty incident INC-8842 triggered for payment-gateway service. Datadog metrics show error rate spike from 0.1% to 12.4% correlated with deployment deploy-4421 at 10:15 UTC. Agent recommends rollback to previous stable version.',
    scopeBadges: ['kubernetes:write', 'deployment:rollback'],
    reversible: true,
    affectedSystems: ['payment-gateway', 'checkout-service'],
    requestedBy: 'agent:incident-triage-v3',
  },
  {
    id: 'apr-002',
    runId: '01968f2a-2b3c-6def-7890-123456789abc',
    workflowName: 'Cost Anomaly Detection',
    status: 'awaiting_approval',
    urgency: 'pending',
    requestedAt: '2026-04-11T09:45:00Z',
    slaDeadline: '2026-04-11T13:45:00Z',
    slaPercentRemaining: 68,
    proposedAction: {
      action: 'aws:terminate_instances',
      target: 'i-0a1b2c3d4e5f6g7h8',
      region: 'us-east-1',
      instance_type: 'p4d.24xlarge',
      monthly_cost: '$23,847.00',
      reason: 'GPU instance running with 0% utilization for 72+ hours',
    },
    context:
      'AWS Cost Explorer flagged anomalous spend in us-east-1. A p4d.24xlarge GPU instance has been running idle for over 72 hours with zero utilization, accumulating $2,961 in unnecessary charges. No active workloads or scheduled jobs found.',
    scopeBadges: ['aws:ec2:write', 'instance:terminate'],
    reversible: false,
    affectedSystems: ['aws:us-east-1', 'ml-training-pipeline'],
    requestedBy: 'agent:cost-anomaly-v2',
  },
  {
    id: 'apr-003',
    runId: '01968f2a-1a2b-5cde-6789-012345678abc',
    workflowName: 'Compliance Check',
    status: 'awaiting_approval',
    urgency: 'urgent',
    requestedAt: '2026-04-11T10:10:00Z',
    slaDeadline: '2026-04-11T10:40:00Z',
    slaPercentRemaining: 18,
    proposedAction: {
      action: 'postgresql:revoke_access',
      target: 'db-prod-analytics',
      user: 'svc-legacy-etl',
      permissions: ['SELECT', 'INSERT', 'UPDATE'],
      reason: 'Service account has excessive permissions violating least-privilege policy',
    },
    context:
      'SOC 2 compliance scan detected that service account svc-legacy-etl has INSERT and UPDATE permissions on db-prod-analytics, but has only performed SELECT queries in the last 90 days. This violates the least-privilege access control requirement (CC6.3).',
    scopeBadges: ['postgresql:admin', 'access:revoke'],
    reversible: true,
    affectedSystems: ['db-prod-analytics', 'legacy-etl-pipeline'],
    requestedBy: 'agent:compliance-auditor-v1',
  },
];

type FilterTab = 'urgent' | 'pending' | 'all';

const FILTER_TABS: Array<{ label: string; value: FilterTab }> = [
  { label: 'Urgent', value: 'urgent' },
  { label: 'Pending', value: 'pending' },
  { label: 'All', value: 'all' },
];

export default function ApprovalsPage() {
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all');

  const filtered =
    activeFilter === 'all'
      ? MOCK_APPROVALS
      : activeFilter === 'urgent'
        ? MOCK_APPROVALS.filter((a) => a.slaPercentRemaining < 20)
        : MOCK_APPROVALS.filter((a) => a.slaPercentRemaining >= 20);

  const urgentCount = MOCK_APPROVALS.filter((a) => a.slaPercentRemaining < 20).length;

  return (
    <AppShell>
      {/* Page header */}
      <div className="flex items-center gap-3 mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-txt-1">Approval Queue</h1>
            <span className="badge bg-warning/10 text-warning border border-warning/20 text-xs">
              {MOCK_APPROVALS.length}
            </span>
          </div>
          <p className="text-sm text-txt-2 mt-1">
            Human-in-the-loop decisions for high-risk agent actions
          </p>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1.5 mb-5">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveFilter(tab.value)}
            className={cn(
              'badge border transition-colors duration-80',
              activeFilter === tab.value
                ? 'bg-elevated border-border-em text-txt-1'
                : 'border-border text-txt-3 hover:text-txt-2 hover:border-border-hover',
              tab.value === 'urgent' && 'relative'
            )}
          >
            {tab.label}
            {tab.value === 'urgent' && urgentCount > 0 && (
              <span className="ml-1.5 inline-flex items-center justify-center w-4 h-4 rounded-full bg-danger text-[10px] text-white font-semibold">
                {urgentCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Approval cards */}
      <div className="space-y-4">
        {filtered.map((item) => {
          const isUrgent = item.slaPercentRemaining < 20;

          return (
            <div
              key={item.id}
              className={cn(
                'bg-surface border rounded-lg p-5',
                isUrgent ? 'border-danger/30' : 'border-border'
              )}
            >
              {/* Top row */}
              <div className="flex items-center gap-3 mb-4">
                <ShieldCheck
                  size={16}
                  className={isUrgent ? 'text-danger' : 'text-warning'}
                />
                <span className="text-sm font-medium text-txt-1">
                  {item.workflowName}
                </span>
                <span className="font-mono text-2xs text-txt-3">
                  {formatRunId(item.runId)}
                </span>
                <span className="badge bg-warning/10 text-warning border border-warning/20 text-2xs">
                  Awaiting Approval
                </span>
                <div className="flex-1" />
                <span className="text-2xs text-txt-3">
                  Requested {formatRelativeTime(item.requestedAt)}
                </span>
              </div>

              {/* Proposed Action */}
              <div className="mb-4">
                <h4 className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-2">
                  Proposed Action
                </h4>
                <pre className="bg-void font-mono text-xs text-txt-2 border border-border rounded p-3 overflow-x-auto">
                  {JSON.stringify(item.proposedAction, null, 2)}
                </pre>
              </div>

              {/* Context */}
              <div className="mb-4">
                <h4 className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-2">
                  Context
                </h4>
                <p className="text-xs text-txt-2 leading-relaxed">{item.context}</p>
              </div>

              {/* Risk indicators */}
              <div className="flex items-center flex-wrap gap-2 mb-4">
                {item.scopeBadges.map((scope) => (
                  <span
                    key={scope}
                    className="badge bg-accent/10 text-accent border border-accent/20 text-2xs font-mono"
                  >
                    {scope}
                  </span>
                ))}
                <span
                  className={cn(
                    'badge border text-2xs',
                    item.reversible
                      ? 'bg-success/10 text-success border-success/20'
                      : 'bg-danger/10 text-danger border-danger/20'
                  )}
                >
                  {item.reversible ? 'Reversible' : 'Irreversible'}
                </span>
                {item.affectedSystems.map((sys) => (
                  <span
                    key={sys}
                    className="badge bg-elevated text-txt-2 border border-border text-2xs"
                  >
                    {sys}
                  </span>
                ))}
              </div>

              {/* SLA countdown */}
              <div className="mb-5">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-2xs text-txt-3 flex items-center gap-1">
                    <Clock size={10} />
                    SLA Deadline
                  </span>
                  <span
                    className={cn(
                      'text-2xs font-mono font-medium',
                      isUrgent ? 'text-danger' : 'text-txt-2'
                    )}
                  >
                    {item.slaPercentRemaining}% remaining
                  </span>
                </div>
                <div className="h-1.5 bg-void rounded-full overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all',
                      isUrgent ? 'bg-danger' : 'bg-warning'
                    )}
                    style={{ width: `${item.slaPercentRemaining}%` }}
                  />
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-2">
                <button className="btn-primary bg-success hover:bg-success/90 text-sm">
                  <CheckCircle size={14} />
                  Approve
                </button>
                <button className="btn-danger text-sm">
                  <XCircle size={14} />
                  Reject
                </button>
                <button className="btn-secondary text-sm">
                  <Edit3 size={14} />
                  Modify & Approve
                </button>
                <div className="flex-1" />
                <button className="btn-ghost text-xs flex items-center gap-1">
                  <Users size={12} />
                  Reassign
                  <ChevronDown size={10} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </AppShell>
  );
}
