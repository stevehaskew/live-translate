package main

import (
	"testing"
	"time"
)

// TestCalculateRetryDelay tests the exponential backoff calculation
func TestCalculateRetryDelay(t *testing.T) {
	tests := []struct {
		retryCount    int
		expectedDelay time.Duration
	}{
		{0, 1 * time.Second},
		{1, 2 * time.Second},
		{2, 4 * time.Second},
		{3, 8 * time.Second},
		{4, 16 * time.Second},
		{5, 16 * time.Second}, // Capped at 16s
		{10, 16 * time.Second}, // Capped at 16s
	}

	for _, tt := range tests {
		t.Run("", func(t *testing.T) {
			delay := calculateRetryDelay(tt.retryCount)
			if delay != tt.expectedDelay {
				t.Errorf("calculateRetryDelay(%d) = %v, want %v", tt.retryCount, delay, tt.expectedDelay)
			}
		})
	}
}

// TestMaxRetriesConstant verifies the maxRetries constant is set correctly
func TestMaxRetriesConstant(t *testing.T) {
	if maxRetries != 5 {
		t.Errorf("maxRetries = %d, want 5", maxRetries)
	}
}

// TestInitialRetryDelayConstant verifies the initialRetryDelay constant is set correctly
func TestInitialRetryDelayConstant(t *testing.T) {
	if initialRetryDelay != 1*time.Second {
		t.Errorf("initialRetryDelay = %v, want 1s", initialRetryDelay)
	}
}
