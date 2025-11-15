#!/bin/bash
# Build Lambda deployment package for AWS API Gateway
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
BUILD_DIR="$PROJECT_ROOT/lambda_build"
OUTPUT_ZIP="$PROJECT_ROOT/lambda_deployment.zip"

echo "Building Lambda deployment package..."
echo "Project root: $PROJECT_ROOT"

# Clean up previous build
rm -rf "$BUILD_DIR"
rm -f "$OUTPUT_ZIP"

# Create build directory
mkdir -p "$BUILD_DIR"

# Copy Lambda handler and dependencies
echo "Copying Python files..."
cp "$PROJECT_ROOT/lambda_handler.py" "$BUILD_DIR/"
cp "$PROJECT_ROOT/client_map.py" "$BUILD_DIR/"
cp "$PROJECT_ROOT/message_handler.py" "$BUILD_DIR/"
cp "$PROJECT_ROOT/token_generator.py" "$BUILD_DIR/"

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -q -t "$BUILD_DIR" boto3 botocore

# Create deployment package
echo "Creating deployment package..."
cd "$BUILD_DIR"
zip -q -r "$OUTPUT_ZIP" .

# Clean up build directory
cd "$PROJECT_ROOT"
rm -rf "$BUILD_DIR"

echo "✓ Lambda deployment package created: $OUTPUT_ZIP"
echo "Package size: $(du -h "$OUTPUT_ZIP" | cut -f1)"
echo ""
echo "Next steps:"
echo "1. cd terraform"
echo "2. terraform init"
echo "3. terraform apply"
