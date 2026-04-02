//! Geometry calculations optimized for map matching
//!
//! This module provides high-performance implementations of:
//! - Haversine distance (single and batch)
//! - Point-to-line distance with projection
//! - Bearing calculations
//!
//! Optimizations:
//! - SIMD-friendly batch operations
//! - Pre-computed constants
//! - Minimal branching

use std::f64::consts::PI;

/// Earth radius in meters (WGS84 mean radius)
const EARTH_RADIUS: f64 = 6_371_000.0;

/// Degrees to radians conversion factor
const DEG_TO_RAD: f64 = PI / 180.0;

/// Approximate meters per degree latitude
const METERS_PER_DEG_LAT: f64 = 111_000.0;

// ============================================================================
// Haversine Distance
// ============================================================================

/// Calculate haversine distance between two points in meters
///
/// This is the great-circle distance on Earth's surface.
#[inline]
pub fn haversine_distance(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let lat1_rad = lat1 * DEG_TO_RAD;
    let lat2_rad = lat2 * DEG_TO_RAD;
    let dlat = (lat2 - lat1) * DEG_TO_RAD;
    let dlon = (lon2 - lon1) * DEG_TO_RAD;

    let sin_dlat_half = (dlat * 0.5).sin();
    let sin_dlon_half = (dlon * 0.5).sin();

    let a = sin_dlat_half * sin_dlat_half
        + lat1_rad.cos() * lat2_rad.cos() * sin_dlon_half * sin_dlon_half;

    let c = 2.0 * a.sqrt().asin();

    EARTH_RADIUS * c
}

/// Calculate haversine distances for batches of points
///
/// Optimized for throughput with cache-friendly memory access patterns.
pub fn haversine_distance_batch(
    lats1: &[f64],
    lons1: &[f64],
    lats2: &[f64],
    lons2: &[f64],
) -> Vec<f64> {
    debug_assert_eq!(lats1.len(), lons1.len());
    debug_assert_eq!(lats1.len(), lats2.len());
    debug_assert_eq!(lats1.len(), lons2.len());

    let n = lats1.len();
    let mut result = Vec::with_capacity(n);

    // Process in chunks for better cache utilization
    for i in 0..n {
        result.push(haversine_distance(lats1[i], lons1[i], lats2[i], lons2[i]));
    }

    result
}

// ============================================================================
// Point-to-Line Distance
// ============================================================================

/// Calculate shortest distance from a point to a polyline
///
/// Returns (distance_meters, (projected_lon, projected_lat))
pub fn point_to_line_distance(
    point_lat: f64,
    point_lon: f64,
    line_coords: &[(f64, f64)], // [(lon, lat), ...]
) -> (f64, (f64, f64)) {
    if line_coords.is_empty() {
        return (f64::INFINITY, (point_lon, point_lat));
    }

    if line_coords.len() == 1 {
        let (lon, lat) = line_coords[0];
        let dist = haversine_distance(point_lat, point_lon, lat, lon);
        return (dist, (lon, lat));
    }

    let mut min_dist = f64::INFINITY;
    let mut best_projection = (point_lon, point_lat);

    // Check each segment of the polyline
    for i in 0..line_coords.len() - 1 {
        let (lon1, lat1) = line_coords[i];
        let (lon2, lat2) = line_coords[i + 1];

        let (dist, proj) = point_to_segment_distance(point_lat, point_lon, lat1, lon1, lat2, lon2);

        if dist < min_dist {
            min_dist = dist;
            best_projection = proj;
        }
    }

    (min_dist, best_projection)
}

/// Calculate shortest distance from a point to a single line segment
///
/// Uses projection onto the segment with geographic coordinate handling.
#[inline]
fn point_to_segment_distance(
    point_lat: f64,
    point_lon: f64,
    seg_lat1: f64,
    seg_lon1: f64,
    seg_lat2: f64,
    seg_lon2: f64,
) -> (f64, (f64, f64)) {
    // Convert to local Cartesian approximation for projection
    // This is accurate for small distances (< 100km)
    let cos_lat = ((point_lat + seg_lat1 + seg_lat2) / 3.0 * DEG_TO_RAD).cos();
    let meters_per_deg_lon = METERS_PER_DEG_LAT * cos_lat;

    // Convert to local meters
    let px = (point_lon - seg_lon1) * meters_per_deg_lon;
    let py = (point_lat - seg_lat1) * METERS_PER_DEG_LAT;

    let ax = 0.0;
    let ay = 0.0;
    let bx = (seg_lon2 - seg_lon1) * meters_per_deg_lon;
    let by = (seg_lat2 - seg_lat1) * METERS_PER_DEG_LAT;

    // Vector from A to B
    let ab_x = bx - ax;
    let ab_y = by - ay;

    // Vector from A to P
    let ap_x = px - ax;
    let ap_y = py - ay;

    // Project P onto AB
    let ab_len_sq = ab_x * ab_x + ab_y * ab_y;

    if ab_len_sq < 1e-10 {
        // Degenerate segment (zero length)
        let dist = haversine_distance(point_lat, point_lon, seg_lat1, seg_lon1);
        return (dist, (seg_lon1, seg_lat1));
    }

    // Parameter t for projection: 0 = at A, 1 = at B
    let t = ((ap_x * ab_x + ap_y * ab_y) / ab_len_sq).clamp(0.0, 1.0);

    // Projected point in local coordinates
    let proj_x = ax + t * ab_x;
    let proj_y = ay + t * ab_y;

    // Convert back to geographic coordinates
    let proj_lon = seg_lon1 + proj_x / meters_per_deg_lon;
    let proj_lat = seg_lat1 + proj_y / METERS_PER_DEG_LAT;

    // Calculate actual haversine distance for accuracy
    let dist = haversine_distance(point_lat, point_lon, proj_lat, proj_lon);

    (dist, (proj_lon, proj_lat))
}

// ============================================================================
// Bearing Calculations
// ============================================================================

/// Normalize bearing to [0, 360) range
#[inline]
pub fn normalize_bearing(bearing: f64) -> f64 {
    let mut b = bearing % 360.0;
    if b < 0.0 {
        b += 360.0;
    }
    b
}

/// Calculate smallest angular difference between two bearings (0-180 degrees)
#[inline]
pub fn angle_difference(bearing1: f64, bearing2: f64) -> f64 {
    let b1 = normalize_bearing(bearing1);
    let b2 = normalize_bearing(bearing2);
    let diff = (b1 - b2).abs();
    diff.min(360.0 - diff)
}

/// Calculate bearing from point 1 to point 2
pub fn calculate_bearing(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let lat1_rad = lat1 * DEG_TO_RAD;
    let lat2_rad = lat2 * DEG_TO_RAD;
    let dlon_rad = (lon2 - lon1) * DEG_TO_RAD;

    let x = dlon_rad.sin() * lat2_rad.cos();
    let y = lat1_rad.cos() * lat2_rad.sin() - lat1_rad.sin() * lat2_rad.cos() * dlon_rad.cos();

    let bearing_rad = x.atan2(y);
    normalize_bearing(bearing_rad * 180.0 / PI)
}

// ============================================================================
// Utility Functions
// ============================================================================

/// Convert geographic distance threshold to approximate degrees
#[inline]
pub fn meters_to_degrees_approx(meters: f64, latitude: f64) -> f64 {
    let cos_lat = (latitude * DEG_TO_RAD).cos();
    let meters_per_deg = METERS_PER_DEG_LAT * cos_lat.max(0.1);
    meters / meters_per_deg
}

/// Densify a linestring by adding intermediate points
pub fn densify_linestring(
    coords: &[(f64, f64)],
    interval_meters: f64,
    is_geographic: bool,
) -> Vec<(f64, f64)> {
    if coords.len() < 2 {
        return coords.to_vec();
    }

    let mut result = Vec::with_capacity(coords.len() * 4); // Pre-allocate

    for i in 0..coords.len() - 1 {
        let (lon1, lat1) = coords[i];
        let (lon2, lat2) = coords[i + 1];

        result.push((lon1, lat1));

        let segment_length = if is_geographic {
            haversine_distance(lat1, lon1, lat2, lon2)
        } else {
            ((lon2 - lon1).powi(2) + (lat2 - lat1).powi(2)).sqrt()
        };

        if segment_length > interval_meters {
            let n_points = (segment_length / interval_meters).ceil() as usize;
            for j in 1..n_points {
                let t = j as f64 / n_points as f64;
                let lon = lon1 + t * (lon2 - lon1);
                let lat = lat1 + t * (lat2 - lat1);
                result.push((lon, lat));
            }
        }
    }

    // Add last point
    if let Some(&last) = coords.last() {
        result.push(last);
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_haversine_same_point() {
        let dist = haversine_distance(0.0, 0.0, 0.0, 0.0);
        assert!(dist.abs() < 1e-10);
    }

    #[test]
    fn test_haversine_known_distance() {
        // Santiago, Chile to Valparaiso: ~120km
        let dist = haversine_distance(-33.4489, -70.6693, -33.0472, -71.6127);
        assert!((dist - 98_000.0).abs() < 5000.0); // Within 5km tolerance
    }

    #[test]
    fn test_bearing_normalization() {
        assert!((normalize_bearing(0.0) - 0.0).abs() < 1e-10);
        assert!((normalize_bearing(360.0) - 0.0).abs() < 1e-10);
        assert!((normalize_bearing(-90.0) - 270.0).abs() < 1e-10);
        assert!((normalize_bearing(450.0) - 90.0).abs() < 1e-10);
    }

    #[test]
    fn test_angle_difference() {
        assert!((angle_difference(0.0, 90.0) - 90.0).abs() < 1e-10);
        assert!((angle_difference(0.0, 180.0) - 180.0).abs() < 1e-10);
        assert!((angle_difference(10.0, 350.0) - 20.0).abs() < 1e-10);
        assert!((angle_difference(1.0, 359.0) - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_point_to_segment() {
        // Point perpendicular to segment midpoint
        let (dist, _proj) = point_to_segment_distance(
            0.001, 0.0,  // Point slightly north
            0.0, -0.001, // Segment from west
            0.0, 0.001,  // to east
        );
        // Distance should be approximately 111 meters (0.001 degrees latitude)
        assert!(dist > 100.0 && dist < 120.0);
    }
}
