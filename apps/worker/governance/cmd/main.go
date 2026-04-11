// Governance Proxy — the moat of Enterprise Agent OS.
//
// Every tool call, memory read, and external API request from every agent
// passes through this service before execution. It provides:
//
//   - Tool scope enforcement (allowlist per workflow)
//   - PII detection and redaction
//   - Prompt injection detection
//   - Immutable hash-chained audit log
//   - Rate limiting per agent/tool/org
//   - Human approval gate management
//
// This is a high-throughput, low-latency proxy. Target: <5ms p99 overhead.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/agent-os/governance-proxy/internal/proxy"
	"github.com/agent-os/governance-proxy/pkg/models"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))

	cfg := proxy.DefaultConfig()

	// In production, these would be backed by PostgreSQL and Redis.
	// Using in-memory implementations for the initial build.
	auditStore := NewMemoryAuditStore()
	rateLimitStore := NewMemoryRateLimitStore()

	gov := proxy.New(auditStore, rateLimitStore, cfg, logger)

	mux := http.NewServeMux()

	// Health check
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
	})

	// Main evaluation endpoint
	mux.HandleFunc("POST /v1/evaluate", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			WorkflowID       string                 `json:"workflow_id"`
			RequiresApproval bool                   `json:"requires_approval"`
			Request          models.ToolCallRequest `json:"request"`
		}

		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeError(w, http.StatusBadRequest, "invalid_request", err.Error())
			return
		}

		resp, err := gov.Evaluate(r.Context(), body.WorkflowID, &body.Request, body.RequiresApproval)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "evaluation_error", err.Error())
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	// Load scope policy
	mux.HandleFunc("POST /v1/policies", func(w http.ResponseWriter, r *http.Request) {
		var policy models.ScopePolicy
		if err := json.NewDecoder(r.Body).Decode(&policy); err != nil {
			writeError(w, http.StatusBadRequest, "invalid_policy", err.Error())
			return
		}

		gov.LoadPolicy(&policy)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(map[string]string{"status": "loaded"})
	})

	addr := envOrDefault("GOVERNANCE_PROXY_ADDR", ":8090")
	srv := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// Graceful shutdown
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh

		logger.Info("shutting down governance proxy")
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		srv.Shutdown(ctx)
	}()

	logger.Info("governance proxy starting", slog.String("addr", addr))
	if err := srv.ListenAndServe(); err != http.ErrServerClosed {
		logger.Error("server error", slog.String("error", err.Error()))
		os.Exit(1)
	}
}

func writeError(w http.ResponseWriter, status int, code, detail string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"type":       fmt.Sprintf("https://api.agentruntime.io/errors/%s", code),
		"title":      code,
		"status":     status,
		"detail":     detail,
		"error_code": code,
	})
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
