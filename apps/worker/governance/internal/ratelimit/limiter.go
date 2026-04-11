// Package ratelimit provides per-agent, per-tool, per-org rate limiting
// using Redis sliding window counters.
package ratelimit

import (
	"context"
	"fmt"
	"time"
)

// Limiter enforces rate limits using sliding window counters.
type Limiter struct {
	store CounterStore
}

// CounterStore is the interface for rate limit counter storage.
type CounterStore interface {
	// Increment atomically increments the counter for the key
	// and returns the new count and TTL remaining.
	Increment(ctx context.Context, key string, window time.Duration) (count int64, err error)
}

// NewLimiter creates a rate limiter backed by the given store.
func NewLimiter(store CounterStore) *Limiter {
	return &Limiter{store: store}
}

// Check evaluates whether a request should be allowed.
// Returns nil if within limits, RateLimitError if exceeded.
func (l *Limiter) Check(ctx context.Context, key string, maxRequests int, windowSec int) error {
	window := time.Duration(windowSec) * time.Second
	count, err := l.store.Increment(ctx, key, window)
	if err != nil {
		return fmt.Errorf("ratelimit: counter error: %w", err)
	}

	if count > int64(maxRequests) {
		return &RateLimitError{
			Key:         key,
			Current:     count,
			MaxRequests: maxRequests,
			WindowSec:   windowSec,
		}
	}

	return nil
}

// BuildKey constructs a rate limit key from components.
// Format: ratelimit:{org_id}:{scope}:{identifier}
func BuildKey(orgID, scope, identifier string) string {
	return fmt.Sprintf("ratelimit:%s:%s:%s", orgID, scope, identifier)
}

// RateLimitError indicates a rate limit has been exceeded.
type RateLimitError struct {
	Key         string
	Current     int64
	MaxRequests int
	WindowSec   int
}

func (e *RateLimitError) Error() string {
	return fmt.Sprintf(
		"rate_limited: key %q at %d/%d requests in %ds window",
		e.Key, e.Current, e.MaxRequests, e.WindowSec,
	)
}
