// Package injection implements prompt injection detection.
// Uses a two-tier approach: fast regex pre-filter + Claude Haiku classifier
// for accurate detection. All user-supplied data must pass through this
// layer before entering any agent prompt.
package injection

import (
	"context"
	"regexp"
	"strings"

	"github.com/agent-os/governance-proxy/pkg/models"
)

// Detector classifies input text for prompt injection attempts.
type Detector struct {
	threshold float64
	patterns  []*regexp.Regexp
}

// NewDetector creates an injection detector with the given confidence threshold.
// Default threshold from spec: 0.6
func NewDetector(threshold float64) *Detector {
	return &Detector{
		threshold: threshold,
		patterns: []*regexp.Regexp{
			// Direct instruction override attempts
			regexp.MustCompile(`(?i)ignore\s+(all\s+)?previous\s+instructions?`),
			regexp.MustCompile(`(?i)forget\s+(all\s+)?previous\s+(instructions?|context)`),
			regexp.MustCompile(`(?i)disregard\s+(all\s+)?(previous|prior|above)\s+`),
			regexp.MustCompile(`(?i)you\s+are\s+now\s+`),
			regexp.MustCompile(`(?i)act\s+as\s+(if\s+you\s+are\s+)?`),
			regexp.MustCompile(`(?i)pretend\s+(you\s+are|to\s+be)\s+`),
			regexp.MustCompile(`(?i)new\s+instructions?:\s*`),
			regexp.MustCompile(`(?i)system\s*:\s*`),
			regexp.MustCompile(`(?i)\[system\]`),
			regexp.MustCompile(`(?i)<\s*system\s*>`),

			// Delimiter injection
			regexp.MustCompile(`(?i)---\s*end\s+of\s+(system|user)\s+`),
			regexp.MustCompile(`(?i)===\s*new\s+prompt`),
			regexp.MustCompile(`(?i)\bEND_CONTEXT\b`),
			regexp.MustCompile(`(?i)\bBEGIN_INJECT\b`),

			// Tool/capability manipulation
			regexp.MustCompile(`(?i)execute\s+(?:this\s+)?(?:shell|bash|command|code)`),
			regexp.MustCompile(`(?i)call\s+(?:the\s+)?(?:function|tool|api)\s+`),
			regexp.MustCompile(`(?i)run\s+(?:the\s+)?(?:following|this)\s+(?:code|command)`),

			// Exfiltration attempts
			regexp.MustCompile(`(?i)send\s+(?:the\s+)?(?:data|information|results?)\s+to\s+`),
			regexp.MustCompile(`(?i)include\s+(?:the\s+)?(?:secret|password|key|token)\s+in`),
			regexp.MustCompile(`(?i)(?:base64|encode|encrypt)\s+(?:the\s+)?(?:key|secret|token)`),
		},
	}
}

// Classify runs the fast regex pre-filter on the input text.
// Returns a classification result. For inputs that match regex patterns,
// confidence is set to 0.8 (above default threshold).
// In production, this should be followed by a Claude Haiku call for
// borderline cases (confidence between 0.4 and 0.8).
func (d *Detector) Classify(ctx context.Context, text string) *models.InjectionClassification {
	normalized := strings.TrimSpace(text)
	if normalized == "" {
		return &models.InjectionClassification{
			IsSafe:     true,
			Confidence: 1.0,
		}
	}

	// Fast regex pre-filter
	for _, pattern := range d.patterns {
		if pattern.MatchString(normalized) {
			return &models.InjectionClassification{
				IsSafe:     false,
				Confidence: 0.85,
				Category:   "regex_match",
			}
		}
	}

	// Structural analysis: high density of control characters or
	// unusual formatting that suggests prompt manipulation
	if d.hasStructuralIndicators(normalized) {
		return &models.InjectionClassification{
			IsSafe:     false,
			Confidence: 0.65,
			Category:   "structural",
		}
	}

	return &models.InjectionClassification{
		IsSafe:     true,
		Confidence: 0.95,
	}
}

// IsBlocked returns true if the classification should block the input
// based on the configured threshold.
func (d *Detector) IsBlocked(classification *models.InjectionClassification) bool {
	if classification.IsSafe {
		return false
	}
	return classification.Confidence >= d.threshold
}

// hasStructuralIndicators checks for formatting tricks commonly used
// in injection attacks: excessive delimiters, fake message boundaries, etc.
func (d *Detector) hasStructuralIndicators(text string) bool {
	// Count delimiter-like patterns
	delimiterCount := 0
	delimiters := []string{"---", "===", "***", "```", "|||", "###"}
	for _, del := range delimiters {
		delimiterCount += strings.Count(text, del)
	}

	// Suspicious if there are many delimiters in a short text
	if len(text) < 500 && delimiterCount > 3 {
		return true
	}

	// Check for role/message boundary spoofing
	roleSpoofs := []string{
		"Human:", "Assistant:", "User:", "System:",
		"[INST]", "[/INST]", "<|im_start|>", "<|im_end|>",
		"<|user|>", "<|assistant|>", "<|system|>",
	}
	spoofCount := 0
	for _, spoof := range roleSpoofs {
		if strings.Contains(text, spoof) {
			spoofCount++
		}
	}
	return spoofCount >= 2
}
