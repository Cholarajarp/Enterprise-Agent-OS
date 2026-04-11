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
import { useApprovals } from '@/lib/hooks';
import type { ApprovalItem } from '@/lib/hooks';

type FilterTab = 'urgent' | 'pending' | 'all';

const FILTER_TABS: Array<{ label: string; value: FilterTab }> = [
  { label: 'Urgent', value: 'urgent' },
  { label: 'Pending', value: 'pending' },
  { label: 'All', value: 'all' },
];

export default function ApprovalsPage() {
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all');
  const { approvals, loading, error, approve, reject } = useApprovals();

  const filtered =
    activeFilter === 'all'
      ? approvals
      : activeFilter === 'urgent'
        ? approvals.filter((a) => a.slaPercentRemaining < 20)
        : approvals.filter((a) => a.slaPercentRemaining >= 20);

  const urgentCount = approvals.filter((a) => a.slaPercentRemaining < 20).length;

  return (
    <AppShell>
      {/* Page header */}
      <div className="flex items-center gap-3 mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-txt-1">Approval Queue</h1>
            <span className="badge bg-warning/10 text-warning border border-warning/20 text-xs">
              {approvals.length}
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

      {/* Loading state */}
      {loading && (
        <div className="text-sm text-txt-3 py-12 text-center">Loading approvals...</div>
      )}

      {/* Error state — graceful */}
      {error && !loading && approvals.length === 0 && (
        <div className="text-sm text-txt-3 py-12 text-center">
          Unable to load approvals. Check that the API is running.
        </div>
      )}

      {/* Approval cards */}
      {!loading && (
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
      )}
    </AppShell>
  );
}
