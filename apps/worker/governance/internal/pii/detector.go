// Package pii detects and redacts Personally Identifiable Information.
// Uses regex patterns for structured PII (SSN, credit card, etc.)
// and is designed to integrate an ML-based NER model for unstructured PII.
package pii

import (
	"regexp"
	"strings"

	"github.com/agent-os/governance-proxy/pkg/models"
)

// Detector identifies and redacts PII from text data.
type Detector struct {
	patterns []piiPattern
}

type piiPattern struct {
	piiType string
	regex   *regexp.Regexp
	redact  string
}

// NewDetector creates a PII detector with all standard patterns.
func NewDetector() *Detector {
	return &Detector{
		patterns: []piiPattern{
			{
				piiType: "SSN",
				regex:   regexp.MustCompile(`\b\d{3}-\d{2}-\d{4}\b`),
				redact:  "[REDACTED-SSN]",
			},
			{
				piiType: "CREDIT_CARD",
				regex:   regexp.MustCompile(`\b(?:\d{4}[-\s]?){3}\d{4}\b`),
				redact:  "[REDACTED-CC]",
			},
			{
				piiType: "IBAN",
				regex:   regexp.MustCompile(`\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b`),
				redact:  "[REDACTED-IBAN]",
			},
			{
				piiType: "EMAIL",
				regex:   regexp.MustCompile(`\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b`),
				redact:  "[REDACTED-EMAIL]",
			},
			{
				piiType: "PHONE",
				regex:   regexp.MustCompile(`\b(?:\+?1[-.]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b`),
				redact:  "[REDACTED-PHONE]",
			},
			{
				piiType: "IP_ADDRESS",
				regex:   regexp.MustCompile(`\b(?:\d{1,3}\.){3}\d{1,3}\b`),
				redact:  "[REDACTED-IP]",
			},
			{
				piiType: "PASSPORT",
				regex:   regexp.MustCompile(`\b[A-Z]{1,2}\d{6,9}\b`),
				redact:  "[REDACTED-PASSPORT]",
			},
			{
				piiType: "DOB",
				regex:   regexp.MustCompile(`\b(?:0[1-9]|1[0-2])[/\-](?:0[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b`),
				redact:  "[REDACTED-DOB]",
			},
		},
	}
}

// Detect scans text for PII and returns all detections.
func (d *Detector) Detect(text string) []models.PIIDetection {
	var detections []models.PIIDetection

	for _, p := range d.patterns {
		matches := p.regex.FindAllStringIndex(text, -1)
		for _, match := range matches {
			detections = append(detections, models.PIIDetection{
				Type:     p.piiType,
				Value:    text[match[0]:match[1]],
				Redacted: p.redact,
				Start:    match[0],
				End:      match[1],
			})
		}
	}

	return detections
}

// Redact replaces all PII in text with redaction markers.
// Returns the redacted text and the list of detections.
func (d *Detector) Redact(text string) (string, []models.PIIDetection) {
	detections := d.Detect(text)
	if len(detections) == 0 {
		return text, nil
	}

	result := text
	// Process detections in reverse order to preserve indices
	for i := len(detections) - 1; i >= 0; i-- {
		det := detections[i]
		result = result[:det.Start] + det.Redacted + result[det.End:]
	}

	return result, detections
}

// RedactMap recursively redacts PII in a map of string values.
// Returns the redacted map and all detections found.
func (d *Detector) RedactMap(data map[string]interface{}) (map[string]interface{}, []models.PIIDetection) {
	var allDetections []models.PIIDetection
	result := make(map[string]interface{}, len(data))

	for k, v := range data {
		switch val := v.(type) {
		case string:
			redacted, detections := d.Redact(val)
			result[k] = redacted
			allDetections = append(allDetections, detections...)
		case map[string]interface{}:
			redacted, detections := d.RedactMap(val)
			result[k] = redacted
			allDetections = append(allDetections, detections...)
		default:
			result[k] = v
		}
	}

	return result, allDetections
}

// ContainsPII checks if text contains any PII patterns.
func (d *Detector) ContainsPII(text string) bool {
	for _, p := range d.patterns {
		if p.regex.MatchString(text) {
			return true
		}
	}
	return false
}

// MaskValue partially masks a value for display purposes.
// E.g., "1234-5678-9012-3456" → "****-****-****-3456"
func MaskValue(value string, visibleChars int) string {
	if len(value) <= visibleChars {
		return strings.Repeat("*", len(value))
	}
	masked := strings.Repeat("*", len(value)-visibleChars)
	return masked + value[len(value)-visibleChars:]
}
