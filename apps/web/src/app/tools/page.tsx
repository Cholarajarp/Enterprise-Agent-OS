'use client';

import { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { StatusDot } from '@/components/common/StatusDot';
import { cn, formatCost } from '@/lib/utils';
import { Plus, Search, Clock, RotateCcw, Shield } from 'lucide-react';

type ToolHealth = 'running' | 'completed' | 'failed';

interface Tool {
  id: string;
  name: string;
  version: string;
  description: string;
  health: ToolHealth;
  healthLabel: string;
  scopes: string[];
  costPerCall: number;
  timeoutMs: number;
  retryPolicy: string;
  callsToday: number;
}

const MOCK_TOOLS: Tool[] = [
  {
    id: 'tool-001',
    name: 'jira:cloud',
    version: '2.4.1',
    description:
      'Create, update, search, and transition Jira issues. Supports custom fields, JQL queries, and bulk operations.',
    health: 'completed',
    healthLabel: 'Healthy',
    scopes: ['issues:read', 'issues:write', 'projects:read'],
    costPerCall: 0.0003,
    timeoutMs: 15000,
    retryPolicy: '3x exponential',
    callsToday: 847,
  },
  {
    id: 'tool-002',
    name: 'pagerduty:v2',
    version: '1.8.0',
    description:
      'Manage PagerDuty incidents, services, and on-call schedules. Trigger, acknowledge, and resolve incidents programmatically.',
    health: 'completed',
    healthLabel: 'Healthy',
    scopes: ['incidents:read', 'incidents:write', 'services:read'],
    costPerCall: 0.0005,
    timeoutMs: 10000,
    retryPolicy: '3x exponential',
    callsToday: 234,
  },
  {
    id: 'tool-003',
    name: 'slack:web-api',
    version: '3.1.2',
    description:
      'Send messages, create channels, manage threads, and post rich block kit messages to Slack workspaces.',
    health: 'completed',
    healthLabel: 'Healthy',
    scopes: ['chat:write', 'channels:read', 'users:read'],
    costPerCall: 0.0001,
    timeoutMs: 8000,
    retryPolicy: '2x linear',
    callsToday: 1523,
  },
  {
    id: 'tool-004',
    name: 'datadog:api',
    version: '2.0.3',
    description:
      'Query metrics, create monitors, search logs, and manage dashboards via Datadog API. Supports custom metric queries.',
    health: 'completed',
    healthLabel: 'Healthy',
    scopes: ['metrics:read', 'monitors:write', 'logs:read'],
    costPerCall: 0.0008,
    timeoutMs: 20000,
    retryPolicy: '3x exponential',
    callsToday: 412,
  },
  {
    id: 'tool-005',
    name: 'github:rest',
    version: '4.2.0',
    description:
      'Interact with GitHub repositories, pull requests, issues, actions, and deployments. Supports both REST and GraphQL.',
    health: 'running',
    healthLabel: 'Degraded',
    scopes: ['repo:read', 'repo:write', 'actions:read', 'deployments:write'],
    costPerCall: 0.0004,
    timeoutMs: 12000,
    retryPolicy: '3x exponential',
    callsToday: 678,
  },
  {
    id: 'tool-006',
    name: 'kubernetes:api',
    version: '1.5.1',
    description:
      'Manage Kubernetes resources including deployments, pods, services, and config maps. Supports rollbacks and scaling.',
    health: 'completed',
    healthLabel: 'Healthy',
    scopes: ['deployments:read', 'deployments:write', 'pods:read', 'pods:exec'],
    costPerCall: 0.0012,
    timeoutMs: 30000,
    retryPolicy: '2x exponential',
    callsToday: 156,
  },
  {
    id: 'tool-007',
    name: 'postgresql:query',
    version: '1.2.0',
    description:
      'Execute read-only SQL queries against PostgreSQL databases. Supports parameterized queries and result pagination.',
    health: 'failed',
    healthLabel: 'Unreachable',
    scopes: ['db:read'],
    costPerCall: 0.0002,
    timeoutMs: 10000,
    retryPolicy: '3x exponential',
    callsToday: 0,
  },
  {
    id: 'tool-008',
    name: 'http:generic',
    version: '1.0.0',
    description:
      'Make arbitrary HTTP requests to allowlisted endpoints. Supports GET, POST, PUT, PATCH, DELETE with custom headers and body.',
    health: 'completed',
    healthLabel: 'Healthy',
    scopes: ['http:request'],
    costPerCall: 0.0001,
    timeoutMs: 15000,
    retryPolicy: '2x linear',
    callsToday: 2341,
  },
];

export default function ToolsPage() {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredTools = MOCK_TOOLS.filter(
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

      {/* Tool grid */}
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
    </AppShell>
  );
}
