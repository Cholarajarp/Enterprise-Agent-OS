// Package models defines the core data types for the governance proxy.
// Every tool call, memory read, and external API request passes through
// the governance layer before execution.
package models

import (
	"time"
)

// ToolCallRequest represents an agent's request to invoke a tool.
type ToolCallRequest struct {
	ID          string                 `json:"id"`
	RunID       string                 `json:"run_id"`
	OrgID       string                 `json:"org_id"`
	AgentID     string                 `json:"agent_id"`
	ToolName    string                 `json:"tool_name"`
	ToolVersion string                 `json:"tool_version"`
	Params      map[string]interface{} `json:"params"`
	Scopes      []string               `json:"scopes"`
	Timestamp   time.Time              `json:"timestamp"`
}

// ToolCallResponse is the governance proxy's decision on a tool call.
type ToolCallResponse struct {
	Allowed      bool                   `json:"allowed"`
	Decision     Decision               `json:"decision"`
	Reason       string                 `json:"reason"`
	RedactedData map[string]interface{} `json:"redacted_data,omitempty"`
	AuditEventID string                 `json:"audit_event_id"`
	LatencyMs    int64                  `json:"latency_ms"`
}

// Decision represents the governance decision outcome.
type Decision string

const (
	DecisionAllowed   Decision = "allowed"
	DecisionBlocked   Decision = "blocked"
	DecisionRedacted  Decision = "redacted"
	DecisionEscalated Decision = "escalated"
)

// AuditEvent is an immutable record of a governance-evaluated event.
// Once written, it can never be updated or deleted.
type AuditEvent struct {
	ID          string    `json:"id"`
	OrgID       string    `json:"org_id"`
	RunID       string    `json:"run_id"`
	AgentID     string    `json:"agent_id"`
	EventType   string    `json:"event_type"`
	ActorType   string    `json:"actor_type"`
	ActorID     string    `json:"actor_id"`
	PayloadHash string    `json:"payload_hash"`
	Payload     string    `json:"payload"`
	Decision    Decision  `json:"decision"`
	PrevHash    string    `json:"prev_hash"`
	LatencyMs   int64     `json:"latency_ms"`
	CreatedAt   time.Time `json:"created_at"`
}

// ScopePolicy defines the allowed tool scopes for a workflow.
type ScopePolicy struct {
	WorkflowID    string   `json:"workflow_id"`
	AllowedScopes []string `json:"allowed_scopes"`
}

// ApprovalRequest is created when an agent action requires human review.
type ApprovalRequest struct {
	ID           string                 `json:"id"`
	OrgID        string                 `json:"org_id"`
	RunID        string                 `json:"run_id"`
	StepID       string                 `json:"step_id"`
	WorkflowID   string                 `json:"workflow_id"`
	Payload      map[string]interface{} `json:"payload"`
	Context      map[string]interface{} `json:"context,omitempty"`
	RequiredRole string                 `json:"required_role"`
	SLADeadline  time.Time              `json:"sla_deadline"`
	Status       string                 `json:"status"`
	CreatedAt    time.Time              `json:"created_at"`
}

// InjectionClassification is the result of the prompt injection detector.
type InjectionClassification struct {
	IsSafe     bool    `json:"is_safe"`
	Confidence float64 `json:"confidence"`
	Category   string  `json:"category,omitempty"`
}

// PIIDetection represents a detected PII occurrence in data.
type PIIDetection struct {
	Type     string `json:"type"`
	Value    string `json:"value"`
	Redacted string `json:"redacted"`
	Start    int    `json:"start"`
	End      int    `json:"end"`
}

// RateLimitConfig defines rate limits per agent/tool/org.
type RateLimitConfig struct {
	Key         string `json:"key"`
	MaxRequests int    `json:"max_requests"`
	WindowSec   int    `json:"window_sec"`
}
