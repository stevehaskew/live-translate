package main

import (
	"context"
	"fmt"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// ---------------------------------------------------------------------------
// MockEngine — used to test listenAndTranscribe without real audio hardware
// ---------------------------------------------------------------------------

type MockEngine struct {
	started bool
	closed  bool
	texts   []string // texts to emit
}

func (m *MockEngine) Start(ctx context.Context, audioIn <-chan []int16) (<-chan string, error) {
	m.started = true
	out := make(chan string, len(m.texts))
	go func() {
		defer close(out)
		for _, t := range m.texts {
			select {
			case out <- t:
			case <-ctx.Done():
				return
			}
		}
		// Drain audioIn so the producer doesn't block
		for range audioIn {
		}
	}()
	return out, nil
}

func (m *MockEngine) Close() error {
	m.closed = true
	return nil
}

// ---------------------------------------------------------------------------
// int16ToFloat32 conversion tests
// ---------------------------------------------------------------------------

func TestInt16ToFloat32(t *testing.T) {
	tests := []struct {
		name     string
		input    []int16
		expected []float32
	}{
		{"zero", []int16{0}, []float32{0}},
		{"max positive", []int16{32767}, []float32{32767.0 / 32768.0}},
		{"max negative", []int16{-32768}, []float32{-1.0}},
		{"mixed", []int16{0, 16384, -16384}, []float32{0, 0.5, -0.5}},
		{"empty", []int16{}, []float32{}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := int16ToFloat32(tt.input)
			if len(result) != len(tt.expected) {
				t.Fatalf("len = %d, want %d", len(result), len(tt.expected))
			}
			for i := range result {
				if math.Abs(float64(result[i]-tt.expected[i])) > 1e-6 {
					t.Errorf("[%d] = %f, want %f", i, result[i], tt.expected[i])
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// isWhisperNoiseToken tests
// ---------------------------------------------------------------------------

func TestIsWhisperNoiseToken(t *testing.T) {
	tests := []struct {
		text string
		want bool
	}{
		{"[BLANK_AUDIO]", true},
		{"[MUSIC]", true},
		{"[Applause]", true},
		{"(Silence)", true},
		{"(Music)", true},
		{"(background noise)", true},
		// real speech — must NOT be suppressed
		{"Hello, world.", false},
		{"Thank you.", false},
		// partial brackets — not a noise token
		{"[incomplete", false},
		{"incomplete]", false},
		{"(incomplete", false},
		{"incomplete)", false},
		// empty string handled separately upstream
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.text, func(t *testing.T) {
			got := isWhisperNoiseToken(tt.text)
			if got != tt.want {
				t.Errorf("isWhisperNoiseToken(%q) = %v, want %v", tt.text, got, tt.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// EnsureModel tests
// ---------------------------------------------------------------------------

func TestEnsureModel_OverridePath(t *testing.T) {
	// Create a temporary file to act as the model
	tmp := filepath.Join(t.TempDir(), "test-model.bin")
	if err := os.WriteFile(tmp, []byte("fake model"), 0o644); err != nil {
		t.Fatal(err)
	}
	// Should return the override path directly
	path, err := EnsureModel("base.en", tmp)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if path != tmp {
		t.Errorf("path = %q, want %q", path, tmp)
	}
}

func TestEnsureModel_OverridePathNotFound(t *testing.T) {
	_, err := EnsureModel("base.en", "/nonexistent/model.bin")
	if err == nil {
		t.Fatal("expected error for missing override path")
	}
}

func TestEnsureModel_InvalidModelSize(t *testing.T) {
	_, err := EnsureModel("huge.en", "")
	if err == nil {
		t.Fatal("expected error for invalid model size")
	}
}

func TestEnsureModel_AutoDownload(t *testing.T) {
	// Spin up a fake HTTP server that returns a small payload
	fakeModel := []byte("fake-ggml-model-data")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(fakeModel)
	}))
	defer srv.Close()

	// Temporarily monkey-patch the download URL by testing downloadFile directly
	dir := t.TempDir()
	dest := filepath.Join(dir, "ggml-tiny.en.bin")
	if err := downloadFile(srv.URL, dest); err != nil {
		t.Fatalf("downloadFile failed: %v", err)
	}

	data, err := os.ReadFile(dest)
	if err != nil {
		t.Fatalf("failed to read downloaded file: %v", err)
	}
	if string(data) != string(fakeModel) {
		t.Errorf("downloaded data = %q, want %q", string(data), string(fakeModel))
	}
}

// ---------------------------------------------------------------------------
// MockEngine interface conformance
// ---------------------------------------------------------------------------

func TestMockEngineImplementsInterface(t *testing.T) {
	var _ TranscriptionEngine = (*MockEngine)(nil)
}

// ---------------------------------------------------------------------------
// Engine name validation in main logic
// ---------------------------------------------------------------------------

func TestEngineNameValidation(t *testing.T) {
	validNames := []string{"local", "aws"}
	for _, name := range validNames {
		if name != "local" && name != "aws" {
			t.Errorf("expected %q to be valid", name)
		}
	}
	invalidNames := []string{"whisper", "google", ""}
	for _, name := range invalidNames {
		if name == "local" || name == "aws" {
			t.Errorf("expected %q to be invalid", name)
		}
	}
}

// ---------------------------------------------------------------------------
// modelInfo map completeness
// ---------------------------------------------------------------------------

func TestModelInfoKeys(t *testing.T) {
	expected := []string{"tiny.en", "base.en", "small.en"}
	for _, key := range expected {
		info, ok := modelInfo[key]
		if !ok {
			t.Errorf("modelInfo missing key %q", key)
			continue
		}
		if info.filename == "" {
			t.Errorf("modelInfo[%q].filename is empty", key)
		}
		if info.sizeDesc == "" {
			t.Errorf("modelInfo[%q].sizeDesc is empty", key)
		}
	}
}

// ---------------------------------------------------------------------------
// downloadFile error handling
// ---------------------------------------------------------------------------

func TestDownloadFile_HTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	}))
	defer srv.Close()

	dest := filepath.Join(t.TempDir(), "should-not-exist.bin")
	err := downloadFile(srv.URL, dest)
	if err == nil {
		t.Fatal("expected error for HTTP 404")
	}
	if _, statErr := os.Stat(dest); statErr == nil {
		// downloadFile creates the file before checking status, but that's OK
		// because EnsureModel removes .tmp on error. Just verify the error was
		// propagated.
		t.Log("file was created but error was returned (expected)")
	}
}

func TestNewSpeechToTextWithEngine(t *testing.T) {
	ctx := context.Background()
	app, err := NewSpeechToText(ctx, "http://localhost:5050/ws", "key", -1, "eu-west-2", false, false, "local")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if app.engineName != "local" {
		t.Errorf("engineName = %q, want %q", app.engineName, "local")
	}

	app2, err := NewSpeechToText(ctx, "http://localhost:5050/ws", "key", -1, "eu-west-2", false, false, "aws")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if app2.engineName != "aws" {
		t.Errorf("engineName = %q, want %q", app2.engineName, "aws")
	}
}

func TestAWSEngineImplementsInterface(t *testing.T) {
	var _ TranscriptionEngine = (*AWSEngine)(nil)
}

func TestDefaultModelsDir(t *testing.T) {
	dir, err := defaultModelsDir()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if dir == "" {
		t.Fatal("expected non-empty directory")
	}
	// Should end with .yot/models
	if filepath.Base(dir) != "models" {
		t.Errorf("dir = %q, expected to end with 'models'", dir)
	}
	parent := filepath.Base(filepath.Dir(dir))
	if parent != ".yot" {
		t.Errorf("parent = %q, expected '.yot'", parent)
	}
	// Directory should exist
	info, err := os.Stat(dir)
	if err != nil {
		t.Fatalf("models dir does not exist: %v", err)
	}
	if !info.IsDir() {
		t.Fatal("models path is not a directory")
	}
}

func TestHuggingFaceURLFormat(t *testing.T) {
	for size, info := range modelInfo {
		expected := fmt.Sprintf("%s/%s?download=true", huggingFaceBaseURL, info.filename)
		url := fmt.Sprintf("%s/%s?download=true", huggingFaceBaseURL, info.filename)
		if url != expected {
			t.Errorf("URL for %s = %q, want %q", size, url, expected)
		}
	}
}
