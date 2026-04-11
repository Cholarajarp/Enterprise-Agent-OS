// Package audit provides an immutable, hash-chained audit log writer.
// Every event gets an ID, timestamp, payload hash, and a reference
// to the previous event's hash, forming a tamper-evident chain.
// Rows can never be updated or deleted.
package audit

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"

	"github.com/agent-os/governance-proxy/pkg/models"
)

// Writer writes immutable audit events to the append-only store.
type Writer struct {
	mu       sync.Mutex
	prevHash string
	store    Store
	logger   *slog.Logger
}

// Store is the persistence interface for audit events.
// Implementations must guarantee append-only semantics.
type Store interface {
	// Append writes an audit event. Must be idempotent on event ID.
	Append(ctx context.Context, event *models.AuditEvent) error
	// LastHash returns the hash of the most recent event for an org.
	LastHash(ctx context.Context, orgID string) (string, error)
}

// NewWriter creates an audit writer backed by the given store.
func NewWriter(store Store, logger *slog.Logger) *Writer {
	return &Writer{
		store:    store,
		prevHash: "genesis",
		logger:   logger,
	}
}

// Write creates and persists an immutable audit event.
// The event is hash-chained to the previous event for tamper detection.
func (w *Writer) Write(ctx context.Context, event *models.AuditEvent) error {
	w.mu.Lock()
	defer w.mu.Unlock()

	// Generate event ID (UUIDv7 for time-sortability)
	eventID, err := uuid.NewV7()
	if err != nil {
		return fmt.Errorf("audit: generate event id: %w", err)
	}
	event.ID = eventID.String()
	event.CreatedAt = time.Now().UTC()

	// Compute payload hash
	payloadBytes, err := json.Marshal(event.Payload)
	if err != nil {
		return fmt.Errorf("audit: marshal payload: %w", err)
	}
	event.PayloadHash = computeSHA256(payloadBytes)

	// Chain to previous hash for tamper evidence
	event.PrevHash = w.prevHash
	chainInput := w.prevHash + event.PayloadHash
	newHash := computeSHA256([]byte(chainInput))

	// Write to store
	if err := w.store.Append(ctx, event); err != nil {
		return fmt.Errorf("audit: append event: %w", err)
	}

	// Update chain state
	w.prevHash = newHash

	w.logger.InfoContext(ctx, "audit event written",
		slog.String("event_id", event.ID),
		slog.String("event_type", event.EventType),
		slog.String("decision", string(event.Decision)),
		slog.String("org_id", event.OrgID),
		slog.String("run_id", event.RunID),
		slog.Int64("latency_ms", event.LatencyMs),
	)

	return nil
}

// ValidateChain verifies the hash chain integrity for an organization.
// Returns nil if the chain is valid, error with the first broken link.
func (w *Writer) ValidateChain(events []*models.AuditEvent) error {
	if len(events) == 0 {
		return nil
	}

	prevHash := "genesis"
	for i, event := range events {
		// Verify the event's prev_hash matches our running chain
		if event.PrevHash != prevHash {
			return fmt.Errorf(
				"audit: chain broken at event %d (id=%s): expected prev_hash %q, got %q",
				i, event.ID, prevHash, event.PrevHash,
			)
		}

		// Recompute and advance
		chainInput := prevHash + event.PayloadHash
		prevHash = computeSHA256([]byte(chainInput))
	}

	return nil
}

func computeSHA256(data []byte) string {
	h := sha256.Sum256(data)
	return hex.EncodeToString(h[:])
}
