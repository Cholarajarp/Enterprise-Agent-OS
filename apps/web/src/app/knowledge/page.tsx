'use client';

import { AppShell } from '@/components/layout/AppShell';
import { KPICard } from '@/components/common/KPICard';
import { cn, formatRelativeTime } from '@/lib/utils';
import { Database, FileStack, RefreshCw, ShieldCheck } from 'lucide-react';

const KPI_DOCS = [28, 31, 35, 34, 40, 42, 48, 47, 51, 56, 62, 64];
const KPI_LATENCY = [240, 225, 218, 230, 205, 198, 190, 186, 179, 184, 171, 168];
const KPI_JOBS = [4, 3, 5, 6, 4, 7, 5, 4, 6, 3, 4, 2];
const KPI_HIT_RATE = [61, 64, 67, 66, 69, 72, 74, 73, 77, 79, 81, 84];

const SOURCES = [
  {
    name: 'Confluence',
    domain: 'it-ops',
    status: 'Healthy',
    cadence: 'Webhook + hourly reconciliation',
    lastSync: '2026-04-11T10:22:00Z',
  },
  {
    name: 'PagerDuty Postmortems',
    domain: 'incident-history',
    status: 'Healthy',
    cadence: '15 minute polling',
    lastSync: '2026-04-11T10:18:00Z',
  },
  {
    name: 'CMDB',
    domain: 'service-topology',
    status: 'Lagging',
    cadence: 'Nightly full sync',
    lastSync: '2026-04-10T23:40:00Z',
  },
];

const JOBS = [
  {
    id: 'ing-1842',
    source: 'Confluence / On-call Runbooks',
    chunks: 1840,
    status: 'completed',
    updatedAt: '2026-04-11T10:20:00Z',
  },
  {
    id: 'ing-1841',
    source: 'CMDB / Service Inventory',
    chunks: 422,
    status: 'running',
    updatedAt: '2026-04-11T10:17:00Z',
  },
  {
    id: 'ing-1838',
    source: 'Incident Reviews / Q1',
    chunks: 760,
    status: 'completed',
    updatedAt: '2026-04-11T09:45:00Z',
  },
];

export default function KnowledgePage() {
  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-txt-1">Knowledge Fabric</h1>
          <p className="mt-1 text-sm text-txt-2">
            Org-scoped ingestion, retrieval quality, and memory freshness for governed runs.
          </p>
        </div>
        <button className="btn-primary">
          <RefreshCw size={14} />
          Trigger Ingestion
        </button>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label="Knowledge Chunks"
          value="64.2K"
          change={{ value: 14, label: 'vs yesterday' }}
          sparklineData={KPI_DOCS}
        />
        <KPICard
          label="Retrieval p95"
          value="168ms"
          change={{ value: -11, label: 'latency improvement' }}
          sparklineData={KPI_LATENCY}
        />
        <KPICard
          label="Active Jobs"
          value="2"
          change={{ value: -33, label: 'vs yesterday' }}
          sparklineData={KPI_JOBS}
        />
        <KPICard
          label="Runbook Hit Rate"
          value="84%"
          change={{ value: 9, label: 'vs last week' }}
          sparklineData={KPI_HIT_RATE}
        />
      </div>

      <div className="mb-6 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-lg border border-border bg-surface">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <h2 className="font-display text-lg font-semibold text-txt-1">Connected Sources</h2>
              <p className="text-xs text-txt-3">Scoped per org and domain</p>
            </div>
            <div className="badge border border-border-em bg-elevated text-txt-2">3 active</div>
          </div>
          <div className="divide-y divide-border-sub">
            {SOURCES.map((source) => (
              <div key={source.name} className="grid grid-cols-[1.4fr_1fr_1fr_1fr] gap-3 px-4 py-4">
                <div>
                  <p className="text-sm font-medium text-txt-1">{source.name}</p>
                  <p className="text-xs text-txt-3">{source.domain}</p>
                </div>
                <div className="text-xs text-txt-2">{source.cadence}</div>
                <div
                  className={cn(
                    'text-xs font-medium',
                    source.status === 'Healthy' ? 'text-success' : 'text-warning'
                  )}
                >
                  {source.status}
                </div>
                <div className="text-right text-xs text-txt-3">
                  {formatRelativeTime(source.lastSync)}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <div className="border-b border-border px-4 py-3">
            <h2 className="font-display text-lg font-semibold text-txt-1">Retrieval Guardrails</h2>
            <p className="text-xs text-txt-3">Isolation and quality controls enforced at query time</p>
          </div>
          <div className="space-y-3 p-4 text-sm text-txt-2">
            <div className="rounded-lg border border-border-sub bg-void px-3 py-3">
              <div className="mb-1 flex items-center gap-2 text-success">
                <ShieldCheck size={14} />
                Mandatory `org_id` filter
              </div>
              <p className="text-xs text-txt-3">
                Every episodic and vector retrieval path is namespaced before ranking.
              </p>
            </div>
            <div className="rounded-lg border border-border-sub bg-void px-3 py-3">
              <div className="mb-1 flex items-center gap-2 text-accent">
                <Database size={14} />
                Hybrid search enabled
              </div>
              <p className="text-xs text-txt-3">
                BM25 + vector retrieval with reciprocal rank fusion feeds the orchestrator context.
              </p>
            </div>
            <div className="rounded-lg border border-border-sub bg-void px-3 py-3">
              <div className="mb-1 flex items-center gap-2 text-warning">
                <FileStack size={14} />
                Cross-encoder re-rank
              </div>
              <p className="text-xs text-txt-3">
                Top results are re-ranked before prompt assembly to keep reasoning precise under tight token budgets.
              </p>
            </div>
          </div>
        </section>
      </div>

      <section className="rounded-lg border border-border bg-surface">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 className="font-display text-lg font-semibold text-txt-1">Ingestion Jobs</h2>
            <p className="text-xs text-txt-3">Recent indexing and refresh activity</p>
          </div>
          <button className="btn-secondary text-xs">View all jobs</button>
        </div>
        <div className="divide-y divide-border-sub">
          {JOBS.map((job) => (
            <div key={job.id} className="grid grid-cols-[120px_1fr_100px_120px] gap-3 px-4 py-4">
              <div className="font-mono text-xs text-txt-3">{job.id}</div>
              <div className="text-sm text-txt-1">{job.source}</div>
              <div className="text-xs text-txt-2">{job.chunks.toLocaleString()} chunks</div>
              <div
                className={cn(
                  'text-right text-xs font-medium',
                  job.status === 'completed' ? 'text-success' : 'text-accent'
                )}
              >
                {job.status} · {formatRelativeTime(job.updatedAt)}
              </div>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
