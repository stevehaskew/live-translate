package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
)

const (
	huggingFaceBaseURL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
)

// modelInfo maps a short model size name to the filename and approximate size
// (for display purposes).
var modelInfo = map[string]struct {
	filename string
	sizeDesc string
}{
	"tiny.en":  {filename: "ggml-tiny.en.bin", sizeDesc: "~78 MB"},
	"base.en":  {filename: "ggml-base.en.bin", sizeDesc: "~148 MB"},
	"small.en": {filename: "ggml-small.en.bin", sizeDesc: "~466 MB"},
}

// defaultModelsDir returns ~/.yot/models, creating it if necessary.
func defaultModelsDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("could not determine home directory: %w", err)
	}
	dir := filepath.Join(home, ".yot", "models")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", fmt.Errorf("could not create models directory %s: %w", dir, err)
	}
	return dir, nil
}

// EnsureModel checks whether the ggml model file for modelSize (e.g.
// "base.en") is present in ~/.yot/models/.  If it is missing it downloads the
// file from Hugging Face, printing progress to stdout.  It returns the
// absolute path to the model file.
//
// If overridePath is non-empty, that path is returned directly without any
// download (the caller is expected to have chosen an explicit model file).
func EnsureModel(modelSize, overridePath string) (string, error) {
	if overridePath != "" {
		if _, err := os.Stat(overridePath); err != nil {
			return "", fmt.Errorf("model file not found at %s: %w", overridePath, err)
		}
		return overridePath, nil
	}

	info, ok := modelInfo[modelSize]
	if !ok {
		return "", fmt.Errorf("unknown model size %q (valid: tiny.en, base.en, small.en)", modelSize)
	}

	dir, err := defaultModelsDir()
	if err != nil {
		return "", err
	}

	modelPath := filepath.Join(dir, info.filename)

	// Already downloaded?
	if fi, err := os.Stat(modelPath); err == nil && fi.Size() > 0 {
		return modelPath, nil
	}

	// Download
	dlURL := fmt.Sprintf("%s/%s?download=true", huggingFaceBaseURL, info.filename)
	fmt.Printf("Downloading whisper model %s (%s) to %s ...\n", info.filename, info.sizeDesc, modelPath)

	tmpPath := modelPath + ".tmp"
	if err := downloadFile(dlURL, tmpPath); err != nil {
		os.Remove(tmpPath)
		return "", fmt.Errorf("download failed: %w", err)
	}

	// Atomic rename to avoid corrupt partial files
	if err := os.Rename(tmpPath, modelPath); err != nil {
		os.Remove(tmpPath)
		return "", fmt.Errorf("failed to finalise model file: %w", err)
	}

	fmt.Printf("✓ Model downloaded to %s\n", modelPath)
	return modelPath, nil
}

// downloadFile streams a URL to a local file, printing a simple byte-count
// progress indicator to stdout.
func downloadFile(url, dest string) error {
	resp, err := http.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, resp.Status)
	}

	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()

	var downloaded int64
	buf := make([]byte, 256*1024) // 256 KB chunks
	for {
		n, readErr := resp.Body.Read(buf)
		if n > 0 {
			if _, writeErr := out.Write(buf[:n]); writeErr != nil {
				return writeErr
			}
			downloaded += int64(n)
			// Simple progress line
			fmt.Printf("\r  %.1f MB downloaded", float64(downloaded)/(1024*1024))
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			return readErr
		}
	}
	fmt.Println() // newline after progress
	return nil
}
