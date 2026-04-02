.PHONY: build build-release develop test test-rust test-python bench clean

# Default target
all: develop

# Build in debug mode
build:
	maturin build

# Build in release mode (optimized)
build-release:
	RUSTFLAGS="-C target-cpu=native" maturin build --release

# Install in development mode
develop:
	RUSTFLAGS="-C target-cpu=native" maturin develop --release

# Run Rust tests
test-rust:
	cargo test

# Run Python tests (requires develop first)
test-python:
	python -m pytest python/tests/ -v -s

# Run all tests
test: test-rust develop test-python

# Run benchmarks
bench:
	cargo bench

# Clean build artifacts
clean:
	cargo clean
	rm -rf target/
	rm -rf .pytest_cache/
	rm -rf python/tests/__pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

# Format code
fmt:
	cargo fmt

# Check code
check:
	cargo check
	cargo clippy -- -D warnings

# Build wheels for distribution
wheels:
	RUSTFLAGS="-C target-cpu=native" maturin build --release

# Show help
help:
	@echo "Available targets:"
	@echo "  develop      - Install in development mode (default)"
	@echo "  build        - Build debug version"
	@echo "  build-release - Build optimized release version"
	@echo "  test         - Run all tests"
	@echo "  test-rust    - Run Rust unit tests only"
	@echo "  test-python  - Run Python integration tests"
	@echo "  bench        - Run performance benchmarks"
	@echo "  clean        - Remove build artifacts"
	@echo "  fmt          - Format Rust code"
	@echo "  check        - Run cargo check and clippy"
	@echo "  wheels       - Build distribution wheels"
