'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useSidebarStore } from '@/stores/ui';
import {
  LayoutDashboard,
  Workflow,
  Play,
  ShieldCheck,
  Wrench,
  Database,
  Shield,
  Users,
  CreditCard,
  Key,
  ChevronLeft,
  ChevronRight,
  Settings,
} from 'lucide-react';

const NAV_GROUPS = [
  {
    label: 'WORKSPACE',
    items: [
      { href: '/', icon: LayoutDashboard, label: 'Dashboard' },
      { href: '/workflows', icon: Workflow, label: 'Workflows' },
      { href: '/runs', icon: Play, label: 'Runs' },
      { href: '/approvals', icon: ShieldCheck, label: 'Approvals' },
    ],
  },
  {
    label: 'SYSTEM',
    items: [
      { href: '/tools', icon: Wrench, label: 'Tools' },
      { href: '/knowledge', icon: Database, label: 'Knowledge' },
      { href: '/governance', icon: Shield, label: 'Governance' },
    ],
  },
  {
    label: 'SETTINGS',
    items: [
      { href: '/settings/team', icon: Users, label: 'Team' },
      { href: '/settings/billing', icon: CreditCard, label: 'Billing' },
      { href: '/settings/api-keys', icon: Key, label: 'API Keys' },
    ],
  },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggle } = useSidebarStore();

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen bg-base border-r border-border-sub',
        'flex flex-col transition-[width] duration-200',
        collapsed ? 'w-[52px]' : 'w-55'
      )}
    >
      {/* Logo */}
      <div className={cn(
        'flex items-center h-13 px-3 border-b border-border-sub',
        collapsed ? 'justify-center' : 'gap-3'
      )}>
        <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center flex-shrink-0">
          <span className="font-mono text-xs font-bold text-white">AO</span>
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="font-display text-sm font-semibold text-txt-1 truncate">
              Agent OS
            </p>
            <p className="text-2xs text-txt-3 truncate">Acme Corp</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-4">
            {!collapsed && (
              <p className="px-3 mb-1 text-2xs font-medium tracking-widest text-txt-3 uppercase">
                {group.label}
              </p>
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = item.href === '/'
                  ? pathname === '/'
                  : pathname.startsWith(item.href);
                const Icon = item.icon;

                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        isActive ? 'nav-item-active' : 'nav-item',
                        collapsed && 'justify-center px-0'
                      )}
                      title={collapsed ? item.label : undefined}
                    >
                      <Icon size={16} className="flex-shrink-0" />
                      {!collapsed && <span>{item.label}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border-sub p-2">
        {!collapsed && (
          <div className="flex items-center gap-2 px-3 py-2 mb-1">
            <div className="w-6 h-6 rounded-full bg-elevated flex items-center justify-center">
              <span className="text-2xs font-medium text-txt-2">JD</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-txt-1 truncate">John Doe</p>
            </div>
            <button
              className="p-1 text-txt-3 hover:text-txt-2 transition-colors"
              aria-label="Settings"
            >
              <Settings size={14} />
            </button>
          </div>
        )}
        <button
          onClick={toggle}
          className={cn(
            'flex items-center justify-center w-full h-7 rounded-md',
            'text-txt-3 hover:text-txt-2 hover:bg-surface transition-colors duration-80'
          )}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
    </aside>
  );
}
