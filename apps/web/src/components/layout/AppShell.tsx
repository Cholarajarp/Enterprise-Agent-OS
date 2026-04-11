'use client';

import { cn } from '@/lib/utils';
import { useSidebarStore } from '@/stores/ui';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette } from './CommandPalette';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebarStore();

  return (
    <div className="min-h-screen bg-void">
      <Sidebar />
      <Topbar />
      <CommandPalette />
      <main
        className={cn(
          'pt-13 min-h-screen transition-[padding-left] duration-200',
          collapsed ? 'pl-[52px]' : 'pl-55'
        )}
      >
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
