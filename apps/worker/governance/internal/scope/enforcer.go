// Package scope enforces tool scope policies.
// Every tool call is checked against the workflow's allowed scope list.
// Any call outside the allowlist is rejected with an audit event.
package scope

import (
	"context"
	"fmt"
	"strings"

	"github.com/agent-os/governance-proxy/pkg/models"
)

// Enforcer checks tool calls against scope policies.
type Enforcer struct {
	policies map[string]*models.ScopePolicy
}

// NewEnforcer creates a scope enforcer with the given policies.
func NewEnforcer() *Enforcer {
	return &Enforcer{
		policies: make(map[string]*models.ScopePolicy),
	}
}

// LoadPolicy registers a scope policy for a workflow.
func (e *Enforcer) LoadPolicy(policy *models.ScopePolicy) {
	e.policies[policy.WorkflowID] = policy
}

// Check evaluates whether a tool call is within the workflow's allowed scopes.
// Returns nil if allowed, error with details if blocked.
func (e *Enforcer) Check(ctx context.Context, workflowID string, req *models.ToolCallRequest) error {
	policy, exists := e.policies[workflowID]
	if !exists {
		return fmt.Errorf("scope_violation: no policy found for workflow %s", workflowID)
	}

	for _, requiredScope := range req.Scopes {
		if !e.scopeAllowed(policy.AllowedScopes, requiredScope) {
			return &ScopeViolation{
				WorkflowID:    workflowID,
				ToolName:      req.ToolName,
				RequiredScope: requiredScope,
				AllowedScopes: policy.AllowedScopes,
			}
		}
	}

	return nil
}

// scopeAllowed checks if a required scope matches any allowed scope.
// Supports hierarchical matching: "jira:read" matches "jira:read" or "jira:*".
func (e *Enforcer) scopeAllowed(allowed []string, required string) bool {
	for _, a := range allowed {
		if a == required {
			return true
		}
		// Wildcard match: "jira:*" matches "jira:read"
		if strings.HasSuffix(a, ":*") {
			prefix := strings.TrimSuffix(a, "*")
			if strings.HasPrefix(required, prefix) {
				return true
			}
		}
	}
	return false
}

// ScopeViolation represents an unauthorized tool scope access attempt.
type ScopeViolation struct {
	WorkflowID    string
	ToolName      string
	RequiredScope string
	AllowedScopes []string
}

func (v *ScopeViolation) Error() string {
	return fmt.Sprintf(
		"scope_violation: tool %q requires scope %q, workflow %s allows %v",
		v.ToolName, v.RequiredScope, v.WorkflowID, v.AllowedScopes,
	)
}
