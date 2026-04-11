'use client';

import { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { StatusDot } from '@/components/common/StatusDot';
import { cn, formatCost } from '@/lib/utils';
import { Plus, Search, Clock, RotateCcw, Shield } from 'lucide-react';
import { useTools } from '@/lib/hooks';
import type { Tool } from '@/lib/hooks';

export default function ToolsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const { tools, loading, error } = useTools();

  const filteredTools = tools.filter(
    (tool) =>
      tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <AppShell>
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-bold text-txt-1">Tool Registry</h1>
          <p className="text-sm text-txt-2 mt-1">
            Registered tools and integrations available to agents
          </p>
        </div>
        <button className="btn-primary">
          <Plus size={14} />
          Register Tool
        </button>
      </div>

      {/* Search bar */}
      <div className="relative mb-5">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-txt-3"
        />
        <input
          type="text"
          placeholder="Search tools by name or description..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="input w-full pl-9"
        />
      </div>

      {/* Loading state */}
      {loading && (
        <div className="text-sm text-txt-3 py-12 text-center">Loading tools...</div>
      )}

      {/* Error state — graceful */}
      {error && !loading && tools.length === 0 && (
        <div className="text-sm text-txt-3 py-12 text-center">
          Unable to load tools. Check that the API is running.
        </div>
      )}

      {/* Tool grid */}
      {!loading && (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredTools.map((tool) => (
          <div
            key={tool.id}
            className={cn(
              'bg-surface border border-border rounded-lg p-4',
              'hover:border-border-hover hover:bg-elevated/50',
              'transition-all duration-150'
            )}
          >
            {/* Name + version */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-mono text-sm font-semibold text-txt-1">
                {tool.name}
              </h3>
              <span className="badge bg-elevated text-txt-3 border border-border text-2xs flex-shrink-0">
                v{tool.version}
              </span>
            </div>

            {/* Description */}
            <p className="text-xs text-txt-2 line-clamp-2 mb-3">{tool.description}</p>

            {/* Health status */}
            <div className="flex items-center gap-2 mb-3">
              <StatusDot status={tool.health} showLabel={false} />
              <span
                className={cn(
                  'text-xs',
                  tool.health === 'completed' && 'text-success',
                  tool.health === 'running' && 'text-warning',
                  tool.health === 'failed' && 'text-danger'
                )}
              >
                {tool.healthLabel}
              </span>
              <div className="flex-1" />
              <span className="text-2xs text-txt-3">
                {tool.callsToday.toLocaleString()} calls today
              </span>
            </div>

            {/* Scopes */}
            <div className="flex items-center flex-wrap gap-1 mb-3">
              {tool.scopes.map((scope) => (
                <span
                  key={scope}
                  className="badge bg-accent/10 text-accent border border-accent/20 text-2xs font-mono"
                >
                  {scope}
                </span>
              ))}
            </div>

            {/* Cost */}
            <div className="mb-3">
              <span className="text-2xs text-txt-3">Cost per call: </span>
              <span className="font-mono text-xs text-txt-1">
                {formatCost(tool.costPerCall)}
              </span>
            </div>

            {/* Footer: timeout + retry */}
            <div className="flex items-center gap-4 pt-3 border-t border-border-sub text-2xs text-txt-3">
              <span className="flex items-center gap-1">
                <Clock size={10} />
                {tool.timeoutMs >= 1000
                  ? `${tool.timeoutMs / 1000}s timeout`
                  : `${tool.timeoutMs}ms timeout`}
              </span>
              <span className="flex items-center gap-1">
                <RotateCcw size={10} />
                {tool.retryPolicy}
              </span>
            </div>
          </div>
        ))}
      </div>
      )}
    </AppShell>
  );
}
