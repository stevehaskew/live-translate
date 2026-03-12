.PHONY: build clean help install-deps build-linux build-darwin build-windows whisper-lib download-model

# whisper.cpp source and build directories
WHISPER_SRC  := build/whisper-src
WHISPER_LIB  := $(WHISPER_SRC)/build/src/libwhisper.a
WHISPER_INC  := $(WHISPER_SRC)/include
CGO_FLAGS    := CGO_ENABLED=1 C_INCLUDE_PATH=$(PWD)/$(WHISPER_SRC)/include:$(PWD)/$(WHISPER_SRC)/ggml/include LIBRARY_PATH=$(PWD)/$(WHISPER_SRC)/build/src:$(PWD)/$(WHISPER_SRC)/build/ggml/src:$(PWD)/$(WHISPER_SRC)/build/ggml/src/ggml-metal:$(PWD)/$(WHISPER_SRC)/build/ggml/src/ggml-blas:$(PWD)/$(WHISPER_SRC)/build/ggml/src/ggml-cpu

# Clone and build whisper.cpp static library
whisper-lib: $(WHISPER_LIB)

$(WHISPER_LIB):
	@echo "Cloning whisper.cpp..."
	@mkdir -p build
	@if [ ! -d "$(WHISPER_SRC)" ]; then \
		git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git $(WHISPER_SRC); \
	fi
	@echo "Building libwhisper.a (this may take a minute)..."
	cmake -S $(WHISPER_SRC) -B $(WHISPER_SRC)/build -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_EXAMPLES=OFF -DWHISPER_BUILD_TESTS=OFF
	cmake --build $(WHISPER_SRC)/build --config Release -j
	@echo "✓ libwhisper.a built"

# Build the speech-to-text client for the current platform
build: whisper-lib
	@echo "Building speech-to-text client..."
	$(CGO_FLAGS) go build -o speech_to_text_go .
	@echo "Build complete: ./speech_to_text_go"

# Download a whisper model to ~/.yot/models/ (default: base.en)
download-model:
	@echo "Downloading whisper model (run the binary to auto-download instead)..."
	@mkdir -p ~/.yot/models
	@MODEL_SIZE=$${MODEL_SIZE:-base.en}; \
	FILE="ggml-$$MODEL_SIZE.bin"; \
	if [ -f "$$HOME/.yot/models/$$FILE" ]; then \
		echo "✓ Model already exists: ~/.yot/models/$$FILE"; \
	else \
		echo "Downloading $$FILE..."; \
		curl -L -o "$$HOME/.yot/models/$$FILE" \
			"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$$FILE?download=true"; \
		echo "✓ Downloaded to ~/.yot/models/$$FILE"; \
	fi

# Build for Linux
build-linux: whisper-lib
	@echo "Building for Linux (amd64)..."
	GOOS=linux GOARCH=amd64 $(CGO_FLAGS) go build -o speech_to_text_go-linux-amd64 .
	@echo "Build complete: ./speech_to_text_go-linux-amd64"

# Build for macOS
build-darwin: whisper-lib
	@echo "Building for macOS (amd64)..."
	GOOS=darwin GOARCH=amd64 $(CGO_FLAGS) go build -o speech_to_text_go-darwin-amd64 .
	@echo "Building for macOS (arm64)..."
	GOOS=darwin GOARCH=arm64 $(CGO_FLAGS) go build -o speech_to_text_go-darwin-arm64 .
	@echo "Build complete: ./speech_to_text_go-darwin-*"

# Build for Windows
build-windows: whisper-lib
	@echo "Building for Windows (amd64)..."
	GOOS=windows GOARCH=amd64 $(CGO_FLAGS) go build -o speech_to_text_go-windows-amd64.exe .
	@echo "Build complete: ./speech_to_text_go-windows-amd64.exe"

# Build for all platforms
build-all: build-linux build-darwin build-windows

# Install Go dependencies
install-deps:
	@echo "Installing Go dependencies..."
	go mod download
	go mod tidy
	@echo "Dependencies installed"

# Clean built binaries and whisper build
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -f speech_to_text_go speech_to_text_go-* speech_to_text_go-*.exe
	@echo "Clean complete"

# Show help
help:
	@echo "Available targets:"
	@echo "  build          - Build for current platform (includes whisper.cpp)"
	@echo "  whisper-lib    - Clone and build whisper.cpp static library"
	@echo "  download-model - Download a whisper model (MODEL_SIZE=base.en by default)"
	@echo "  build-linux    - Build for Linux (amd64)"
	@echo "  build-darwin   - Build for macOS (amd64 and arm64)"
	@echo "  build-windows  - Build for Windows (amd64)"
	@echo "  build-all      - Build for all platforms"
	@echo "  install-deps   - Install Go dependencies"
	@echo "  clean          - Remove built binaries and whisper build"
	@echo "  help           - Show this help message"
