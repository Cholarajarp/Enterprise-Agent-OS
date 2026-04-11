'use client';

import { AppShell } from '@/components/layout/AppShell';
import { KPICard } from '@/components/common/KPICard';
import { AlertTriangle, CreditCard, Wallet } from 'lucide-react';

const DAILY_COST = [8, 11, 10, 14, 16, 15, 21, 19, 24, 26, 28, 31];
const TOKEN_USAGE = [120, 140, 155, 162, 190, 214, 238, 244, 260, 281, 295, 314];
const AUTO_RESOLUTION = [24, 28, 31, 29, 33, 35, 38, 41, 40, 43, 45, 48];

export default function BillingSettingsPage() {
  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-txt-1">Billing & Budgets</h1>
          <p className="mt-1 text-sm text-txt-2">
            Spend controls, remaining budget, and workflow cost efficiency.
          </p>
        </div>
        <button className="btn-primary">
          <Wallet size={14} />
          Adjust Budget Guardrail
        </button>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <KPICard
          label="Cost This Month"
          value="$8,472"
          change={{ value: 12, label: 'vs previous period' }}
          sparklineData={DAILY_COST}
        />
        <KPICard
          label="Token Usage"
          value="314K"
          change={{ value: 8, label: 'vs yesterday' }}
          sparklineData={TOKEN_USAGE}
        />
        <KPICard
          label="Auto-Resolution Rate"
          value="48%"
          change={{ value: 11, label: 'vs baseline' }}
          sparklineData={AUTO_RESOLUTION}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-4 flex items-center gap-2 text-warning">
            <AlertTriangle size={14} />
            <span className="text-xs font-medium uppercase tracking-widest">Budget Status</span>
          </div>
          <div className="mb-3 flex items-end justify-between">
            <div>
              <p className="font-display text-3xl font-bold text-txt-1">$1,528</p>
              <p className="text-xs text-txt-3">remaining of $10,000 monthly budget</p>
            </div>
            <span className="badge border border-warning/20 bg-warning/10 text-warning">
              84.7% consumed
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-void">
            <div className="h-full w-[84.7%] rounded-full bg-warning" />
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3 text-xs text-txt-2">
            <div className="rounded-md border border-border-sub bg-void p-3">
              <p className="text-txt-3">Per-run hard cap</p>
              <p className="mt-1 font-mono text-sm text-txt-1">$25.00</p>
            </div>
            <div className="rounded-md border border-border-sub bg-void p-3">
              <p className="text-txt-3">Alert threshold</p>
              <p className="mt-1 font-mono text-sm text-txt-1">80%</p>
            </div>
            <div className="rounded-md border border-border-sub bg-void p-3">
              <p className="text-txt-3">Billing plan</p>
              <p className="mt-1 font-mono text-sm text-txt-1">Enterprise</p>
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-4 flex items-center gap-2 text-accent">
            <CreditCard size={14} />
            <span className="text-xs font-medium uppercase tracking-widest">Cost Controls</span>
          </div>
          <div className="space-y-3 text-sm text-txt-2">
            <div className="rounded-md border border-border-sub bg-void p-3">
              Pre-flight estimation blocks new runs when projected spend crosses monthly remaining budget.
            </div>
            <div className="rounded-md border border-border-sub bg-void p-3">
              Tool registry call costs are rolled into run ledgers alongside model and compute spend.
            </div>
            <div className="rounded-md border border-border-sub bg-void p-3">
              Cost anomalies page reviewers before production promotion when projected ROI drops below threshold.
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
