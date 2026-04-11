// In-memory implementations for audit store and rate limiter.
// Production replacements: PostgreSQL (audit) and Redis (rate limits).
package main

import (
	"context"
	"sync"
	"time"

	"github.com/agent-os/governance-proxy/pkg/models"
)

// MemoryAuditStore is an in-memory append-only audit event store.
// Replace with PostgreSQL in production.
type MemoryAuditStore struct {
	mu     sync.RWMutex
	events []*models.AuditEvent
}

func NewMemoryAuditStore() *MemoryAuditStore {
	return &MemoryAuditStore{
		events: make([]*models.AuditEvent, 0, 10000),
	}
}

func (s *MemoryAuditStore) Append(ctx context.Context, event *models.AuditEvent) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, event)
	return nil
}

func (s *MemoryAuditStore) LastHash(ctx context.Context, orgID string) (string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for i := len(s.events) - 1; i >= 0; i-- {
		if s.events[i].OrgID == orgID {
			return s.events[i].PayloadHash, nil
		}
	}
	return "genesis", nil
}

// MemoryRateLimitStore is an in-memory sliding window counter.
// Replace with Redis in production.
type MemoryRateLimitStore struct {
	mu       sync.Mutex
	counters map[string]*windowCounter
}

type windowCounter struct {
	count     int64
	expiresAt time.Time
}

func NewMemoryRateLimitStore() *MemoryRateLimitStore {
	return &MemoryRateLimitStore{
		counters: make(map[string]*windowCounter),
	}
}

func (s *MemoryRateLimitStore) Increment(ctx context.Context, key string, window time.Duration) (int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	counter, exists := s.counters[key]
	if !exists || now.After(counter.expiresAt) {
		s.counters[key] = &windowCounter{
			count:     1,
			expiresAt: now.Add(window),
		}
		return 1, nil
	}

	counter.count++
	return counter.count, nil
}
