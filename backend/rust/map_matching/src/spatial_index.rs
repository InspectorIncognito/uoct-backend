//! Spatial indexing for efficient segment lookup
//!
//! Uses a KD-tree built from densified segment points for fast
//! nearest-neighbor queries. Optimized for memory efficiency
//! using f32 coordinates internally.

use kiddo::float::kdtree::KdTree;
use kiddo::SquaredEuclidean;
use std::collections::HashSet;
use thiserror::Error;

use crate::geometry::{densify_linestring, haversine_distance, meters_to_degrees_approx};

/// Spatial index errors
#[derive(Error, Debug)]
pub enum SpatialIndexError {
    #[error("No segments provided")]
    EmptySegments,
    #[error("Segment count mismatch: {0} pks vs {1} geometries")]
    CountMismatch(usize, usize),
    #[error("Failed to build KD-tree: {0}")]
    TreeBuildError(String),
}

/// Spatial index for efficient segment lookup
///
/// Internally uses f32 coordinates to reduce memory footprint
/// while maintaining sufficient precision for map matching.
pub struct SpatialIndex {
    /// KD-tree for spatial queries (2D: lon, lat in degrees)
    tree: KdTree<f32, 2>,

    /// Segment PK for each indexed point
    segment_ids: Vec<i64>,

    /// Original coordinates for each indexed point (for precise distance calc)
    coords: Vec<(f32, f32)>,

    /// Whether coordinates are geographic (degrees) or projected (meters)
    pub is_geographic: bool,
}

impl SpatialIndex {
    /// Create a new spatial index from segment data
    ///
    /// # Arguments
    /// * `segment_pks` - Primary keys for each segment
    /// * `geometries` - LineString coordinates for each segment [(lon, lat), ...]
    /// * `interval` - Densification interval in meters
    /// * `is_geographic` - Whether coordinates are in degrees (true) or meters (false)
    pub fn new(
        segment_pks: &[i64],
        geometries: &[Vec<(f64, f64)>],
        interval: f64,
        is_geographic: bool,
    ) -> Result<Self, SpatialIndexError> {
        if segment_pks.is_empty() {
            return Err(SpatialIndexError::EmptySegments);
        }

        if segment_pks.len() != geometries.len() {
            return Err(SpatialIndexError::CountMismatch(
                segment_pks.len(),
                geometries.len(),
            ));
        }

        // Pre-calculate capacity
        let estimated_points: usize = geometries.iter().map(|g| g.len() * 4).sum();

        let mut segment_ids = Vec::with_capacity(estimated_points);
        let mut coords = Vec::with_capacity(estimated_points);

        // Densify each segment and collect points
        for (pk, geom) in segment_pks.iter().zip(geometries.iter()) {
            if geom.is_empty() {
                continue;
            }

            let densified = densify_linestring(geom, interval, is_geographic);

            for (lon, lat) in densified {
                segment_ids.push(*pk);
                coords.push((lon as f32, lat as f32));
            }
        }

        if coords.is_empty() {
            return Err(SpatialIndexError::EmptySegments);
        }

        // Build KD-tree
        let mut tree: KdTree<f32, 2> = KdTree::with_capacity(coords.len());

        for (idx, &(lon, lat)) in coords.iter().enumerate() {
            tree.add(&[lon, lat], idx as u64);
        }

        Ok(Self {
            tree,
            segment_ids,
            coords,
            is_geographic,
        })
    }

    /// Query segments within a radius of a point
    ///
    /// # Arguments
    /// * `lon` - Query longitude
    /// * `lat` - Query latitude
    /// * `max_distance` - Maximum distance in meters
    ///
    /// # Returns
    /// Unique segment PKs within the radius
    pub fn query(&self, lon: f64, lat: f64, max_distance: f64) -> Vec<i64> {
        let radius_deg = if self.is_geographic {
            meters_to_degrees_approx(max_distance, lat)
        } else {
            max_distance
        };

        // KDTree uses squared Euclidean distance
        let radius_sq = (radius_deg * radius_deg) as f32;

        let neighbors = self
            .tree
            .within::<SquaredEuclidean>(&[lon as f32, lat as f32], radius_sq);

        // Collect unique segment IDs
        let mut seen = HashSet::with_capacity(neighbors.len());
        let mut result = Vec::with_capacity(neighbors.len());

        for neighbor in neighbors {
            let idx = neighbor.item as usize;
            let seg_pk = self.segment_ids[idx];

            if seen.insert(seg_pk) {
                result.push(seg_pk);
            }
        }

        result
    }

    /// Query segments with approximate distances
    ///
    /// Returns (segment_pk, approximate_distance) pairs sorted by distance.
    pub fn query_with_distances(
        &self,
        lon: f64,
        lat: f64,
        max_distance: f64,
    ) -> Vec<(i64, f64)> {
        let radius_deg = if self.is_geographic {
            meters_to_degrees_approx(max_distance, lat)
        } else {
            max_distance
        };

        let radius_sq = (radius_deg * radius_deg) as f32;

        let neighbors = self
            .tree
            .within::<SquaredEuclidean>(&[lon as f32, lat as f32], radius_sq);

        // Track best distance per segment
        let mut best_dist: rustc_hash::FxHashMap<i64, f64> =
            rustc_hash::FxHashMap::with_capacity_and_hasher(
                neighbors.len(),
                Default::default(),
            );

        for neighbor in neighbors {
            let idx = neighbor.item as usize;
            let seg_pk = self.segment_ids[idx];
            let (p_lon, p_lat) = self.coords[idx];

            // Calculate actual haversine distance
            let dist = if self.is_geographic {
                haversine_distance(lat, lon, p_lat as f64, p_lon as f64)
            } else {
                ((lon - p_lon as f64).powi(2) + (lat - p_lat as f64).powi(2)).sqrt()
            };

            best_dist
                .entry(seg_pk)
                .and_modify(|d| {
                    if dist < *d {
                        *d = dist;
                    }
                })
                .or_insert(dist);
        }

        let mut result: Vec<_> = best_dist.into_iter().collect();
        result.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));

        result
    }

    /// Find k-nearest segments to a point
    ///
    /// Useful as fallback when no segments are within max_distance.
    pub fn nearest_k(&self, lon: f64, lat: f64, k: usize) -> Vec<i64> {
        let neighbors = self
            .tree
            .nearest_n::<SquaredEuclidean>(&[lon as f32, lat as f32], k);

        let mut seen = HashSet::with_capacity(k);
        let mut result = Vec::with_capacity(k);

        for neighbor in neighbors {
            let idx = neighbor.item as usize;
            let seg_pk = self.segment_ids[idx];

            if seen.insert(seg_pk) {
                result.push(seg_pk);
            }
        }

        result
    }

    /// Get number of indexed points
    pub fn len(&self) -> usize {
        self.coords.len()
    }

    /// Check if index is empty
    pub fn is_empty(&self) -> bool {
        self.coords.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_segments() -> (Vec<i64>, Vec<Vec<(f64, f64)>>) {
        let pks = vec![1, 2, 3];
        let geoms = vec![
            vec![(-70.66, -33.44), (-70.65, -33.44)], // ~900m east-west
            vec![(-70.66, -33.45), (-70.66, -33.44)], // ~1100m north-south
            vec![(-70.64, -33.44), (-70.63, -33.44)], // ~900m further east
        ];
        (pks, geoms)
    }

    #[test]
    fn test_index_creation() {
        let (pks, geoms) = sample_segments();
        let index = SpatialIndex::new(&pks, &geoms, 20.0, true).unwrap();
        assert!(!index.is_empty());
    }

    #[test]
    fn test_query_near_segment() {
        let (pks, geoms) = sample_segments();
        let index = SpatialIndex::new(&pks, &geoms, 20.0, true).unwrap();

        // Query near segment 1
        let results = index.query(-70.655, -33.44, 500.0);
        assert!(results.contains(&1));
    }

    #[test]
    fn test_query_far_from_segments() {
        let (pks, geoms) = sample_segments();
        let index = SpatialIndex::new(&pks, &geoms, 20.0, true).unwrap();

        // Query far away - should return empty
        let results = index.query(-71.0, -33.0, 100.0);
        assert!(results.is_empty());
    }

    #[test]
    fn test_nearest_k() {
        let (pks, geoms) = sample_segments();
        let index = SpatialIndex::new(&pks, &geoms, 20.0, true).unwrap();

        // Should find closest segments even if far
        let results = index.nearest_k(-70.65, -33.44, 2);
        assert!(!results.is_empty());
    }
}
