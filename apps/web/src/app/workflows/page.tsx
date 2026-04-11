'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AppShell } from '@/components/layout/AppShell';
import { StatusDot } from '@/components/common/StatusDot';
import { cn, formatCost, formatRelativeTime } from '@/lib/utils';
import { Plus, GitBranch, Play, Clock } from 'lucide-react';

type WorkflowStatus = 'draft' | 'staging' | 'production';

interface Workflow {
  id: string;
  name: string;
  status: WorkflowStatus;
  description: string;
  totalRuns: number;
  avgCost: number;
  lastRunAt: string;
  stepsCount: number;
}

const STATUS_BADGE: Record<WorkflowStatus, string> = {
  draft: 'bg-txt-3/10 text-txt-3 border-txt-3/20',
  staging: 'bg-warning/10 text-warning border-warning/20',
  production: 'bg-success/10 text-success border-success/20',
};

const STATUS_LABEL: Record<WorkflowStatus, string> = {
  draft: 'Draft',
  staging: 'Staging',
  production: 'Production',
};

const MOCK_WORKFLOWS: Workflow[] = [
  {
    id: 'wf-001',
    name: 'IT Incident Triage',
    status: 'production',
    description:
      'Automatically triages incoming PagerDuty incidents, enriches with Datadog metrics, diagnoses root cause, and proposes remediation with human approval.',
    totalRuns: 1284,
    avgCost: 0.034,
    lastRunAt: '2026-04-11T10:23:00Z',
    stepsCount: 8,
  },
  {
    id: 'wf-002',
    name: 'Deploy Rollback',
    status: 'production',
    description:
      'Monitors deployment health via GitHub Actions and Datadog. Triggers automatic rollback when error rates exceed thresholds, with approval gate for production.',
    totalRuns: 342,
    avgCost: 0.041,
    lastRunAt: '2026-04-11T10:15:00Z',
    stepsCount: 6,
  },
  {
    id: 'wf-003',
    name: 'Knowledge Sync',
    status: 'staging',
    description:
      'Periodically syncs internal documentation from Confluence and Notion into the agent knowledge base. Deduplicates and indexes for fast retrieval.',
    totalRuns: 89,
    avgCost: 0.006,
    lastRunAt: '2026-04-11T10:00:00Z',
    stepsCount: 4,
  },
  {
    id: 'wf-004',
    name: 'Ticket Enrichment',
    status: 'production',
    description:
      'Enriches incoming Jira tickets with related incidents, runbooks, and historical resolution data. Assigns priority and suggests resolution paths.',
    totalRuns: 2156,
    avgCost: 0.012,
    lastRunAt: '2026-04-11T09:30:00Z',
    stepsCount: 5,
  },
  {
    id: 'wf-005',
    name: 'Cost Anomaly Detection',
    status: 'staging',
    description:
      'Analyzes cloud spend data from AWS Cost Explorer and flags anomalous usage patterns. Sends Slack alerts and creates budget tickets automatically.',
    totalRuns: 56,
    avgCost: 0.022,
    lastRunAt: '2026-04-10T18:00:00Z',
    stepsCount: 6,
  },
  {
    id: 'wf-006',
    name: 'Compliance Check',
    status: 'draft',
    description:
      'Runs scheduled compliance audits against SOC 2 and ISO 27001 controls. Generates evidence reports and flags non-compliant resources for remediation.',
    totalRuns: 0,
    avgCost: 0,
    lastRunAt: '',
    stepsCount: 7,
  },
];

const FILTER_TABS: Array<{ label: string; value: WorkflowStatus | 'all' }> = [
  { label: 'All', value: 'all' },
  { label: 'Draft', value: 'draft' },
  { label: 'Staging', value: 'staging' },
  { label: 'Production', value: 'production' },
];

export default function WorkflowsPage() {
  const [activeFilter, setActiveFilter] = useState<WorkflowStatus | 'all'>('all');

  const filteredWorkflows =
    activeFilter === 'all'
      ? MOCK_WORKFLOWS
      : MOCK_WORKFLOWS.filter((wf) => wf.status === activeFilter);

  return (
    <AppShell>
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-bold text-txt-1">Workflows</h1>
          <p className="text-sm text-txt-2 mt-1">Design, test, and deploy agent workflows</p>
        </div>
        <button className="btn-primary">
          <Plus size={14} />
          Create Workflow
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-1.5 mb-5">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveFilter(tab.value)}
            className={cn(
              'badge border transition-colors duration-80',
              activeFilter === tab.value
                ? 'bg-elevated border-border-em text-txt-1'
                : 'border-border text-txt-3 hover:text-txt-2 hover:border-border-hover'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Workflow grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredWorkflows.map((wf) => (
          <Link
            key={wf.id}
            href={`/workflows/${wf.id}/edit`}
            className={cn(
              'bg-surface border border-border rounded-lg p-4',
              'hover:border-border-hover hover:bg-elevated/50',
              'transition-all duration-150 group block'
            )}
          >
            {/* Top row: name + status */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-display text-base font-semibold text-txt-1 group-hover:text-accent transition-colors">
                {wf.name}
              </h3>
              <span
                className={cn(
                  'badge border text-2xs flex-shrink-0',
                  STATUS_BADGE[wf.status]
                )}
              >
                {STATUS_LABEL[wf.status]}
              </span>
            </div>

            {/* Description */}
            <p className="text-xs text-txt-2 line-clamp-2 mb-4">{wf.description}</p>

            {/* Footer stats */}
            <div className="flex items-center gap-4 text-2xs text-txt-3">
              <span className="flex items-center gap-1">
                <Play size={10} />
                {wf.totalRuns.toLocaleString()} runs
              </span>
              <span className="flex items-center gap-1">
                <GitBranch size={10} />
                {wf.stepsCount} steps
              </span>
              {wf.avgCost > 0 && (
                <span className="font-mono">{formatCost(wf.avgCost)} avg</span>
              )}
              {wf.lastRunAt && (
                <span className="flex items-center gap-1 ml-auto">
                  <Clock size={10} />
                  {formatRelativeTime(wf.lastRunAt)}
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
