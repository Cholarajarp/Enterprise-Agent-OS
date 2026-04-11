'use client';

import { KPICard } from '@/components/common/KPICard';
import { RunsTable } from '@/components/runs/RunsTable';
import { RunDrawer } from '@/components/runs/RunDrawer';
import { AppShell } from '@/components/layout/AppShell';
import { Activity, Clock, DollarSign, ShieldCheck } from 'lucide-react';

const SPARKLINE_RUNS = [12, 18, 15, 22, 28, 24, 31, 27, 35, 32, 38, 42];
const SPARKLINE_CYCLE = [450, 380, 420, 310, 290, 340, 280, 250, 220, 230, 210, 195];
const SPARKLINE_COST = [12, 15, 18, 14, 22, 19, 25, 21, 28, 24, 30, 27];
const SPARKLINE_APPROVALS = [8, 5, 7, 3, 6, 4, 2, 5, 3, 4, 2, 3];

export default function DashboardPage() {
  return (
    <AppShell>
      {/* Page header */}
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-txt-1">Dashboard</h1>
        <p className="text-sm text-txt-2 mt-1">Real-time overview of your agent operations</p>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPICard
          label="Active Runs"
          value="42"
          change={{ value: 18, label: 'vs last week' }}
          sparklineData={SPARKLINE_RUNS}
        />
        <KPICard
          label="Avg Cycle Time"
          value="3.2m"
          change={{ value: -24, label: 'vs last week' }}
          sparklineData={SPARKLINE_CYCLE}
        />
        <KPICard
          label="Cost Today"
          value="$27.84"
          change={{ value: 12, label: 'vs yesterday' }}
          sparklineData={SPARKLINE_COST}
        />
        <KPICard
          label="Pending Approvals"
          value="3"
          change={{ value: -40, label: 'vs last week' }}
          sparklineData={SPARKLINE_APPROVALS}
        />
      </div>

      {/* Recent Runs */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display text-lg font-semibold text-txt-1">Recent Runs</h2>
          <button className="btn-ghost text-xs">View all runs →</button>
        </div>
        <RunsTable />
      </div>

      {/* Run Detail Drawer */}
      <RunDrawer />
    </AppShell>
  );
}
