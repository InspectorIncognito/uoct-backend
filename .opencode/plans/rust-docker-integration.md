# Rust Map Matching Docker Integration Plan

## Overview
Integrate the Rust `map_matching` extension into the Docker build process.

## Files to Modify

### 1. `requirements-prod.txt`

Add numpy explicitly (required by the Rust extension):

```diff
 scipy
 beautifulsoup4
+numpy>=1.24.0
```

### 2. `backend/rust/map_matching/.cargo/config.toml`

Replace hardcoded cascadelake target with comments (CPU target will be set via RUSTFLAGS):

**Replace entire file with:**

```toml
# Cargo configuration for map_matching
# CPU target configured via RUSTFLAGS environment variable at build time
#
# Examples:
# - Local development: RUSTFLAGS="-C target-cpu=native"
# - EC2 Cascade Lake: RUSTFLAGS="-C target-cpu=cascadelake"
# - Docker portable:  RUSTFLAGS="-C target-cpu=x86-64-v3"
#
# The Makefile and Dockerfile set RUSTFLAGS="-C target-cpu=native" by default

# Uncomment below for local development on Cascade Lake machines:
# [build]
# rustflags = ["-C", "target-cpu=cascadelake"]
```

### 3. `backend/rust/map_matching/Makefile`

Update to use `native` CPU target instead of `cascadelake`:

```diff
 # Build in release mode (optimized)
 build-release:
-	RUSTFLAGS="-C target-cpu=cascadelake" maturin build --release
+	RUSTFLAGS="-C target-cpu=native" maturin build --release
 
 # Install in development mode
 develop:
-	RUSTFLAGS="-C target-cpu=cascadelake" maturin develop --release
+	RUSTFLAGS="-C target-cpu=native" maturin develop --release

 # Build wheels for distribution
 wheels:
-	RUSTFLAGS="-C target-cpu=cascadelake" maturin build --release
+	RUSTFLAGS="-C target-cpu=native" maturin build --release
```

### 4. `docker/Dockerfile`

Add Rust build stage. Replace entire file with:

```dockerfile
FROM python:3.12-alpine3.20 as base

# ============================================================================
# Rust Builder Stage - Build the map_matching extension
# ============================================================================
FROM base as rust-builder

# Install build dependencies for Rust compilation
RUN apk add --no-cache \
    curl \
    build-base \
    openssl-dev \
    musl-dev

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.cargo/bin:${PATH}"

# Install maturin for building Python wheels from Rust
RUN pip install maturin

# Copy and build the Rust map_matching extension
COPY backend/rust/map_matching /build/map_matching
WORKDIR /build/map_matching

# Build with native CPU optimizations (auto-detect at build time)
RUN RUSTFLAGS="-C target-cpu=native" maturin build --release

# ============================================================================
# Dependencies Stage
# ============================================================================
FROM base as dependencies

RUN /bin/sh -c "apk update"
RUN /bin/sh -c "apk add --no-cache \
    gdal-dev \
    g++  \
    proj \
    proj-dev \
    proj-util \
    gcc \
    musl-dev \
    geos \
    geos-dev \
    postgresql-dev\
    "

# ============================================================================
# Requirements Stage - Install Python dependencies
# ============================================================================
FROM dependencies as requirements

RUN mkdir /install
COPY requirements-prod.txt /install/requirements-prod.txt
RUN /bin/sh -c 'pip3 install --no-cache-dir --upgrade pip'
RUN /bin/sh -c 'pip3 install --no-cache-dir --no-warn-script-location --prefix /install -r /install/requirements-prod.txt'

# Install the Rust map_matching wheel
COPY --from=rust-builder /build/map_matching/target/wheels/*.whl /tmp/
RUN pip3 install --no-cache-dir --no-warn-script-location --prefix /install /tmp/map_matching*.whl && rm /tmp/*.whl

# ============================================================================
# Dev Stage
# ============================================================================
FROM requirements as dev

ENV PYTHONUNBUFFERED 1
COPY --from=requirements /install /usr/local
COPY requirements-dev.txt /install/requirements-dev.txt
RUN /bin/sh -c 'apk update && apk add --no-cache postgresql-dev'
RUN /bin/sh -c 'pip3 install --no-cache-dir --upgrade pip'
RUN /bin/sh -c 'pip3 install --no-cache-dir -r /install/requirements-dev.txt'

WORKDIR /app
COPY ./docker/entrypoint.sh ./docker/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]
COPY ./backend ./backend

# ============================================================================
# Prod Stage - Set build target as prod in your docker-compose file
# ============================================================================
FROM requirements as prod

# Prevents Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
# Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED 1

COPY --from=requirements /install /usr/local
RUN /bin/sh -c 'apk update && apk add --no-cache postgresql-dev'
WORKDIR /app

# copy project files on /app folder
COPY ./docker ./docker
COPY ./backend ./backend

EXPOSE 8000
ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]
```

## Verification Steps

After making the changes, verify with:

```bash
# 1. Build the Docker image
docker build -f docker/Dockerfile --target prod -t uoct-backend:test .

# 2. Test that map_matching is available
docker run --rm uoct-backend:test python -c "import map_matching; print(f'Version: {map_matching.__version__}')"

# 3. Run the test suite
docker run --rm uoct-backend:test python -m pytest backend/rust/map_matching/python/tests/ -v
```

## Local Testing (without Docker)

```bash
# Install Rust (one-time)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

# Install Python dependencies
pip install maturin pytest numpy

# Build and test
cd backend/rust/map_matching
make test
```

## Notes

- The Docker build uses `target-cpu=native` which auto-detects the build machine's CPU
- For maximum performance on EC2 Cascade Lake instances, the EC2 deployment should ideally build with `target-cpu=cascadelake`
- If building on a different CPU than the deployment target, consider using `target-cpu=x86-64-v3` for broad compatibility with AVX2-capable CPUs
