'use client';

import { AppShell } from '@/components/layout/AppShell';
import { cn, formatRelativeTime } from '@/lib/utils';
import { Shield, UserCog, Users, KeyRound } from 'lucide-react';

const MEMBERS = [
  {
    name: 'John Doe',
    role: 'Platform Admin',
    auth: 'Okta SSO + WebAuthn',
    lastActive: '2026-04-11T10:20:00Z',
  },
  {
    name: 'Priya Nair',
    role: 'Automation Reviewer',
    auth: 'Azure AD + TOTP',
    lastActive: '2026-04-11T09:42:00Z',
  },
  {
    name: 'Ethan Brooks',
    role: 'Incident Commander',
    auth: 'Google SSO + WebAuthn',
    lastActive: '2026-04-10T21:15:00Z',
  },
];

export default function TeamSettingsPage() {
  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-txt-1">Team & Access</h1>
          <p className="mt-1 text-sm text-txt-2">
            SSO-backed identities, reviewer roles, and admin separation of duties.
          </p>
        </div>
        <button className="btn-primary">
          <Users size={14} />
          Invite Member
        </button>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-2 flex items-center gap-2 text-accent">
            <Shield size={15} />
            <span className="text-xs font-medium uppercase tracking-widest">SSO</span>
          </div>
          <p className="font-display text-2xl font-bold text-txt-1">Required</p>
          <p className="mt-1 text-xs text-txt-3">Okta, Azure AD, and Google OIDC are enabled.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-2 flex items-center gap-2 text-success">
            <KeyRound size={15} />
            <span className="text-xs font-medium uppercase tracking-widest">MFA</span>
          </div>
          <p className="font-display text-2xl font-bold text-txt-1">100%</p>
          <p className="mt-1 text-xs text-txt-3">All human users have a second factor enrolled.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-2 flex items-center gap-2 text-warning">
            <UserCog size={15} />
            <span className="text-xs font-medium uppercase tracking-widest">Review Pool</span>
          </div>
          <p className="font-display text-2xl font-bold text-txt-1">3</p>
          <p className="mt-1 text-xs text-txt-3">Primary approvers for destructive or high-cost actions.</p>
        </div>
      </div>

      <section className="rounded-lg border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <h2 className="font-display text-lg font-semibold text-txt-1">Active Members</h2>
        </div>
        <div className="divide-y divide-border-sub">
          {MEMBERS.map((member) => (
            <div key={member.name} className="grid grid-cols-[1.1fr_1fr_1fr_140px] gap-3 px-4 py-4">
              <div>
                <p className="text-sm font-medium text-txt-1">{member.name}</p>
                <p className="text-xs text-txt-3">{member.role}</p>
              </div>
              <div className="text-xs text-txt-2">{member.auth}</div>
              <div>
                <span
                  className={cn(
                    'badge border border-success/20 bg-success/10 text-success'
                  )}
                >
                  Reviewer eligible
                </span>
              </div>
              <div className="text-right text-xs text-txt-3">
                {formatRelativeTime(member.lastActive)}
              </div>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
