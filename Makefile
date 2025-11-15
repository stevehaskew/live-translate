.PHONY: build clean help install-deps build-linux build-darwin build-windows

# Build the speech-to-text client for the current platform
build:
	@echo "Building speech-to-text client..."
	go build -o speech_to_text_go speech_to_text.go
	@echo "Build complete: ./speech_to_text_go"

# Build for Linux
build-linux:
	@echo "Building for Linux (amd64)..."
	GOOS=linux GOARCH=amd64 go build -o speech_to_text_go-linux-amd64 speech_to_text.go
	@echo "Build complete: ./speech_to_text_go-linux-amd64"

# Build for macOS
build-darwin:
	@echo "Building for macOS (amd64)..."
	GOOS=darwin GOARCH=amd64 go build -o speech_to_text_go-darwin-amd64 speech_to_text.go
	@echo "Building for macOS (arm64)..."
	GOOS=darwin GOARCH=arm64 go build -o speech_to_text_go-darwin-arm64 speech_to_text.go
	@echo "Build complete: ./speech_to_text_go-darwin-*"

# Build for Windows
build-windows:
	@echo "Building for Windows (amd64)..."
	GOOS=windows GOARCH=amd64 go build -o speech_to_text_go-windows-amd64.exe speech_to_text.go
	@echo "Build complete: ./speech_to_text_go-windows-amd64.exe"

lambda:
	./scripts/build_lambda.sh

frontend:
	./scripts/build_frontend.sh

terraform:
	cd terraform && terraform apply -auto-approve

# Build for all platforms
build-all: build-linux build-darwin build-windows

local: build lambda terraform frontend

# Install Go dependencies
install-deps:
	@echo "Installing Go dependencies..."
	go mod download
	go mod tidy
	@echo "Dependencies installed"

# Clean built binaries
clean:
	@echo "Cleaning build artifacts..."
	rm -f speech_to_text_go speech_to_text_go-* speech_to_text_go-*.exe
	@echo "Clean complete"

# Show help
help:
	@echo "Available targets:"
	@echo "  build        - Build for current platform"
	@echo "  build-linux  - Build for Linux (amd64)"
	@echo "  build-darwin - Build for macOS (amd64 and arm64)"
	@echo "  build-windows- Build for Windows (amd64)"
	@echo "  build-all    - Build for all platforms"
	@echo "  install-deps - Install Go dependencies"
	@echo "  clean        - Remove built binaries"
	@echo "  help         - Show this help message"
