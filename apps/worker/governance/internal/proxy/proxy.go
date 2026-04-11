// Package proxy implements the core Governance Proxy.
// Every tool call, memory read, and external API request passes through
// this proxy before execution. It enforces scope policies, detects PII,
// checks for prompt injection, enforces rate limits, manages approval gates,
// and writes immutable audit events for every decision.
package proxy

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/agent-os/governance-proxy/internal/audit"
	"github.com/agent-os/governance-proxy/internal/injection"
	"github.com/agent-os/governance-proxy/internal/pii"
	"github.com/agent-os/governance-proxy/internal/ratelimit"
	"github.com/agent-os/governance-proxy/internal/scope"
	"github.com/agent-os/governance-proxy/pkg/models"
)

// Proxy is the central governance enforcement layer.
// All agent operations flow through Evaluate before execution.
type Proxy struct {
	scope       *scope.Enforcer
	pii         *pii.Detector
	injection   *injection.Detector
	rateLimiter *ratelimit.Limiter
	auditWriter *audit.Writer
	logger      *slog.Logger
}

// Config holds configuration for the governance proxy.
type Config struct {
	InjectionThreshold float64
	DefaultRateLimit   int
	DefaultRateWindow  int
}

// DefaultConfig returns the default governance proxy configuration.
func DefaultConfig() *Config {
	return &Config{
		InjectionThreshold: 0.6,
		DefaultRateLimit:   100,
		DefaultRateWindow:  60,
	}
}

// New creates a new Governance Proxy with all subsystems.
func New(
	auditStore audit.Store,
	rateLimitStore ratelimit.CounterStore,
	cfg *Config,
	logger *slog.Logger,
) *Proxy {
	if cfg == nil {
		cfg = DefaultConfig()
	}

	return &Proxy{
		scope:       scope.NewEnforcer(),
		pii:         pii.NewDetector(),
		injection:   injection.NewDetector(cfg.InjectionThreshold),
		rateLimiter: ratelimit.NewLimiter(rateLimitStore),
		auditWriter: audit.NewWriter(auditStore, logger),
		logger:      logger,
	}
}

// LoadPolicy registers a scope policy for a workflow.
func (p *Proxy) LoadPolicy(policy *models.ScopePolicy) {
	p.scope.LoadPolicy(policy)
}

// Evaluate runs the full governance pipeline on a tool call request.
// Pipeline order:
//  1. Rate limit check
//  2. Scope enforcement
//  3. Prompt injection detection (on params)
//  4. PII detection and redaction
//  5. Approval gate check
//  6. Audit event emission
//
// Returns the decision with latency tracking.
func (p *Proxy) Evaluate(ctx context.Context, workflowID string, req *models.ToolCallRequest, requiresApproval bool) (*models.ToolCallResponse, error) {
	start := time.Now()

	// ─── 1. Rate Limit ──────────────────────────────────
	rlKey := ratelimit.BuildKey(req.OrgID, "tool", req.AgentID)
	if err := p.rateLimiter.Check(ctx, rlKey, 100, 60); err != nil {
		latency := time.Since(start).Milliseconds()
		p.emitAudit(ctx, req, "tool_call", models.DecisionBlocked, latency, "rate_limited")
		return &models.ToolCallResponse{
			Allowed:      false,
			Decision:     models.DecisionBlocked,
			Reason:       err.Error(),
			AuditEventID: "",
			LatencyMs:    latency,
		}, nil
	}

	// ─── 2. Scope Enforcement ───────────────────────────
	if err := p.scope.Check(ctx, workflowID, req); err != nil {
		latency := time.Since(start).Milliseconds()
		p.emitAudit(ctx, req, "scope_violation", models.DecisionBlocked, latency, err.Error())
		return &models.ToolCallResponse{
			Allowed:      false,
			Decision:     models.DecisionBlocked,
			Reason:       err.Error(),
			AuditEventID: "",
			LatencyMs:    latency,
		}, nil
	}

	// ─── 3. Injection Detection ─────────────────────────
	// Check all string values in params for injection attempts
	paramsJSON, _ := json.Marshal(req.Params)
	classification := p.injection.Classify(ctx, string(paramsJSON))
	if p.injection.IsBlocked(classification) {
		latency := time.Since(start).Milliseconds()
		p.emitAudit(ctx, req, "injection_detected", models.DecisionBlocked, latency,
			fmt.Sprintf("confidence=%.2f category=%s", classification.Confidence, classification.Category))
		return &models.ToolCallResponse{
			Allowed:      false,
			Decision:     models.DecisionBlocked,
			Reason:       "injection_detected: input classified as potential prompt injection",
			AuditEventID: "",
			LatencyMs:    latency,
		}, nil
	}

	// ─── 4. PII Detection & Redaction ───────────────────
	redactedParams, piiDetections := p.pii.RedactMap(req.Params)
	decision := models.DecisionAllowed
	if len(piiDetections) > 0 {
		decision = models.DecisionRedacted
		p.logger.WarnContext(ctx, "pii detected and redacted",
			slog.String("run_id", req.RunID),
			slog.Int("detections", len(piiDetections)),
		)
	}

	// ─── 5. Approval Gate ───────────────────────────────
	if requiresApproval {
		latency := time.Since(start).Milliseconds()
		p.emitAudit(ctx, req, "approval_requested", models.DecisionEscalated, latency, "requires_approval")
		return &models.ToolCallResponse{
			Allowed:      false,
			Decision:     models.DecisionEscalated,
			Reason:       "approval_required: action requires human review",
			RedactedData: redactedParams,
			AuditEventID: "",
			LatencyMs:    latency,
		}, nil
	}

	// ─── 6. Emit Audit Event (allowed) ──────────────────
	latency := time.Since(start).Milliseconds()
	auditID := p.emitAudit(ctx, req, "tool_call", decision, latency, "")

	return &models.ToolCallResponse{
		Allowed:      true,
		Decision:     decision,
		Reason:       "",
		RedactedData: redactedParams,
		AuditEventID: auditID,
		LatencyMs:    latency,
	}, nil
}

// emitAudit writes an immutable audit event and returns its ID.
func (p *Proxy) emitAudit(ctx context.Context, req *models.ToolCallRequest, eventType string, decision models.Decision, latencyMs int64, detail string) string {
	payload := map[string]interface{}{
		"tool_name": req.ToolName,
		"params":    "redacted",
		"detail":    detail,
	}
	payloadJSON, _ := json.Marshal(payload)

	event := &models.AuditEvent{
		OrgID:     req.OrgID,
		RunID:     req.RunID,
		AgentID:   req.AgentID,
		EventType: eventType,
		ActorType: "agent",
		ActorID:   req.AgentID,
		Payload:   string(payloadJSON),
		Decision:  decision,
		LatencyMs: latencyMs,
	}

	if err := p.auditWriter.Write(ctx, event); err != nil {
		p.logger.ErrorContext(ctx, "failed to write audit event",
			slog.String("event_type", eventType),
			slog.String("error", err.Error()),
		)
		return ""
	}

	return event.ID
}
