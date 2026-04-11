'use client';

import { AppShell } from '@/components/layout/AppShell';
import { cn, formatRelativeTime } from '@/lib/utils';
import { KeyRound, RotateCcw, ShieldCheck } from 'lucide-react';

const KEYS = [
  {
    name: 'svc-incident-runtime',
    scopes: ['runs:write', 'approvals:read', 'audit:read'],
    lastUsed: '2026-04-11T10:21:00Z',
    status: 'active',
  },
  {
    name: 'svc-knowledge-sync',
    scopes: ['knowledge:write', 'tools:read'],
    lastUsed: '2026-04-11T09:54:00Z',
    status: 'active',
  },
  {
    name: 'legacy-reporting-export',
    scopes: ['audit:read'],
    lastUsed: '2026-03-28T18:11:00Z',
    status: 'rotation_due',
  },
];

export default function ApiKeysPage() {
  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-txt-1">API Keys</h1>
          <p className="mt-1 text-sm text-txt-2">
            Scoped service credentials with rotation hygiene and immutable usage visibility.
          </p>
        </div>
        <button className="btn-primary">
          <KeyRound size={14} />
          Create Service Key
        </button>
      </div>

      <section className="rounded-lg border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <h2 className="font-display text-lg font-semibold text-txt-1">Issued Credentials</h2>
        </div>
        <div className="divide-y divide-border-sub">
          {KEYS.map((key) => (
            <div key={key.name} className="grid grid-cols-[1fr_1.3fr_140px_160px] gap-3 px-4 py-4">
              <div>
                <p className="font-mono text-sm text-txt-1">{key.name}</p>
                <p className="text-xs text-txt-3">Displayed once at creation, then redacted</p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {key.scopes.map((scope) => (
                  <span
                    key={scope}
                    className="badge border border-accent/20 bg-accent/10 font-mono text-accent"
                  >
                    {scope}
                  </span>
                ))}
              </div>
              <div
                className={cn(
                  'text-xs font-medium',
                  key.status === 'active' ? 'text-success' : 'text-warning'
                )}
              >
                {key.status === 'active' ? 'Healthy rotation window' : 'Rotation due'}
              </div>
              <div className="flex items-center justify-end gap-2">
                <span className="text-xs text-txt-3">{formatRelativeTime(key.lastUsed)}</span>
                <button className="btn-secondary text-xs">
                  <RotateCcw size={12} />
                  Rotate
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-4 flex items-center gap-2 text-xs text-success">
        <ShieldCheck size={12} />
        Keys are org-scoped, rotatable, and never shown again after creation.
      </div>
    </AppShell>
  );
}
