'use client';

import { useEffect, useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useCommandPaletteStore } from '@/stores/ui';
import {
  Search,
  ArrowRight,
  Workflow,
  Play,
  Wrench,
  Shield,
  Database,
  FolderKanban,
  Activity,
} from 'lucide-react';

const GROUPS = [
  {
    label: 'Navigation',
    items: [
      { icon: Activity, label: 'Dashboard', shortcut: 'G D', href: '/' },
      { icon: Workflow, label: 'Workflows', shortcut: 'G W', href: '/workflows' },
      { icon: Play, label: 'Runs', shortcut: 'G R', href: '/runs' },
      { icon: Shield, label: 'Approvals', shortcut: 'G A', href: '/approvals' },
      { icon: Wrench, label: 'Tools', shortcut: 'G T', href: '/tools' },
      { icon: Database, label: 'Knowledge', shortcut: 'G K', href: '/knowledge' },
    ],
  },
  {
    label: 'Recent Runs',
    items: [
      { icon: Play, label: 'INC-8842 triage', shortcut: 'R 1', href: '/runs' },
      { icon: Play, label: 'deploy-rollback-v2', shortcut: 'R 2', href: '/runs' },
      { icon: Play, label: 'knowledge-sync-daily', shortcut: 'R 3', href: '/runs' },
    ],
  },
  {
    label: 'Workflows',
    items: [
      {
        icon: FolderKanban,
        label: 'IT Incident Triage',
        shortcut: 'W 1',
        href: '/workflows/wf-001/edit',
      },
      {
        icon: FolderKanban,
        label: 'Deploy Rollback',
        shortcut: 'W 2',
        href: '/workflows/wf-002/edit',
      },
    ],
  },
  {
    label: 'Actions',
    items: [
      { icon: ArrowRight, label: 'Trigger workflow...', shortcut: 'T', href: '#trigger' },
      { icon: Shield, label: 'Review approvals', shortcut: 'R', href: '/approvals' },
    ],
  },
];

export function CommandPalette() {
  const router = useRouter();
  const { open, setOpen } = useCommandPaletteStore();
  const [query, setQuery] = useState('');

  const filteredGroups = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return GROUPS;
    }

    return GROUPS.map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        item.label.toLowerCase().includes(normalized)
      ),
    })).filter((group) => group.items.length > 0);
  }, [query]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === 'Escape') setOpen(false);
    },
    [open, setOpen]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] animate-fade-in"
      onClick={() => setOpen(false)}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-void/80 backdrop-blur-sm" />

      {/* Modal */}
      <div
        className={cn(
          'relative w-full max-w-[600px] mx-4',
          'bg-overlay border border-border-em rounded-xl shadow-2xl',
          'animate-scale-in overflow-hidden'
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className="flex items-center gap-3 px-4 h-12 border-b border-border">
          <Search size={16} className="text-txt-3 flex-shrink-0" />
          <input
            autoFocus
            type="text"
            placeholder="Type a command or search..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="flex-1 bg-transparent text-sm text-txt-1 placeholder:text-txt-4 outline-none"
          />
          <kbd className="h-5 px-1.5 rounded border border-border-em bg-elevated font-mono text-2xs text-txt-3">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto p-2">
          {filteredGroups.map((group) => (
            <div key={group.label} className="mb-2">
              <p className="px-3 py-1.5 text-2xs font-medium tracking-widest text-txt-3 uppercase">
                {group.label}
              </p>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.label}
                    className={cn(
                      'flex items-center gap-3 w-full px-3 py-2 rounded-md',
                      'text-sm text-txt-2 hover:bg-elevated hover:text-txt-1',
                      'transition-colors duration-80'
                    )}
                    onClick={() => {
                      setOpen(false);
                      if (item.href && !item.href.startsWith('#')) {
                        router.push(item.href);
                      }
                    }}
                  >
                    <Icon size={16} className="flex-shrink-0" />
                    <span className="flex-1 text-left">{item.label}</span>
                    <kbd className="hidden sm:inline-flex h-5 items-center px-1.5 rounded border border-border-em bg-elevated font-mono text-2xs text-txt-3">
                      {item.shortcut}
                    </kbd>
                  </button>
                );
              })}
            </div>
          ))}
          {filteredGroups.length === 0 && (
            <div className="px-3 py-6 text-sm text-txt-3">
              No results for &quot;{query}&quot;.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
