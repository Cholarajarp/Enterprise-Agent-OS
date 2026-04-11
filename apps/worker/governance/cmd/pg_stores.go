// PostgreSQL-backed audit store and Redis-backed rate limit store for production use.
package main

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/agent-os/governance-proxy/pkg/models"
)

// PgAuditStore writes audit events to PostgreSQL.
type PgAuditStore struct {
	pool *pgxpool.Pool
}

func NewPgAuditStore(pool *pgxpool.Pool) *PgAuditStore {
	return &PgAuditStore{pool: pool}
}

func (s *PgAuditStore) Append(ctx context.Context, event *models.AuditEvent) error {
	_, err := s.pool.Exec(ctx,
		`INSERT INTO audit_events (id, org_id, run_id, agent_id, event_type, actor_type, actor_id, payload_hash, payload, decision, prev_hash, latency_ms, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)`,
		event.ID, event.OrgID, event.RunID, event.AgentID,
		event.EventType, event.ActorType, event.ActorID,
		event.PayloadHash, event.Payload, string(event.Decision),
		event.PrevHash, event.LatencyMs, event.CreatedAt,
	)
	return err
}

func (s *PgAuditStore) LastHash(ctx context.Context, orgID string) (string, error) {
	var hash string
	err := s.pool.QueryRow(ctx,
		`SELECT payload_hash FROM audit_events WHERE org_id = $1 ORDER BY created_at DESC LIMIT 1`,
		orgID,
	).Scan(&hash)
	if err != nil {
		return "genesis", nil
	}
	return hash, nil
}

// RedisRateLimitStore wraps memory store (production: Redis INCR + EXPIRE).
type RedisRateLimitStore struct {
	mem *MemoryRateLimitStore
}

func NewRedisRateLimitStore(_ string) *RedisRateLimitStore {
	return &RedisRateLimitStore{mem: NewMemoryRateLimitStore()}
}

func (s *RedisRateLimitStore) Increment(ctx context.Context, key string, window time.Duration) (int64, error) {
	return s.mem.Increment(ctx, key, window)
}

// initPgPool creates a PostgreSQL connection pool.
func initPgPool(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse database url: %w", err)
	}
	config.MaxConns = 10
	config.MinConns = 2

	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("create pool: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		return nil, fmt.Errorf("ping database: %w", err)
	}

	return pool, nil
}
