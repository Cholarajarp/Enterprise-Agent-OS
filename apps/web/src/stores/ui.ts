import { create } from 'zustand';

interface SidebarState {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (v: boolean) => void;
}

export const useSidebarStore = create<SidebarState>((set) => ({
  collapsed: false,
  toggle: () => set((s) => ({ collapsed: !s.collapsed })),
  setCollapsed: (collapsed) => set({ collapsed }),
}));

interface CommandPaletteState {
  open: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
}

export const useCommandPaletteStore = create<CommandPaletteState>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  toggle: () => set((s) => ({ open: !s.open })),
}));

interface RunDrawerState {
  runId: string | null;
  open: (runId: string) => void;
  close: () => void;
}

export const useRunDrawerStore = create<RunDrawerState>((set) => ({
  runId: null,
  open: (runId) => set({ runId }),
  close: () => set({ runId: null }),
}));
