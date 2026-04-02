//! High-performance HMM Map Matching Library
//!
//! This library provides a Rust implementation of Hidden Markov Model (HMM)
//! based map matching for GPS trajectories, optimized for:
//! - Single-threaded performance (targeting 2 vCPU EC2 instances)
//! - AVX-512 SIMD operations on Cascade Lake processors
//! - Memory efficiency (f32 coordinates, pre-allocated buffers)
//!
//! Based on the paper "Hidden Markov Map Matching Through Noise and Sparseness"
//! by Newson and Krumm.

use pyo3::prelude::*;

mod geometry;
mod probability;
mod spatial_index;
mod viterbi;

use geometry::{haversine_distance, haversine_distance_batch};
use spatial_index::SpatialIndex;
use viterbi::{viterbi_match, ViterbiResult};

/// Python module for map matching
#[pymodule]
fn map_matching(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Geometry functions
    m.add_function(wrap_pyfunction!(py_haversine_distance, m)?)?;
    m.add_function(wrap_pyfunction!(py_haversine_distance_batch, m)?)?;
    m.add_function(wrap_pyfunction!(py_point_to_line_distance, m)?)?;
    
    // Spatial index class
    m.add_class::<PySpatialIndex>()?;
    
    // Direction cache class
    m.add_class::<PyDirectionCache>()?;
    
    // Segment cache class
    m.add_class::<PySegmentCache>()?;
    
    // Main viterbi function
    m.add_function(wrap_pyfunction!(py_viterbi, m)?)?;
    
    // Batch viterbi function
    m.add_function(wrap_pyfunction!(py_batch_viterbi, m)?)?;
    
    // Version info
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    
    Ok(())
}

// ============================================================================
// Python-exposed geometry functions
// ============================================================================

/// Calculate haversine distance between two points in meters
#[pyfunction]
#[pyo3(name = "haversine_distance")]
fn py_haversine_distance(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    haversine_distance(lat1, lon1, lat2, lon2)
}

/// Calculate haversine distances for batches of points (vectorized)
#[pyfunction]
#[pyo3(name = "haversine_distance_batch")]
fn py_haversine_distance_batch<'py>(
    py: Python<'py>,
    lats1: numpy::PyReadonlyArray1<f64>,
    lons1: numpy::PyReadonlyArray1<f64>,
    lats2: numpy::PyReadonlyArray1<f64>,
    lons2: numpy::PyReadonlyArray1<f64>,
) -> PyResult<Bound<'py, numpy::PyArray1<f64>>> {
    let lats1 = lats1.as_slice()?;
    let lons1 = lons1.as_slice()?;
    let lats2 = lats2.as_slice()?;
    let lons2 = lons2.as_slice()?;
    
    let result = haversine_distance_batch(lats1, lons1, lats2, lons2);
    Ok(numpy::PyArray1::from_vec_bound(py, result))
}

/// Calculate shortest distance from point to line segment
#[pyfunction]
#[pyo3(name = "point_to_line_distance")]
fn py_point_to_line_distance(
    point_lat: f64,
    point_lon: f64,
    line_coords: Vec<(f64, f64)>, // [(lon, lat), ...]
) -> (f64, (f64, f64)) {
    geometry::point_to_line_distance(point_lat, point_lon, &line_coords)
}

// ============================================================================
// Python-exposed spatial index
// ============================================================================

/// Spatial index for efficient segment lookup
#[pyclass]
#[pyo3(name = "SpatialIndex")]
struct PySpatialIndex {
    inner: SpatialIndex,
}

#[pymethods]
impl PySpatialIndex {
    /// Create a new spatial index from segment data
    #[new]
    #[pyo3(signature = (segment_pks, geometries, interval=20.0, is_geographic=true))]
    fn new(
        segment_pks: Vec<i64>,
        geometries: Vec<Vec<(f64, f64)>>, // List of LineString coords [(lon, lat), ...]
        interval: f64,
        is_geographic: bool,
    ) -> PyResult<Self> {
        let inner = SpatialIndex::new(&segment_pks, &geometries, interval, is_geographic)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(Self { inner })
    }
    
    /// Query segments within radius of a point
    fn query(&self, lon: f64, lat: f64, max_distance: f64) -> Vec<i64> {
        self.inner.query(lon, lat, max_distance)
    }
    
    /// Get number of indexed points
    fn len(&self) -> usize {
        self.inner.len()
    }
    
    fn is_geographic(&self) -> bool {
        self.inner.is_geographic
    }
}

// ============================================================================
// Python-exposed direction cache
// ============================================================================

/// Cache for precomputed direction group data
#[pyclass]
#[pyo3(name = "DirectionCache")]
struct PyDirectionCache {
    inner: viterbi::DirectionCache,
}

#[pymethods]
impl PyDirectionCache {
    /// Create direction cache from segment directions
    #[new]
    fn new(
        segment_pks: Vec<i64>,
        directions: Vec<i32>,
        geometries: Vec<Vec<(f64, f64)>>,
    ) -> PyResult<Self> {
        let inner = viterbi::DirectionCache::new(&segment_pks, &directions, &geometries)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(Self { inner })
    }
    
    /// Get direction for a segment
    fn get_direction(&self, segment_pk: i64) -> Option<i32> {
        self.inner.get_direction(segment_pk)
    }
}

// ============================================================================
// Python-exposed segment cache
// ============================================================================

/// Cache for segment geometries and bearings
#[pyclass]
#[pyo3(name = "SegmentCache")]
struct PySegmentCache {
    inner: viterbi::SegmentCache,
}

#[pymethods]
impl PySegmentCache {
    /// Create segment cache from segment data
    #[new]
    fn new(
        segment_pks: Vec<i64>,
        geometries: Vec<Vec<(f64, f64)>>,
        bearings: Vec<Option<f64>>,
    ) -> PyResult<Self> {
        let inner = viterbi::SegmentCache::new(&segment_pks, &geometries, &bearings)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(Self { inner })
    }
    
    /// Get bearing for a segment
    fn get_bearing(&self, segment_pk: i64) -> Option<f64> {
        self.inner.get_bearing(segment_pk)
    }
}

// ============================================================================
// Python-exposed Viterbi algorithm
// ============================================================================

/// Run Viterbi HMM map matching algorithm
#[pyfunction]
#[pyo3(name = "viterbi")]
#[pyo3(signature = (
    gps_lons,
    gps_lats,
    spatial_index,
    direction_cache,
    segment_cache,
    max_distance=200.0,
    sigma=20.0,
    beta=25.0,
    min_candidates=2,
    gps_bearings=None,
    sigma_bearing=30.0,
    bearing_weight_factor=0.5,
    excluded_indices=None
))]
fn py_viterbi(
    gps_lons: Vec<f64>,
    gps_lats: Vec<f64>,
    spatial_index: &PySpatialIndex,
    direction_cache: &PyDirectionCache,
    segment_cache: &PySegmentCache,
    max_distance: f64,
    sigma: f64,
    beta: f64,
    min_candidates: usize,
    gps_bearings: Option<Vec<Option<f64>>>,
    sigma_bearing: f64,
    bearing_weight_factor: f64,
    excluded_indices: Option<Vec<usize>>,
) -> PyResult<(Vec<Option<i64>>, Vec<usize>, Vec<Option<(f64, f64)>>)> {
    let result = viterbi_match(
        &gps_lons,
        &gps_lats,
        &spatial_index.inner,
        &direction_cache.inner,
        &segment_cache.inner,
        max_distance,
        sigma,
        beta,
        min_candidates,
        gps_bearings.as_deref(),
        sigma_bearing,
        bearing_weight_factor,
        excluded_indices.as_deref(),
    );
    
    Ok((result.matched_segments, result.valid_indices, result.projected_points))
}

/// Run Viterbi on multiple trajectories (batch processing)
#[pyfunction]
#[pyo3(name = "batch_viterbi")]
#[pyo3(signature = (
    trajectories,
    spatial_index,
    direction_cache,
    segment_cache,
    max_distance=200.0,
    sigma=20.0,
    beta=25.0,
    min_candidates=2,
    sigma_bearing=30.0,
    bearing_weight_factor=0.5
))]
fn py_batch_viterbi(
    trajectories: Vec<(Vec<f64>, Vec<f64>, Option<Vec<Option<f64>>>)>, // (lons, lats, bearings)
    spatial_index: &PySpatialIndex,
    direction_cache: &PyDirectionCache,
    segment_cache: &PySegmentCache,
    max_distance: f64,
    sigma: f64,
    beta: f64,
    min_candidates: usize,
    sigma_bearing: f64,
    bearing_weight_factor: f64,
) -> PyResult<Vec<(Vec<Option<i64>>, Vec<usize>, Vec<Option<(f64, f64)>>)>> {
    let results: Vec<_> = trajectories
        .iter()
        .map(|(lons, lats, bearings)| {
            let result = viterbi_match(
                lons,
                lats,
                &spatial_index.inner,
                &direction_cache.inner,
                &segment_cache.inner,
                max_distance,
                sigma,
                beta,
                min_candidates,
                bearings.as_deref(),
                sigma_bearing,
                bearing_weight_factor,
                None,
            );
            (result.matched_segments, result.valid_indices, result.projected_points)
        })
        .collect();
    
    Ok(results)
}
