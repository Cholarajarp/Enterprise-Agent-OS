// Governance Proxy — the moat of Enterprise Agent OS.
//
// Every tool call, memory read, and external API request from every agent
// passes through this service before execution.
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

	// Use persistent stores if DATABASE_URL is set
	var auditStore interface {
		Append(ctx context.Context, event *models.AuditEvent) error
		LastHash(ctx context.Context, orgID string) (string, error)
	}
	var rateLimitStore interface {
		Increment(ctx context.Context, key string, window time.Duration) (int64, error)
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL != "" {
		pool, err := initPgPool(context.Background(), dbURL)
		if err != nil {
			logger.Warn("falling back to in-memory audit store", slog.String("error", err.Error()))
			auditStore = NewMemoryAuditStore()
		} else {
			logger.Info("connected to PostgreSQL for audit storage")
			auditStore = NewPgAuditStore(pool)
		}
	} else {
		auditStore = NewMemoryAuditStore()
	}

	redisURL := os.Getenv("REDIS_URL")
	if redisURL != "" {
		rateLimitStore = NewRedisRateLimitStore(redisURL)
		logger.Info("rate limit store initialized", slog.String("backend", "redis-wrapped"))
	} else {
		rateLimitStore = NewMemoryRateLimitStore()
	}

	gov := proxy.New(auditStore, rateLimitStore, cfg, logger)

	mux := http.NewServeMux()

	// Health check
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status":  "healthy",
			"version": "0.2.0",
		})
	})

	// Evaluate endpoint — returns governance decision without executing
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

	// Execute endpoint — evaluate + proxy to tool if allowed
	mux.HandleFunc("POST /v1/execute", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			WorkflowID       string                 `json:"workflow_id"`
			RequiresApproval bool                   `json:"requires_approval"`
			Request          models.ToolCallRequest `json:"request"`
		}

		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeError(w, http.StatusBadRequest, "invalid_request", err.Error())
			return
		}

		// Step 1: governance evaluation
		resp, err := gov.Evaluate(r.Context(), body.WorkflowID, &body.Request, body.RequiresApproval)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "evaluation_error", err.Error())
			return
		}

		// Step 2: if allowed, return with execution marker
		if resp.Allowed {
			result := map[string]interface{}{
				"governance":     resp,
				"execution":      "delegated",
				"tool_name":      body.Request.ToolName,
				"params":         resp.RedactedData,
				"execution_note": "Tool execution delegated to orchestrator tool fabric",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(result)
			return
		}

		// Not allowed — return governance response as-is
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	// Batch evaluate endpoint
	mux.HandleFunc("POST /v1/evaluate/batch", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			WorkflowID string `json:"workflow_id"`
			Requests   []struct {
				RequiresApproval bool                   `json:"requires_approval"`
				Request          models.ToolCallRequest `json:"request"`
			} `json:"requests"`
		}

		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeError(w, http.StatusBadRequest, "invalid_request", err.Error())
			return
		}

		results := make([]*models.ToolCallResponse, 0, len(body.Requests))
		for _, req := range body.Requests {
			resp, err := gov.Evaluate(r.Context(), body.WorkflowID, &req.Request, req.RequiresApproval)
			if err != nil {
				writeError(w, http.StatusInternalServerError, "evaluation_error", err.Error())
				return
			}
			results = append(results, resp)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"results": results,
			"count":   len(results),
		})
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

	// Metrics endpoint
	mux.HandleFunc("GET /v1/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status":  "operational",
			"version": "0.2.0",
		})
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

	logger.Info("governance proxy starting", slog.String("addr", addr), slog.String("version", "0.2.0"))
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
