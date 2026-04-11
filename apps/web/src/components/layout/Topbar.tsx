'use client';

import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useCommandPaletteStore, useSidebarStore } from '@/stores/ui';
import { Search, Bell, ChevronRight } from 'lucide-react';

const BREADCRUMB_MAP: Record<string, string> = {
  '/': 'Dashboard',
  '/workflows': 'Workflows',
  '/runs': 'Runs',
  '/approvals': 'Approvals',
  '/tools': 'Tools',
  '/knowledge': 'Knowledge',
  '/governance': 'Governance',
  '/settings/team': 'Team',
  '/settings/billing': 'Billing',
  '/settings/api-keys': 'API Keys',
};

function EnvironmentBadge({ env }: { env: 'production' | 'staging' | 'development' }) {
  const styles = {
    production: 'bg-danger/10 text-danger border-danger/20',
    staging: 'bg-warning/10 text-warning border-warning/20',
    development: 'bg-txt-3/10 text-txt-3 border-txt-3/20',
  };

  return (
    <span className={cn('badge border', styles[env])}>
      {env.toUpperCase()}
    </span>
  );
}

export function Topbar() {
  const pathname = usePathname();
  const { collapsed } = useSidebarStore();
  const { setOpen: openPalette } = useCommandPaletteStore();
  const currentPage = pathname.includes('/workflows/') && pathname.endsWith('/edit')
    ? 'Workflow Editor'
    : BREADCRUMB_MAP[pathname] || pathname.split('/').pop() || '';

  return (
    <header
      className={cn(
        'fixed top-0 right-0 z-30 h-13 bg-base/80 backdrop-blur-sm',
        'border-b border-border-sub flex items-center px-4 gap-4',
        'transition-[left] duration-200',
        collapsed ? 'left-[52px]' : 'left-55'
      )}
    >
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-sm min-w-0">
        <span className="text-txt-3">Agent OS</span>
        <ChevronRight size={12} className="text-txt-3" />
        <span className="text-txt-1 font-medium truncate">{currentPage}</span>
      </div>

      {/* Search */}
      <button
        onClick={() => openPalette(true)}
        className={cn(
          'flex items-center gap-2 mx-auto',
          'h-8 w-full max-w-md px-3',
          'bg-surface border border-border rounded-md',
          'text-sm text-txt-4 hover:border-border-hover',
          'transition-colors duration-80'
        )}
      >
        <Search size={14} />
        <span className="flex-1 text-left">Search workflows, runs, tools...</span>
        <kbd className="hidden sm:inline-flex h-5 items-center gap-0.5 rounded border border-border-em bg-elevated px-1.5 font-mono text-2xs text-txt-3">
          <span>⌘</span>K
        </kbd>
      </button>

      {/* Right section */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <EnvironmentBadge env="production" />

        <button
          className="relative p-1.5 text-txt-3 hover:text-txt-2 transition-colors"
          aria-label="Notifications"
        >
          <Bell size={16} />
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-accent rounded-full flex items-center justify-center animate-scale-in">
            <span className="text-[9px] font-bold text-white">3</span>
          </span>
        </button>
      </div>
    </header>
  );
}
