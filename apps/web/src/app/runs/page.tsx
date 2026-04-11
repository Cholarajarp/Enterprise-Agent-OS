'use client';

import { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { RunsTable } from '@/components/runs/RunsTable';
import { RunDrawer } from '@/components/runs/RunDrawer';
import { cn } from '@/lib/utils';
import { Calendar, Filter, RotateCcw, ChevronDown } from 'lucide-react';

const WORKFLOW_OPTIONS = [
  'All Workflows',
  'IT Incident Triage',
  'Deploy Rollback',
  'Knowledge Sync',
  'Ticket Enrichment',
  'Cost Anomaly Detection',
  'Compliance Check',
];

export default function RunsPage() {
  const [selectedWorkflow, setSelectedWorkflow] = useState('All Workflows');
  const [dateFrom, setDateFrom] = useState('2026-04-04');
  const [dateTo, setDateTo] = useState('2026-04-11');
  const [showWorkflowDropdown, setShowWorkflowDropdown] = useState(false);

  return (
    <AppShell>
      {/* Page header */}
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-txt-1">Runs</h1>
        <p className="text-sm text-txt-2 mt-1">
          Complete history of all workflow executions
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-3 mb-5">
        {/* Date range picker */}
        <div className="flex items-center gap-2">
          <Calendar size={14} className="text-txt-3" />
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="input text-xs w-36"
          />
          <span className="text-txt-3 text-xs">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="input text-xs w-36"
          />
        </div>

        <div className="h-5 w-px bg-border" />

        {/* Workflow filter dropdown */}
        <div className="relative">
          <button
            className="btn-secondary text-xs flex items-center gap-1.5"
            onClick={() => setShowWorkflowDropdown(!showWorkflowDropdown)}
          >
            <Filter size={12} />
            {selectedWorkflow}
            <ChevronDown size={10} />
          </button>

          {showWorkflowDropdown && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowWorkflowDropdown(false)}
              />
              <div className="absolute top-full left-0 mt-1 z-20 w-56 bg-elevated border border-border rounded-lg shadow-xl py-1">
                {WORKFLOW_OPTIONS.map((wf) => (
                  <button
                    key={wf}
                    className={cn(
                      'w-full text-left px-3 py-1.5 text-xs transition-colors',
                      selectedWorkflow === wf
                        ? 'text-txt-1 bg-surface'
                        : 'text-txt-2 hover:text-txt-1 hover:bg-surface'
                    )}
                    onClick={() => {
                      setSelectedWorkflow(wf);
                      setShowWorkflowDropdown(false);
                    }}
                  >
                    {wf}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="flex-1" />

        <button className="btn-ghost text-xs">
          <RotateCcw size={12} />
          Refresh
        </button>
      </div>

      {/* Runs table (reused component) */}
      <RunsTable />

      {/* Run detail drawer (reused component) */}
      <RunDrawer />
    </AppShell>
  );
}
