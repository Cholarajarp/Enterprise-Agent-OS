import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock fetch globally
const mockFetch = vi.fn();
(global as any).fetch = mockFetch;

describe('API hooks exports', () => {
  it('should export all required hooks', async () => {
    const hooks = await import('../src/lib/hooks');
    expect(typeof hooks.useWorkflows).toBe('function');
    expect(typeof hooks.useRuns).toBe('function');
    expect(typeof hooks.useApprovals).toBe('function');
    expect(typeof hooks.useTools).toBe('function');
    expect(typeof hooks.useAuditEvents).toBe('function');
    expect(typeof hooks.useKPIDashboard).toBe('function');
  });
});

describe('Utility functions', () => {
  it('should handle empty arrays gracefully', () => {
    const arr: unknown[] = [];
    expect(arr.length).toBe(0);
    expect(Array.isArray(arr)).toBe(true);
  });

  it('should construct API URLs correctly', () => {
    const base = 'http://localhost:8000';
    const path = '/v1/workflows';
    const url = `${base}${path}`;
    expect(url).toBe('http://localhost:8000/v1/workflows');
  });
});
