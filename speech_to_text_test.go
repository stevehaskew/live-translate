package main

import (
	"context"
	"fmt"
	"strings"
	"sync"
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
		{5, 16 * time.Second},  // Capped at 16s
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

// TestTokenRefreshIntervalConstant verifies the token refresh interval is set to 20 minutes
func TestTokenRefreshIntervalConstant(t *testing.T) {
	if tokenRefreshInterval != 20*time.Minute {
		t.Errorf("tokenRefreshInterval = %v, want 20m", tokenRefreshInterval)
	}
}

// TestDynamicCredentialsProvider tests the dynamic credentials provider
func TestDynamicCredentialsProvider(t *testing.T) {
	ctx := context.Background()

	// Create a SpeechToText instance
	stt := &SpeechToText{
		ctx:        ctx,
		verbose:    false,
		tokenMutex: sync.RWMutex{},
		currentToken: &TokenResponse{
			Status: "success",
			Credentials: AWSCredentials{
				AccessKeyId:     "INITIAL_KEY",
				SecretAccessKey: "INITIAL_SECRET",
				SessionToken:    "INITIAL_TOKEN",
				Expiration:      "2024-01-01T12:00:00Z",
			},
			Region: "us-east-1",
		},
	}

	// Create the dynamic provider
	provider := &dynamicCredentialsProvider{stt: stt}

	// Retrieve credentials - should get initial token
	creds, err := provider.Retrieve(ctx)
	if err != nil {
		t.Fatalf("Failed to retrieve credentials: %v", err)
	}

	if creds.AccessKeyID != "INITIAL_KEY" {
		t.Errorf("AccessKeyID = %s, want INITIAL_KEY", creds.AccessKeyID)
	}
	if creds.SecretAccessKey != "INITIAL_SECRET" {
		t.Errorf("SecretAccessKey = %s, want INITIAL_SECRET", creds.SecretAccessKey)
	}
	if creds.SessionToken != "INITIAL_TOKEN" {
		t.Errorf("SessionToken = %s, want INITIAL_TOKEN", creds.SessionToken)
	}
	if creds.Source != "DynamicTokenProvider" {
		t.Errorf("Source = %s, want DynamicTokenProvider", creds.Source)
	}

	// Update the token (simulating a refresh)
	stt.tokenMutex.Lock()
	stt.currentToken = &TokenResponse{
		Status: "success",
		Credentials: AWSCredentials{
			AccessKeyId:     "REFRESHED_KEY",
			SecretAccessKey: "REFRESHED_SECRET",
			SessionToken:    "REFRESHED_TOKEN",
			Expiration:      "2024-01-01T12:20:00Z",
		},
		Region: "us-east-1",
	}
	stt.tokenMutex.Unlock()

	// Retrieve credentials again - should get refreshed token
	creds, err = provider.Retrieve(ctx)
	if err != nil {
		t.Fatalf("Failed to retrieve refreshed credentials: %v", err)
	}

	if creds.AccessKeyID != "REFRESHED_KEY" {
		t.Errorf("After refresh: AccessKeyID = %s, want REFRESHED_KEY", creds.AccessKeyID)
	}
	if creds.SecretAccessKey != "REFRESHED_SECRET" {
		t.Errorf("After refresh: SecretAccessKey = %s, want REFRESHED_SECRET", creds.SecretAccessKey)
	}
	if creds.SessionToken != "REFRESHED_TOKEN" {
		t.Errorf("After refresh: SessionToken = %s, want REFRESHED_TOKEN", creds.SessionToken)
	}
}

// TestDynamicCredentialsProviderNoToken tests error handling when no token is available
func TestDynamicCredentialsProviderNoToken(t *testing.T) {
	ctx := context.Background()

	// Create a SpeechToText instance without a token
	stt := &SpeechToText{
		ctx:          ctx,
		verbose:      false,
		tokenMutex:   sync.RWMutex{},
		currentToken: nil,
	}

	// Create the dynamic provider
	provider := &dynamicCredentialsProvider{stt: stt}

	// Retrieve credentials - should fail
	_, err := provider.Retrieve(ctx)
	if err == nil {
		t.Error("Expected error when no token available, got nil")
	}
	if err.Error() != "no AWS token available" {
		t.Errorf("Expected error 'no AWS token available', got '%v'", err)
	}
}

// TestIsTokenExpiredError tests the token expiration error detection
func TestIsTokenExpiredError(t *testing.T) {
	tests := []struct {
		name     string
		err      error
		expected bool
	}{
		{
			name:     "nil error",
			err:      nil,
			expected: false,
		},
		{
			name:     "expired token error",
			err:      fmt.Errorf("The security token included in the request is expired"),
			expected: true,
		},
		{
			name:     "expired token exception",
			err:      fmt.Errorf("ExpiredTokenException: The token has expired"),
			expected: true,
		},
		{
			name:     "token has expired",
			err:      fmt.Errorf("token has expired"),
			expected: true,
		},
		{
			name:     "security token expired",
			err:      fmt.Errorf("security token expired"),
			expected: true,
		},
		{
			name:     "credentials have expired",
			err:      fmt.Errorf("credentials have expired"),
			expected: true,
		},
		{
			name:     "unrelated expired message not matched",
			err:      fmt.Errorf("certificate expired"),
			expected: false, // We only match specific AWS token patterns, not generic "expired"
		},
		{
			name:     "request timeout not matched",
			err:      fmt.Errorf("request has expired"),
			expected: false, // Removed this pattern to avoid false positives with generic timeouts
		},
		{
			name:     "non-expired error",
			err:      fmt.Errorf("connection refused"),
			expected: false,
		},
		{
			name:     "access denied error",
			err:      fmt.Errorf("AccessDenied: User is not authorized"),
			expected: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := isTokenExpiredError(tt.err)
			if result != tt.expected {
				t.Errorf("isTokenExpiredError(%v) = %v, want %v", tt.err, result, tt.expected)
			}
		})
	}
}

// TestTokenExpiredError tests the TokenExpiredError type
func TestTokenExpiredError(t *testing.T) {
	innerErr := fmt.Errorf("the security token included in the request is expired")
	tokenErr := &TokenExpiredError{Err: innerErr}

	// Test Error() method
	errStr := tokenErr.Error()
	if !strings.Contains(errStr, "AWS token expired") {
		t.Errorf("TokenExpiredError.Error() = %s, want to contain 'AWS token expired'", errStr)
	}
	if !strings.Contains(errStr, innerErr.Error()) {
		t.Errorf("TokenExpiredError.Error() = %s, want to contain inner error message", errStr)
	}

	// Test Unwrap() method
	unwrapped := tokenErr.Unwrap()
	if unwrapped != innerErr {
		t.Errorf("TokenExpiredError.Unwrap() = %v, want %v", unwrapped, innerErr)
	}

	// Test that isTokenExpiredError detects wrapped error
	if !isTokenExpiredError(tokenErr) {
		t.Error("isTokenExpiredError should detect TokenExpiredError")
	}
}

// TestMaxTokenRefreshRetriesConstant verifies the max token refresh retries constant
func TestMaxTokenRefreshRetriesConstant(t *testing.T) {
	if maxTokenRefreshRetries != 3 {
		t.Errorf("maxTokenRefreshRetries = %d, want 3", maxTokenRefreshRetries)
	}
}
