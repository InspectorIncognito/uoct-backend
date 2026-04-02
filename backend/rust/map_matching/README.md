# Map Matching (Rust)

High-performance HMM map matching for GPS trajectories, implemented in Rust with Python bindings.

## Features

- **10-50x faster** than pure Python implementation
- **Memory efficient** - uses f32 coordinates internally
- **SIMD optimized** for Cascade Lake CPUs (AVX-512)
- **Zero-copy** NumPy array support

## Installation

### Development

```bash
# Install maturin
pip install maturin

# Build and install in development mode
cd backend/rust/map_matching
maturin develop --release
```

### Production

```bash
# Build wheel
maturin build --release

# Install wheel
pip install target/wheels/map_matching-*.whl
```

## Usage

```python
from map_matching import (
    SpatialIndex,
    DirectionCache,
    SegmentCache,
    viterbi,
    haversine_distance,
)

# Create caches from segment data
spatial_index = SpatialIndex(
    segment_pks=[1, 2, 3],
    geometries=[
        [(-70.66, -33.45), (-70.65, -33.45)],
        [(-70.65, -33.45), (-70.64, -33.45)],
        [(-70.64, -33.45), (-70.63, -33.45)],
    ],
    interval=20.0,
    is_geographic=True,
)

direction_cache = DirectionCache(
    segment_pks=[1, 2, 3],
    directions=[0, 0, 0],
    geometries=[...],
)

segment_cache = SegmentCache(
    segment_pks=[1, 2, 3],
    geometries=[...],
    bearings=[90.0, 90.0, 90.0],
)

# Run map matching
matched_segments, valid_indices, projected_points = viterbi(
    gps_lons=[-70.658, -70.648, -70.638],
    gps_lats=[-33.4501, -33.4501, -33.4501],
    spatial_index=spatial_index,
    direction_cache=direction_cache,
    segment_cache=segment_cache,
    max_distance=200.0,
    sigma=25.0,
    beta=40.0,
)
```

## Benchmarks

On EC2 t3.medium (2 vCPU, 4GB RAM, Cascade Lake):

| Operation | Python | Rust | Speedup |
|-----------|--------|------|---------|
| Single trajectory (100 pts) | ~50ms | ~1-2ms | 25-50x |
| Batch (100 trajectories) | ~5s | ~150ms | 30x |
| Haversine distance | ~1μs | ~50ns | 20x |

## Build Requirements

- Rust 1.70+
- Python 3.9+
- maturin 1.4+
