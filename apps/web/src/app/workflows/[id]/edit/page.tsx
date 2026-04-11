'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AppShell } from '@/components/layout/AppShell';
import { useSidebarStore } from '@/stores/ui';
import { cn } from '@/lib/utils';
import {
  ArrowLeft,
  Save,
  Play,
  ArrowUpRight,
  Cpu,
  Wrench,
  ShieldCheck,
  GitBranch,
  Repeat,
  Bot,
  Shuffle,
  Clock,
  Bell,
  GripVertical,
} from 'lucide-react';

interface StepType {
  type: string;
  label: string;
  icon: typeof Cpu;
  color: string;
}

const STEP_PALETTE: StepType[] = [
  { type: 'llm_call', label: 'LLM Call', icon: Cpu, color: 'text-accent' },
  { type: 'tool_call', label: 'Tool Call', icon: Wrench, color: 'text-success' },
  { type: 'approval_gate', label: 'Approval Gate', icon: ShieldCheck, color: 'text-warning' },
  { type: 'branch', label: 'Branch', icon: GitBranch, color: 'text-purple' },
  { type: 'loop', label: 'Loop', icon: Repeat, color: 'text-cyan' },
  { type: 'sub_agent', label: 'Sub-Agent', icon: Bot, color: 'text-accent' },
  { type: 'transform', label: 'Transform', icon: Shuffle, color: 'text-teal' },
  { type: 'delay', label: 'Delay', icon: Clock, color: 'text-txt-2' },
  { type: 'notify', label: 'Notify', icon: Bell, color: 'text-warning' },
];

export default function WorkflowEditorPage() {
  const { collapsed } = useSidebarStore();
  const [workflowName, setWorkflowName] = useState('IT Incident Triage');

  return (
    <AppShell>
      {/* Override the default padding from AppShell by using negative margins */}
      <div className="-m-6 flex flex-col h-[calc(100vh-52px)]">
        {/* Top toolbar */}
        <div className="h-12 flex items-center gap-3 px-4 border-b border-border bg-surface flex-shrink-0">
          <Link
            href="/workflows"
            className="btn-ghost p-1.5"
            aria-label="Back to workflows"
          >
            <ArrowLeft size={16} />
          </Link>

          <div className="h-5 w-px bg-border" />

          <input
            type="text"
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            className="bg-transparent font-display text-sm font-semibold text-txt-1 border-none outline-none focus:ring-0 px-1 py-0.5 rounded hover:bg-elevated focus:bg-elevated transition-colors w-52"
          />

          <span className="badge bg-success/10 text-success border border-success/20 text-2xs">
            Production
          </span>

          <div className="flex-1" />

          <button className="btn-secondary text-xs">
            <Play size={12} />
            Dry Run
          </button>
          <button className="btn-primary text-xs">
            <Save size={12} />
            Save
          </button>
          <button className="btn-primary text-xs">
            <ArrowUpRight size={12} />
            Promote
          </button>
        </div>

        {/* Main editor area */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left panel — Step palette */}
          <div className="w-56 border-r border-border bg-surface flex-shrink-0 overflow-y-auto">
            <div className="p-3">
              <h3 className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-3">
                Step Types
              </h3>
              <div className="space-y-1">
                {STEP_PALETTE.map((step) => {
                  const Icon = step.icon;
                  return (
                    <div
                      key={step.type}
                      className={cn(
                        'flex items-center gap-2.5 px-2.5 py-2 rounded-md',
                        'border border-transparent',
                        'hover:bg-elevated hover:border-border cursor-grab',
                        'transition-all duration-80 group'
                      )}
                      draggable
                    >
                      <GripVertical
                        size={12}
                        className="text-txt-3 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                      />
                      <Icon size={14} className={cn('flex-shrink-0', step.color)} />
                      <span className="text-sm text-txt-2 group-hover:text-txt-1 transition-colors">
                        {step.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Center — Canvas area */}
          <div
            className={cn(
              'flex-1 relative overflow-auto',
              'bg-[radial-gradient(#1E1E2E_1px,transparent_1px)] bg-[size:20px_20px]'
            )}
          >
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <div className="w-16 h-16 rounded-xl bg-elevated border border-border-sub flex items-center justify-center mx-auto mb-4">
                  <GitBranch size={24} className="text-txt-3" />
                </div>
                <p className="text-sm text-txt-3 font-medium">
                  Drop steps here to build your workflow
                </p>
                <p className="text-xs text-txt-3/60 mt-1">
                  Drag step types from the left panel
                </p>
              </div>
            </div>
          </div>

          {/* Right panel — Properties */}
          <div className="w-80 border-l border-border bg-surface flex-shrink-0 overflow-y-auto">
            <div className="p-4">
              <h3 className="text-2xs font-medium tracking-widest text-txt-3 uppercase mb-3">
                Properties
              </h3>
              <div className="flex items-center justify-center h-48">
                <p className="text-sm text-txt-3">Select a step to configure</p>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom panel — Console */}
        <div className="h-32 border-t border-border bg-void flex-shrink-0 overflow-y-auto">
          <div className="flex items-center gap-2 px-4 py-1.5 border-b border-border-sub">
            <span className="text-2xs font-medium tracking-widest text-txt-3 uppercase">
              Console
            </span>
            <div className="flex-1" />
            <button className="text-2xs text-txt-3 hover:text-txt-2 transition-colors">
              Clear
            </button>
          </div>
          <div className="p-4">
            <p className="font-mono text-2xs text-txt-3">
              Ready. Run a dry-run to see output here.
            </p>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
