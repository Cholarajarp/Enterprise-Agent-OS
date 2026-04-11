'use client';

import { cn } from '@/lib/utils';
import { formatRunId, formatDuration, formatCost, formatRelativeTime } from '@/lib/utils';
import { StatusDot } from '@/components/common/StatusDot';
import { useRunDrawerStore } from '@/stores/ui';
import { ExternalLink, MoreHorizontal, RotateCcw, X as XIcon } from 'lucide-react';

// Demo data — replaced by TanStack Query in production
const MOCK_RUNS = [
  { id: '01968f2a-3b4c-7def-8901-234567890abc', workflow: 'IT Incident Triage', status: 'running', trigger: 'PagerDuty webhook', steps: '4/8', cost: 0.0234, duration: 12400, started: '2026-04-11T10:23:00Z' },
  { id: '01968f2a-2b3c-6def-7890-123456789abc', workflow: 'IT Incident Triage', status: 'awaiting_approval', trigger: 'PagerDuty webhook', steps: '3/8', cost: 0.0189, duration: 8200, started: '2026-04-11T10:20:00Z' },
  { id: '01968f2a-1a2b-5cde-6789-012345678abc', workflow: 'Deploy Rollback', status: 'completed', trigger: 'Manual', steps: '6/6', cost: 0.0412, duration: 45200, started: '2026-04-11T10:15:00Z' },
  { id: '01968f2a-0a1b-4bcd-5678-901234567abc', workflow: 'IT Incident Triage', status: 'failed', trigger: 'PagerDuty webhook', steps: '2/8', cost: 0.0098, duration: 3100, started: '2026-04-11T10:12:00Z' },
  { id: '01968f29-fa0a-3abc-4567-890123456abc', workflow: 'Knowledge Sync', status: 'completed', trigger: 'Schedule (cron)', steps: '4/4', cost: 0.0056, duration: 21000, started: '2026-04-11T10:00:00Z' },
  { id: '01968f29-e90f-2abc-3456-789012345abc', workflow: 'IT Incident Triage', status: 'completed', trigger: 'PagerDuty webhook', steps: '8/8', cost: 0.0367, duration: 52300, started: '2026-04-11T09:45:00Z' },
  { id: '01968f29-d80e-1abc-2345-678901234abc', workflow: 'Ticket Enrichment', status: 'cancelled', trigger: 'Jira webhook', steps: '1/5', cost: 0.0012, duration: 1200, started: '2026-04-11T09:30:00Z' },
  { id: '01968f29-c70d-0abc-1234-567890123abc', workflow: 'IT Incident Triage', status: 'completed', trigger: 'PagerDuty webhook', steps: '8/8', cost: 0.0298, duration: 38100, started: '2026-04-11T09:15:00Z' },
  { id: '01968f29-b60c-fabc-0123-456789012abc', workflow: 'Deploy Rollback', status: 'timed_out', trigger: 'GitHub Actions', steps: '3/6', cost: 0.0445, duration: 600000, started: '2026-04-11T09:00:00Z' },
  { id: '01968f29-a50b-eabc-fa12-345678901abc', workflow: 'IT Incident Triage', status: 'completed', trigger: 'PagerDuty webhook', steps: '7/8', cost: 0.0312, duration: 41200, started: '2026-04-11T08:45:00Z' },
];

interface RunsTableProps {
  className?: string;
}

export function RunsTable({ className }: RunsTableProps) {
  const { open: openDrawer } = useRunDrawerStore();

  return (
    <div className={cn('w-full', className)}>
      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex items-center gap-1.5">
          {['All', 'Running', 'Awaiting', 'Failed'].map((filter) => (
            <button
              key={filter}
              className={cn(
                'badge border transition-colors duration-80',
                filter === 'All'
                  ? 'bg-elevated border-border-em text-txt-1'
                  : 'border-border text-txt-3 hover:text-txt-2 hover:border-border-hover'
              )}
            >
              {filter}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <button className="btn-ghost text-xs">
          <RotateCcw size={12} />
          Refresh
        </button>
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[28px_100px_1fr_140px_60px_72px_80px_100px_40px] items-center h-8 px-3 bg-surface text-2xs font-medium tracking-wider text-txt-3 uppercase border-b border-border">
          <div />
          <div>Run ID</div>
          <div>Workflow</div>
          <div>Trigger</div>
          <div>Steps</div>
          <div>Cost</div>
          <div>Duration</div>
          <div>Started</div>
          <div />
        </div>

        {/* Rows */}
        {MOCK_RUNS.map((run) => (
          <div
            key={run.id}
            className="table-row grid grid-cols-[28px_100px_1fr_140px_60px_72px_80px_100px_40px] items-center px-3"
            onClick={() => openDrawer(run.id)}
            role="row"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && openDrawer(run.id)}
          >
            <div className="flex items-center justify-center">
              <StatusDot status={run.status} />
            </div>
            <div className="font-mono text-2xs text-txt-2">{formatRunId(run.id)}</div>
            <div className="text-sm text-txt-1 truncate pr-2">{run.workflow}</div>
            <div className="text-xs text-txt-2 truncate">{run.trigger}</div>
            <div className="font-mono text-xs text-txt-2">{run.steps}</div>
            <div className="font-mono text-xs text-txt-2">{formatCost(run.cost)}</div>
            <div className="font-mono text-xs text-txt-2">{formatDuration(run.duration)}</div>
            <div className="text-2xs text-txt-3">{formatRelativeTime(run.started)}</div>
            <div className="flex items-center justify-center">
              <button
                className="p-1 text-txt-3 hover:text-txt-2 transition-colors"
                onClick={(e) => e.stopPropagation()}
                aria-label="More actions"
              >
                <MoreHorizontal size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
