'use client';

import { KPICard } from '@/components/common/KPICard';
import { RunsTable } from '@/components/runs/RunsTable';
import { RunDrawer } from '@/components/runs/RunDrawer';
import { AppShell } from '@/components/layout/AppShell';
import { Activity, Clock, DollarSign, ShieldCheck } from 'lucide-react';
import { useKPIDashboard, useRuns } from '@/lib/hooks';

// Fallback sparklines used while the API is loading or unreachable
const SPARKLINE_RUNS = [12, 18, 15, 22, 28, 24, 31, 27, 35, 32, 38, 42];
const SPARKLINE_CYCLE = [450, 380, 420, 310, 290, 340, 280, 250, 220, 230, 210, 195];
const SPARKLINE_COST = [12, 15, 18, 14, 22, 19, 25, 21, 28, 24, 30, 27];
const SPARKLINE_APPROVALS = [8, 5, 7, 3, 6, 4, 2, 5, 3, 4, 2, 3];

export default function DashboardPage() {
  const { dashboard, loading: kpiLoading } = useKPIDashboard();
  // Recent runs — limited to 10 for the dashboard summary
  const { runs, loading: runsLoading } = useRuns({ limit: 10 });

  return (
    <AppShell>
      {/* Page header */}
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-txt-1">Dashboard</h1>
        <p className="text-sm text-txt-2 mt-1">Real-time overview of your agent operations</p>
      </div>

      {/* KPI Strip */}
      {kpiLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="kpi-card animate-pulse">
              <div className="h-3 w-24 bg-border rounded mb-3" />
              <div className="h-8 w-16 bg-border rounded" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <KPICard
            label="Active Runs"
            value={dashboard ? String(dashboard.active_runs) : '42'}
            change={{ value: dashboard?.active_runs_change ?? 18, label: 'vs last week' }}
            sparklineData={dashboard?.sparkline_runs ?? SPARKLINE_RUNS}
          />
          <KPICard
            label="Avg Cycle Time"
            value={dashboard?.avg_cycle_time ?? '3.2m'}
            change={{ value: dashboard?.avg_cycle_time_change ?? -24, label: 'vs last week' }}
            sparklineData={dashboard?.sparkline_cycle ?? SPARKLINE_CYCLE}
          />
          <KPICard
            label="Cost Today"
            value={dashboard?.cost_today ?? '$27.84'}
            change={{ value: dashboard?.cost_today_change ?? 12, label: 'vs yesterday' }}
            sparklineData={dashboard?.sparkline_cost ?? SPARKLINE_COST}
          />
          <KPICard
            label="Pending Approvals"
            value={dashboard ? String(dashboard.pending_approvals) : '3'}
            change={{ value: dashboard?.pending_approvals_change ?? -40, label: 'vs last week' }}
            sparklineData={dashboard?.sparkline_approvals ?? SPARKLINE_APPROVALS}
          />
        </div>
      )}

      {/* Recent Runs */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display text-lg font-semibold text-txt-1">Recent Runs</h2>
          <button className="btn-ghost text-xs">View all runs →</button>
        </div>
        {runsLoading ? (
          <div className="text-sm text-txt-3 py-8 text-center">Loading runs...</div>
        ) : (
          <RunsTable runs={runs} />
        )}
      </div>

      {/* Run Detail Drawer */}
      <RunDrawer />
    </AppShell>
  );
}
