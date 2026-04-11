import { cn } from '@/lib/utils';
import type { RunStatus } from '@agent-os/types';

const STATUS_STYLES: Record<string, string> = {
  running: 'bg-accent animate-pulse-status',
  completed: 'bg-success',
  awaiting_approval: 'bg-warning',
  failed: 'bg-danger',
  timed_out: 'bg-danger',
  queued: 'bg-txt-2',
  cancelled: 'bg-txt-3',
};

const STATUS_LABELS: Record<string, string> = {
  running: 'Running',
  completed: 'Completed',
  awaiting_approval: 'Awaiting Approval',
  failed: 'Failed',
  timed_out: 'Timed Out',
  queued: 'Queued',
  cancelled: 'Cancelled',
};

interface StatusDotProps {
  status: string;
  showLabel?: boolean;
  className?: string;
}

export function StatusDot({ status, showLabel = false, className }: StatusDotProps) {
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span
        className={cn('status-dot', STATUS_STYLES[status] || 'bg-txt-3')}
        aria-label={STATUS_LABELS[status] || status}
      />
      {showLabel && (
        <span className="text-xs text-txt-2">{STATUS_LABELS[status] || status}</span>
      )}
    </span>
  );
}
