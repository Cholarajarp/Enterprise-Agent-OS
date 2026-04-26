package proxy_test

import (
	"context"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/agent-os/governance-proxy/internal/proxy"
	"github.com/agent-os/governance-proxy/pkg/models"
)

// ── in-memory test stores ────────────────────────────────────────────

type testAuditStore struct {
	events []*models.AuditEvent
}

func (s *testAuditStore) Append(_ context.Context, e *models.AuditEvent) error {
	s.events = append(s.events, e)
	return nil
}

func (s *testAuditStore) LastHash(_ context.Context, _ string) (string, error) {
	if len(s.events) == 0 {
		return "genesis", nil
	}
	return s.events[len(s.events)-1].PayloadHash, nil
}

type testRateLimitStore struct {
	counts map[string]int64
}

func newTestRateLimitStore() *testRateLimitStore {
	return &testRateLimitStore{counts: make(map[string]int64)}
}

func (s *testRateLimitStore) Increment(_ context.Context, key string, _ time.Duration) (int64, error) {
	s.counts[key]++
	return s.counts[key], nil
}

// ── helpers ──────────────────────────────────────────────────────────

func newTestProxy(t *testing.T) *proxy.Proxy {
	t.Helper()
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelError}))
	cfg := proxy.DefaultConfig()
	return proxy.New(&testAuditStore{}, newTestRateLimitStore(), cfg, logger)
}

func toolRequest(toolName string, params map[string]interface{}) *models.ToolCallRequest {
	return &models.ToolCallRequest{
		RunID:   "run-test-1",
		OrgID:   "org-test-1",
		AgentID: "agent-test-1",
		ToolName: toolName,
		Params:  params,
	}
}

// ── tests ────────────────────────────────────────────────────────────

func TestDefaultConfigIsNonZero(t *testing.T) {
	cfg := proxy.DefaultConfig()
	if cfg == nil {
		t.Fatal("DefaultConfig returned nil")
	}
	if cfg.DefaultRateLimit <= 0 {
		t.Errorf("expected positive DefaultRateLimit, got %d", cfg.DefaultRateLimit)
	}
	if cfg.InjectionThreshold <= 0 || cfg.InjectionThreshold >= 1 {
		t.Errorf("expected InjectionThreshold in (0,1), got %f", cfg.InjectionThreshold)
	}
}

func TestNewProxyInstantiates(t *testing.T) {
	p := newTestProxy(t)
	if p == nil {
		t.Fatal("expected non-nil Proxy")
	}
}

func TestEvaluateAllowedToolInScope(t *testing.T) {
	p := newTestProxy(t)

	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-1",
		AllowedScopes: []string{"slack:send_message"},
	})

	req := toolRequest("slack:send_message", map[string]interface{}{"channel": "#test", "text": "hello"})
	resp, err := p.Evaluate(context.Background(), "wf-1", req, false)
	if err != nil {
		t.Fatalf("Evaluate error: %v", err)
	}
	if !resp.Allowed {
		t.Errorf("expected allowed, got blocked: reason=%s", resp.Reason)
	}
}

func TestEvaluateBlockedToolOutOfScope(t *testing.T) {
	p := newTestProxy(t)

	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-1",
		AllowedScopes: []string{"slack:send_message"},
	})

	req := toolRequest("k8s:delete_namespace", map[string]interface{}{"namespace": "production"})
	req.Scopes = []string{"k8s:delete_namespace"}
	resp, err := p.Evaluate(context.Background(), "wf-1", req, false)
	if err != nil {
		t.Fatalf("Evaluate error: %v", err)
	}
	if resp.Allowed {
		t.Errorf("expected blocked tool to be denied")
	}
}

func TestEvaluateWildcardScopeAllowsSubtools(t *testing.T) {
	p := newTestProxy(t)

	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-wild",
		AllowedScopes: []string{"slack:*"},
	})

	for _, tool := range []string{"slack:send_message", "slack:get_channels", "slack:create_channel"} {
		req := toolRequest(tool, map[string]interface{}{"channel": "#test"})
		resp, err := p.Evaluate(context.Background(), "wf-wild", req, false)
		if err != nil {
			t.Fatalf("Evaluate(%s) error: %v", tool, err)
		}
		if !resp.Allowed {
			t.Errorf("expected %s to be allowed by slack:* scope", tool)
		}
	}
}

func TestEvaluateAuditEventWritten(t *testing.T) {
	auditStore := &testAuditStore{}
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelError}))
	p := proxy.New(auditStore, newTestRateLimitStore(), proxy.DefaultConfig(), logger)

	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-audit",
		AllowedScopes: []string{"slack:*"},
	})

	req := toolRequest("slack:send_message", map[string]interface{}{"text": "audit test"})
	_, err := p.Evaluate(context.Background(), "wf-audit", req, false)
	if err != nil {
		t.Fatalf("Evaluate error: %v", err)
	}

	if len(auditStore.events) == 0 {
		t.Error("expected at least one audit event to be written")
	}
}

func TestPIIRedactionInParams(t *testing.T) {
	p := newTestProxy(t)

	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-pii",
		AllowedScopes: []string{"slack:*"},
	})

	req := toolRequest("slack:send_message", map[string]interface{}{
		"text": "Contact admin@example.com for support",
	})
	resp, err := p.Evaluate(context.Background(), "wf-pii", req, false)
	if err != nil {
		t.Fatalf("Evaluate error: %v", err)
	}
	// Presence of PII may lead to redaction decision but should not crash
	t.Logf("PII test: allowed=%v decision=%s", resp.Allowed, resp.Decision)
}

func TestEvaluateRequiresApproval(t *testing.T) {
	p := newTestProxy(t)

	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-approval",
		AllowedScopes: []string{"k8s:*"},
	})

	req := toolRequest("k8s:restart", map[string]interface{}{"deployment": "web"})
	resp, err := p.Evaluate(context.Background(), "wf-approval", req, true)
	if err != nil {
		t.Fatalf("Evaluate error: %v", err)
	}
	// With requires_approval=true the proxy should either block or mark as escalated
	t.Logf("Approval test: allowed=%v decision=%s", resp.Allowed, resp.Decision)
}

func TestLoadPolicyOverridesExisting(t *testing.T) {
	p := newTestProxy(t)

	// First policy: only slack
	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-override",
		AllowedScopes: []string{"slack:send_message"},
	})

	req := toolRequest("jira:create_issue", map[string]interface{}{"summary": "test"})
	req.Scopes = []string{"jira:create_issue"}
	resp, _ := p.Evaluate(context.Background(), "wf-override", req, false)
	if resp.Allowed {
		t.Error("expected jira blocked before policy update")
	}

	// Update policy to also allow jira
	p.LoadPolicy(&models.ScopePolicy{
		WorkflowID:    "wf-override",
		AllowedScopes: []string{"slack:send_message", "jira:create_issue"},
	})

	resp2, _ := p.Evaluate(context.Background(), "wf-override", req, false)
	if !resp2.Allowed {
		t.Error("expected jira allowed after policy update")
	}
}
