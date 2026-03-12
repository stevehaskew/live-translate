package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"syscall"

	whisper "github.com/ggerganov/whisper.cpp/bindings/go/pkg/whisper"
)

const (
	// whisperWindowSeconds controls how many seconds of audio are accumulated
	// before being sent to the Whisper model for recognition.
	whisperWindowSeconds = 3

	// whisperWindowSamples = sampleRate * whisperWindowSeconds
	whisperWindowSamples = sampleRate * whisperWindowSeconds
)

// WhisperEngine implements TranscriptionEngine using a local whisper.cpp model.
type WhisperEngine struct {
	modelPath string
	language  string
	model     whisper.Model
}

// NewWhisperEngine creates a new engine backed by a local whisper.cpp model.
// modelPath must point to a valid ggml model file (e.g. ggml-base.en.bin).
func NewWhisperEngine(modelPath, language string) (*WhisperEngine, error) {
	// whisper.cpp prints verbose init diagnostics directly to the C stderr
	// file descriptor.  Redirect fd 2 to /dev/null for the duration of the
	// model load, then restore it so normal Go logging is unaffected.
	restore := suppressStderr()
	model, err := whisper.New(modelPath)
	restore()
	if err != nil {
		return nil, fmt.Errorf("failed to load whisper model %s: %w", modelPath, err)
	}
	return &WhisperEngine{
		modelPath: modelPath,
		language:  language,
		model:     model,
	}, nil
}

// Start implements TranscriptionEngine.  It accumulates audio in windows of
// whisperWindowSeconds, runs inference on each window, and emits non-empty
// transcripts on the returned channel.
func (e *WhisperEngine) Start(ctx context.Context, audioIn <-chan []int16) (<-chan string, error) {
	wCtx, err := e.model.NewContext()
	if err != nil {
		return nil, fmt.Errorf("failed to create whisper context: %w", err)
	}

	// Configure the context — only set language on multilingual models.
	// English-only (.en) models do not support SetLanguage and will return an
	// error if we call it.
	if e.language != "" && wCtx.IsMultilingual() {
		if err := wCtx.SetLanguage(e.language); err != nil {
			log.Printf("Warning: could not set whisper language to %q: %v", e.language, err)
		}
	}

	out := make(chan string, 16)

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		defer close(out)

		// Accumulate int16 samples, then convert a full window to float32.
		buf := make([]int16, 0, whisperWindowSamples)

		for {
			select {
			case <-ctx.Done():
				// Do not process leftover audio on shutdown — the inference
				// call is blocking C code and would delay exit by up to
				// whisperWindowSeconds.
				return
			case samples, ok := <-audioIn:
				if !ok {
					// Channel closed — process leftover audio
					if len(buf) > 0 {
						e.processWindow(ctx, wCtx, int16ToFloat32(buf), out)
					}
					return
				}
				buf = append(buf, samples...)

				// Once we have enough samples for a full window, process them
				for len(buf) >= whisperWindowSamples {
					window := buf[:whisperWindowSamples]
					buf = buf[whisperWindowSamples:]

					e.processWindow(ctx, wCtx, int16ToFloat32(window), out)
				}
			}
		}
	}()

	return out, nil
}

// processWindow runs whisper inference on a float32 PCM window and sends any
// recognised text to the output channel.
func (e *WhisperEngine) processWindow(ctx context.Context, wCtx whisper.Context, samples []float32, out chan<- string) {
	if err := wCtx.Process(samples, nil, nil, nil); err != nil {
		log.Printf("Whisper process error: %v", err)
		return
	}

	for {
		segment, err := wCtx.NextSegment()
		if err != nil {
			break
		}
		text := strings.TrimSpace(segment.Text)
		if text == "" || isWhisperNoiseToken(text) {
			continue
		}
		select {
		case out <- text:
		case <-ctx.Done():
			return
		}
	}

	wCtx.ResetTimings()
}

// Close implements TranscriptionEngine.
func (e *WhisperEngine) Close() error {
	if e.model != nil {
		e.model.Close()
	}
	return nil
}

// int16ToFloat32 converts PCM int16 samples to the float32 range [-1.0, 1.0]
// expected by whisper.cpp.
func int16ToFloat32(samples []int16) []float32 {
	out := make([]float32, len(samples))
	for i, s := range samples {
		out[i] = float32(s) / 32768.0
	}
	return out
}

// suppressStderr redirects the OS-level file descriptor 2 (stderr) to
// /dev/null and returns a restore function.  This is used to silence verbose
// diagnostic output emitted directly by the C whisper.cpp library during
// model initialisation, which cannot be intercepted via Go's log package.
func suppressStderr() func() {
	// Duplicate the real stderr so we can restore it afterwards.
	savedFd, err := syscall.Dup(int(os.Stderr.Fd()))
	if err != nil {
		// If we can't dup, return a no-op so the caller is always safe.
		return func() {}
	}
	devNull, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0)
	if err != nil {
		syscall.Close(savedFd)
		return func() {}
	}
	// Point fd 2 at /dev/null.
	if err := syscall.Dup2(int(devNull.Fd()), 2); err != nil {
		devNull.Close()
		syscall.Close(savedFd)
		return func() {}
	}
	devNull.Close()
	return func() {
		syscall.Dup2(savedFd, 2)
		syscall.Close(savedFd)
	}
}

// isWhisperNoiseToken reports whether text is a whisper meta/noise token that
// should be suppressed rather than forwarded for translation.  Whisper emits
// tokens like [BLANK_AUDIO], (Silence), [MUSIC], (Music), etc. for segments
// that contain no real speech.
func isWhisperNoiseToken(text string) bool {
	// Tokens that are entirely wrapped in [...] or (...) are whisper
	// internal annotations, not transcribed speech.
	if (strings.HasPrefix(text, "[") && strings.HasSuffix(text, "]")) ||
		(strings.HasPrefix(text, "(") && strings.HasSuffix(text, ")")) {
		return true
	}
	return false
}
