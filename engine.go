package main

import "context"

// TranscriptionEngine abstracts the speech-to-text backend so different
// implementations (AWS Transcribe, local Whisper, etc.) can be swapped at
// runtime via the --engine flag.
type TranscriptionEngine interface {
	// Start begins consuming PCM int16 audio samples from audioIn and
	// emitting recognised text strings on the returned channel.  The
	// engine must close the output channel when it is done (either
	// because ctx was cancelled or audioIn was closed).
	Start(ctx context.Context, audioIn <-chan []int16) (<-chan string, error)

	// Close releases any resources held by the engine (models, etc.).
	Close() error
}
