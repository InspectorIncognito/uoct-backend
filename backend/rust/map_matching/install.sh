#!/bin/bash
# Installation script for Rust map_matching extension
# Run this on your EC2 instance to build and install the optimized module

set -e

echo "=== Installing Rust Map Matching Extension ==="

# Check for Rust
if ! command -v rustc &> /dev/null; then
    echo "Rust not found. Installing via rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source $HOME/.cargo/env
fi

echo "Rust version: $(rustc --version)"

# Check for maturin
if ! command -v maturin &> /dev/null; then
    echo "Installing maturin..."
    pip install maturin
fi

echo "Maturin version: $(maturin --version)"

# Navigate to the Rust project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building map_matching with Cascade Lake optimizations..."

# Build with Cascade Lake CPU optimizations
RUSTFLAGS="-C target-cpu=cascadelake" maturin develop --release

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Test the installation with:"
echo "  python -c \"import map_matching; print(f'Version: {map_matching.__version__}')\""
echo ""
echo "Run benchmarks with:"
echo "  make bench"
echo ""
echo "Run tests with:"
echo "  make test"
