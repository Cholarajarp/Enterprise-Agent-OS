'use client';

import { cn } from '@/lib/utils';
import { formatRunId, formatDuration, formatCost } from '@/lib/utils';
import { StatusDot } from '@/components/common/StatusDot';
import { useRunDrawerStore } from '@/stores/ui';
import {
  X, RotateCcw, ExternalLink, FileText,
  Cpu, Wrench, ShieldCheck, GitBranch,
  ChevronDown, ChevronRight,
} from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';

// Demo step data
const MOCK_STEPS = [
  { index: 0, type: 'tool_call', name: 'Enrich Alert', status: 'completed', duration: 2300, tool: 'PagerDuty:get_incident_details' },
  { index: 1, type: 'tool_call', name: 'Fetch Metrics', status: 'completed', duration: 1800, tool: 'Datadog:get_metrics' },
  { index: 2, type: 'llm_call', name: 'Diagnose Root Cause', status: 'completed', duration: 4200, tool: null },
  { index: 3, type: 'approval_gate', name: 'Approve Auto-Resolution', status: 'running', duration: 0, tool: null },
  { index: 4, type: 'tool_call', name: 'Execute Resolution', status: 'queued', duration: 0, tool: 'Kubernetes:restart_deployment' },
  { index: 5, type: 'llm_call', name: 'Verify Resolution', status: 'queued', duration: 0, tool: null },
  { index: 6, type: 'tool_call', name: 'Close & Document', status: 'queued', duration: 0, tool: null },
  { index: 7, type: 'tool_call', name: 'Update KPI Ledger', status: 'queued', duration: 0, tool: null },
];

const STEP_ICONS: Record<string, typeof Cpu> = {
  llm_call: Cpu,
  tool_call: Wrench,
  approval_gate: ShieldCheck,
  branch: GitBranch,
};

const STEP_COLORS: Record<string, string> = {
  llm_call: 'text-accent',
  tool_call: 'text-success',
  approval_gate: 'text-warning',
  branch: 'text-purple',
};

export function RunDrawer() {
  const { runId, close } = useRunDrawerStore();
  const [expandedStep, setExpandedStep] = useState<number | null>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    },
    [close]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!runId) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-void/40"
        onClick={close}
      />

      {/* Drawer */}
      <div
        className={cn(
          'fixed right-0 top-0 z-50 h-screen w-120',
          'bg-surface border-l border-border',
          'animate-slide-in-right overflow-y-auto'
        )}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-surface border-b border-border px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <StatusDot status="running" />
              <span className="font-mono text-xs text-txt-2">{formatRunId(runId)}</span>
            </div>
            <div className="flex items-center gap-1">
              <button className="btn-ghost" aria-label="Rerun">
                <RotateCcw size={14} />
              </button>
              <button className="btn-ghost" aria-label="View audit trail">
                <FileText size={14} />
              </button>
              <button className="btn-ghost" aria-label="Open in new tab">
                <ExternalLink size={14} />
              </button>
              <button className="btn-ghost" onClick={close} aria-label="Close drawer">
                <X size={14} />
              </button>
            </div>
          </div>
          <h2 className="font-display text-lg font-semibold text-txt-1">IT Incident Triage</h2>
          <div className="flex items-center gap-3 mt-1.5">
            <span className="text-xs text-txt-3">PagerDuty webhook</span>
            <span className="text-xs text-txt-3">4/8 steps</span>
            <span className="badge bg-accent/10 text-accent border border-accent/20">
              {formatCost(0.0234)}
            </span>
          </div>
        </div>

        {/* Steps */}
        <div className="p-4">
          <h3 className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-3">
            Execution Steps
          </h3>
          <div className="space-y-1">
            {MOCK_STEPS.map((step) => {
              const Icon = STEP_ICONS[step.type] || Wrench;
              const color = STEP_COLORS[step.type] || 'text-txt-2';
              const expanded = expandedStep === step.index;

              return (
                <div key={step.index}>
                  <button
                    className={cn(
                      'flex items-center gap-3 w-full px-3 py-2 rounded-md text-left',
                      'transition-colors duration-80',
                      step.status === 'completed' && 'hover:bg-elevated',
                      step.status === 'running' && 'bg-accent/5 border border-accent/10',
                      step.status === 'queued' && 'opacity-50'
                    )}
                    onClick={() => setExpandedStep(expanded ? null : step.index)}
                    disabled={step.status === 'queued'}
                  >
                    <Icon size={14} className={cn('flex-shrink-0', color)} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-txt-1 truncate">{step.name}</p>
                      {step.tool && (
                        <p className="font-mono text-2xs text-txt-3 truncate">{step.tool}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <StatusDot status={step.status} />
                      {step.duration > 0 && (
                        <span className="font-mono text-2xs text-txt-3">
                          {formatDuration(step.duration)}
                        </span>
                      )}
                      {step.status !== 'queued' && (
                        expanded
                          ? <ChevronDown size={12} className="text-txt-3" />
                          : <ChevronRight size={12} className="text-txt-3" />
                      )}
                    </div>
                  </button>

                  {/* Expanded detail */}
                  {expanded && step.status !== 'queued' && (
                    <div className="ml-8 mr-3 my-1 p-3 rounded-md bg-void border border-border-sub">
                      <pre className="font-mono text-2xs text-txt-2 whitespace-pre-wrap">
{`{
  "tool": "${step.tool || 'claude-opus-4-5'}",
  "params": {
    "incident_id": "INC-8842",
    "service": "payment-gateway",
    "lookback_minutes": 30
  },
  "result": {
    "status": "success",
    "data": { "..." }
  }
}`}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Agent Reasoning Stream */}
        <div className="p-4 border-t border-border-sub">
          <h3 className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-3">
            Agent Reasoning
          </h3>
          <div className="bg-void rounded-md border border-border-sub p-3 max-h-48 overflow-y-auto">
            <p className="font-mono text-2xs text-txt-2 leading-relaxed">
              <span className="text-accent">[plan]</span> Analyzing PagerDuty alert INC-8842 for payment-gateway service.
              {'\n'}
              <span className="text-accent">[observe]</span> Enriched with Datadog metrics: error rate spike from 0.1% to 12.4% at 10:18 UTC.
              {'\n'}
              <span className="text-accent">[reason]</span> Cross-referencing with recent deployments — deploy-4421 rolled out at 10:15 UTC.
              {'\n'}
              <span className="text-accent">[conclude]</span> Root cause: deployment deploy-4421 introduced regression in payment validation.
              Confidence: 91%. Recommended action: rollback deploy-4421.
              {'\n'}
              <span className="text-warning">[gate]</span> Action requires approval. Requesting review from on-call team.
              <span className="animate-pulse">_</span>
            </p>
          </div>
        </div>

        {/* Cost Breakdown */}
        <div className="p-4 border-t border-border-sub">
          <h3 className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-3">
            Cost Breakdown
          </h3>
          <div className="space-y-1.5">
            {[
              { label: 'Input tokens (2,847)', cost: 0.0085 },
              { label: 'Output tokens (1,234)', cost: 0.0074 },
              { label: 'Tool calls (4)', cost: 0.0040 },
              { label: 'Compute (12.4s)', cost: 0.0035 },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between">
                <span className="text-xs text-txt-2">{item.label}</span>
                <span className="font-mono text-xs text-txt-2">{formatCost(item.cost)}</span>
              </div>
            ))}
            <div className="flex items-center justify-between pt-1.5 border-t border-border-sub">
              <span className="text-xs font-medium text-txt-1">Total</span>
              <span className="font-mono text-xs font-medium text-txt-1">{formatCost(0.0234)}</span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="p-4 border-t border-border-sub flex items-center gap-2">
          <button className="btn-secondary flex-1">
            <RotateCcw size={14} />
            Rerun
          </button>
          <button className="btn-danger flex-1">
            <X size={14} />
            Cancel
          </button>
        </div>
      </div>
    </>
  );
}
