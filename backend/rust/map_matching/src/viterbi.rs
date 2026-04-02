//! Viterbi algorithm for HMM map matching
//!
//! This module implements the core Viterbi algorithm for matching GPS trajectories
//! to road segments using a Hidden Markov Model approach.
//!
//! Optimizations:
//! - Pre-allocated buffers to avoid repeated allocations
//! - SmallVec for candidate lists (stack allocation for small sets)
//! - FxHashMap for faster integer key lookups
//! - Log-space probability calculations to avoid underflow

use rustc_hash::FxHashMap;
use smallvec::SmallVec;
use std::collections::HashSet;
use thiserror::Error;

use crate::geometry::{haversine_distance, normalize_bearing, point_to_line_distance};
use crate::probability::{emission_prob_log, transition_prob_log_with_direction};
use crate::spatial_index::SpatialIndex;

/// Maximum candidates to keep on stack (before heap allocation)
const MAX_STACK_CANDIDATES: usize = 16;

/// Candidate segment with projection info
type CandidateList = SmallVec<[Candidate; MAX_STACK_CANDIDATES]>;

/// Viterbi algorithm errors
#[derive(Error, Debug)]
pub enum ViterbiError {
    #[error("Empty trajectory")]
    EmptyTrajectory,
    #[error("Mismatched input lengths")]
    LengthMismatch,
}

/// Result of Viterbi map matching
#[derive(Debug, Clone)]
pub struct ViterbiResult {
    /// Matched segment PK for each GPS point (None if no match)
    pub matched_segments: Vec<Option<i64>>,

    /// Indices of GPS points that have valid matches
    pub valid_indices: Vec<usize>,

    /// Projected point (lon, lat) for each GPS point (None if no match)
    pub projected_points: Vec<Option<(f64, f64)>>,
}

/// A candidate segment for a GPS observation
#[derive(Debug, Clone)]
struct Candidate {
    segment_pk: i64,
    projected_point: (f64, f64), // (lon, lat)
    distance: f64,
    segment_bearing: Option<f64>,
}

/// Direction cache for precomputed direction group data
#[derive(Debug, Clone)]
pub struct DirectionCache {
    /// Map from segment PK to direction ID
    segment_to_direction: FxHashMap<i64, i32>,

    /// Unified line coordinates per direction (for route distance estimation)
    /// In a full implementation, this would store the merged geometry
    direction_segments: FxHashMap<i32, Vec<i64>>,
}

impl DirectionCache {
    /// Create direction cache from segment directions
    pub fn new(
        segment_pks: &[i64],
        directions: &[i32],
        _geometries: &[Vec<(f64, f64)>],
    ) -> Result<Self, ViterbiError> {
        if segment_pks.len() != directions.len() {
            return Err(ViterbiError::LengthMismatch);
        }

        let mut segment_to_direction = FxHashMap::with_capacity_and_hasher(
            segment_pks.len(),
            Default::default(),
        );

        let mut direction_segments: FxHashMap<i32, Vec<i64>> = FxHashMap::default();

        for (&pk, &dir) in segment_pks.iter().zip(directions.iter()) {
            segment_to_direction.insert(pk, dir);
            direction_segments.entry(dir).or_default().push(pk);
        }

        Ok(Self {
            segment_to_direction,
            direction_segments,
        })
    }

    /// Get direction for a segment
    #[inline]
    pub fn get_direction(&self, segment_pk: i64) -> Option<i32> {
        self.segment_to_direction.get(&segment_pk).copied()
    }

    /// Check if two segments are in the same direction
    #[inline]
    pub fn same_direction(&self, seg1: i64, seg2: i64) -> bool {
        match (self.get_direction(seg1), self.get_direction(seg2)) {
            (Some(d1), Some(d2)) => d1 == d2,
            _ => false, // Unknown direction = assume different
        }
    }
}

/// Segment cache for geometries and bearings
#[derive(Debug, Clone)]
pub struct SegmentCache {
    /// Segment geometries: pk -> [(lon, lat), ...]
    geometries: FxHashMap<i64, Vec<(f64, f64)>>,

    /// Segment bearings: pk -> bearing (normalized 0-360)
    bearings: FxHashMap<i64, Option<f64>>,
}

impl SegmentCache {
    /// Create segment cache from segment data
    pub fn new(
        segment_pks: &[i64],
        geometries: &[Vec<(f64, f64)>],
        bearings: &[Option<f64>],
    ) -> Result<Self, ViterbiError> {
        if segment_pks.len() != geometries.len() || segment_pks.len() != bearings.len() {
            return Err(ViterbiError::LengthMismatch);
        }

        let mut geom_map = FxHashMap::with_capacity_and_hasher(
            segment_pks.len(),
            Default::default(),
        );
        let mut bearing_map = FxHashMap::with_capacity_and_hasher(
            segment_pks.len(),
            Default::default(),
        );

        for ((&pk, geom), &bearing) in segment_pks.iter().zip(geometries.iter()).zip(bearings.iter())
        {
            geom_map.insert(pk, geom.clone());
            bearing_map.insert(pk, bearing.map(normalize_bearing));
        }

        Ok(Self {
            geometries: geom_map,
            bearings: bearing_map,
        })
    }

    /// Get geometry for a segment
    #[inline]
    pub fn get_geometry(&self, segment_pk: i64) -> Option<&Vec<(f64, f64)>> {
        self.geometries.get(&segment_pk)
    }

    /// Get bearing for a segment
    #[inline]
    pub fn get_bearing(&self, segment_pk: i64) -> Option<f64> {
        self.bearings.get(&segment_pk).copied().flatten()
    }
}

/// Run Viterbi HMM map matching algorithm
///
/// # Arguments
/// * `gps_lons` - GPS longitudes
/// * `gps_lats` - GPS latitudes
/// * `spatial_index` - Spatial index for segment lookup
/// * `direction_cache` - Direction cache for transition calculations
/// * `segment_cache` - Segment cache for geometry/bearing lookup
/// * `max_distance` - Maximum distance for candidate segments (meters)
/// * `sigma` - GPS measurement noise (meters)
/// * `beta` - Transition probability parameter
/// * `min_candidates` - Minimum candidates required for valid observation
/// * `gps_bearings` - Optional GPS bearings
/// * `sigma_bearing` - Bearing noise (degrees)
/// * `bearing_weight_factor` - Weight for bearing in emission probability
/// * `excluded_indices` - GPS indices to exclude from matching
///
/// # Returns
/// ViterbiResult with matched segments, valid indices, and projected points
pub fn viterbi_match(
    gps_lons: &[f64],
    gps_lats: &[f64],
    spatial_index: &SpatialIndex,
    direction_cache: &DirectionCache,
    segment_cache: &SegmentCache,
    max_distance: f64,
    sigma: f64,
    beta: f64,
    min_candidates: usize,
    gps_bearings: Option<&[Option<f64>]>,
    sigma_bearing: f64,
    bearing_weight_factor: f64,
    excluded_indices: Option<&[usize]>,
) -> ViterbiResult {
    let n_observations = gps_lons.len();

    // Early return for empty trajectory
    if n_observations == 0 {
        return ViterbiResult {
            matched_segments: vec![],
            valid_indices: vec![],
            projected_points: vec![],
        };
    }

    // Convert excluded indices to set for O(1) lookup
    let excluded: HashSet<usize> = excluded_indices
        .map(|e| e.iter().copied().collect())
        .unwrap_or_default();

    // Normalize GPS bearings once
    let normalized_bearings: Option<Vec<Option<f64>>> = gps_bearings.map(|bearings| {
        bearings
            .iter()
            .map(|b| b.map(normalize_bearing))
            .collect()
    });

    // ========================================================================
    // Step 1: Find candidates for each observation
    // ========================================================================

    let mut valid_observations: Vec<usize> = Vec::with_capacity(n_observations);
    let mut observation_mapping: FxHashMap<usize, usize> = FxHashMap::default();
    let mut filtered_candidates: Vec<CandidateList> = Vec::with_capacity(n_observations);

    for i in 0..n_observations {
        if excluded.contains(&i) {
            continue;
        }

        let lon = gps_lons[i];
        let lat = gps_lats[i];

        // Query spatial index for candidate segments
        let candidate_pks = spatial_index.query(lon, lat, max_distance);

        if candidate_pks.is_empty() {
            // Try fallback: get nearest segments
            let fallback_pks = spatial_index.nearest_k(lon, lat, 10);
            if fallback_pks.is_empty() {
                continue;
            }
        }

        // Build candidate list with projections
        let mut candidates: CandidateList = SmallVec::new();

        for seg_pk in candidate_pks {
            if let Some(geom) = segment_cache.get_geometry(seg_pk) {
                let (distance, (proj_lon, proj_lat)) =
                    point_to_line_distance(lat, lon, geom);

                if distance <= max_distance {
                    candidates.push(Candidate {
                        segment_pk: seg_pk,
                        projected_point: (proj_lon, proj_lat),
                        distance,
                        segment_bearing: segment_cache.get_bearing(seg_pk),
                    });
                }
            }
        }

        if candidates.len() >= min_candidates {
            observation_mapping.insert(valid_observations.len(), i);
            valid_observations.push(i);
            filtered_candidates.push(candidates);
        }
    }

    // Not enough valid observations
    if valid_observations.len() < min_candidates {
        return ViterbiResult {
            matched_segments: vec![None; n_observations],
            valid_indices: vec![],
            projected_points: vec![None; n_observations],
        };
    }

    let n_filtered = filtered_candidates.len();

    // ========================================================================
    // Step 2: Viterbi forward pass
    // ========================================================================

    // V[t][segment] = max log probability of reaching segment at time t
    let mut v: Vec<FxHashMap<i64, f64>> = vec![FxHashMap::default(); n_filtered];

    // path[t][segment] = best previous segment
    let mut path: Vec<FxHashMap<i64, Option<i64>>> = vec![FxHashMap::default(); n_filtered];

    // Initialize first observation
    let first_gps_idx = observation_mapping[&0];
    let first_gps_bearing = normalized_bearings
        .as_ref()
        .and_then(|b| b.get(first_gps_idx).copied())
        .flatten();

    for candidate in &filtered_candidates[0] {
        let emission = emission_prob_log(
            candidate.distance,
            sigma,
            first_gps_bearing,
            candidate.segment_bearing,
            sigma_bearing,
            bearing_weight_factor,
        );
        v[0].insert(candidate.segment_pk, emission);
        path[0].insert(candidate.segment_pk, None);
    }

    // Forward pass
    for t in 1..n_filtered {
        let curr_gps_idx = observation_mapping[&t];
        let prev_gps_idx = observation_mapping[&(t - 1)];

        let curr_gps_bearing = normalized_bearings
            .as_ref()
            .and_then(|b| b.get(curr_gps_idx).copied())
            .flatten();

        let curr_gps = (gps_lons[curr_gps_idx], gps_lats[curr_gps_idx]);
        let prev_gps = (gps_lons[prev_gps_idx], gps_lats[prev_gps_idx]);

        for curr_candidate in &filtered_candidates[t] {
            let emission = emission_prob_log(
                curr_candidate.distance,
                sigma,
                curr_gps_bearing,
                curr_candidate.segment_bearing,
                sigma_bearing,
                bearing_weight_factor,
            );

            let curr_direction = direction_cache.get_direction(curr_candidate.segment_pk);

            let mut max_log_prob = f64::NEG_INFINITY;
            let mut best_prev_seg: Option<i64> = None;

            for prev_candidate in &filtered_candidates[t - 1] {
                let prev_log_prob = v[t - 1]
                    .get(&prev_candidate.segment_pk)
                    .copied()
                    .unwrap_or(f64::NEG_INFINITY);

                if prev_log_prob == f64::NEG_INFINITY {
                    continue;
                }

                let prev_direction = direction_cache.get_direction(prev_candidate.segment_pk);
                let same_dir = match (prev_direction, curr_direction) {
                    (Some(d1), Some(d2)) => d1 == d2,
                    _ => false,
                };

                // Estimate route distance (simplified: use direct distance)
                let route_dist = haversine_distance(
                    prev_candidate.projected_point.1,
                    prev_candidate.projected_point.0,
                    curr_candidate.projected_point.1,
                    curr_candidate.projected_point.0,
                );

                let trans_log = transition_prob_log_with_direction(
                    prev_candidate.projected_point,
                    curr_candidate.projected_point,
                    prev_gps,
                    curr_gps,
                    beta,
                    route_dist,
                    same_dir,
                );

                let log_prob = prev_log_prob + trans_log + emission;

                if log_prob > max_log_prob {
                    max_log_prob = log_prob;
                    best_prev_seg = Some(prev_candidate.segment_pk);
                }
            }

            if max_log_prob > f64::NEG_INFINITY {
                v[t].insert(curr_candidate.segment_pk, max_log_prob);
                path[t].insert(curr_candidate.segment_pk, best_prev_seg);
            }
        }
    }

    // ========================================================================
    // Step 3: Backward pass - find best path
    // ========================================================================

    // Find best final segment
    let mut max_log_prob = f64::NEG_INFINITY;
    let mut best_last_segment: Option<i64> = None;

    for candidate in &filtered_candidates[n_filtered - 1] {
        if let Some(&prob) = v[n_filtered - 1].get(&candidate.segment_pk) {
            if prob > max_log_prob {
                max_log_prob = prob;
                best_last_segment = Some(candidate.segment_pk);
            }
        }
    }

    // Reconstruct path
    let mut filtered_result: Vec<Option<i64>> = vec![None; n_filtered];
    let mut filtered_projected: Vec<Option<(f64, f64)>> = vec![None; n_filtered];

    if let Some(last_seg) = best_last_segment {
        filtered_result[n_filtered - 1] = Some(last_seg);

        // Find projected point for last segment
        for candidate in &filtered_candidates[n_filtered - 1] {
            if candidate.segment_pk == last_seg {
                filtered_projected[n_filtered - 1] = Some(candidate.projected_point);
                break;
            }
        }

        // Backtrack
        for t in (0..n_filtered - 1).rev() {
            let next_seg = filtered_result[t + 1];

            let prev_seg = next_seg.and_then(|s| path[t + 1].get(&s).copied()).flatten();

            if let Some(seg) = prev_seg {
                filtered_result[t] = Some(seg);

                // Find projected point
                for candidate in &filtered_candidates[t] {
                    if candidate.segment_pk == seg {
                        filtered_projected[t] = Some(candidate.projected_point);
                        break;
                    }
                }
            } else {
                // Fallback: choose best by emission probability
                let gps_idx = observation_mapping[&t];
                let gps_bearing = normalized_bearings
                    .as_ref()
                    .and_then(|b| b.get(gps_idx).copied())
                    .flatten();

                let best = best_by_emission(&filtered_candidates[t], sigma, gps_bearing, sigma_bearing, bearing_weight_factor);
                filtered_result[t] = best.map(|c| c.segment_pk);
                filtered_projected[t] = best.map(|c| c.projected_point);
            }
        }
    } else {
        // Complete fallback: choose best by emission for each timestep
        for t in 0..n_filtered {
            let gps_idx = observation_mapping[&t];
            let gps_bearing = normalized_bearings
                .as_ref()
                .and_then(|b| b.get(gps_idx).copied())
                .flatten();

            let best = best_by_emission(&filtered_candidates[t], sigma, gps_bearing, sigma_bearing, bearing_weight_factor);
            filtered_result[t] = best.map(|c| c.segment_pk);
            filtered_projected[t] = best.map(|c| c.projected_point);
        }
    }

    // ========================================================================
    // Step 4: Map back to original indices
    // ========================================================================

    let mut full_result: Vec<Option<i64>> = vec![None; n_observations];
    let mut full_projected: Vec<Option<(f64, f64)>> = vec![None; n_observations];

    for (filtered_idx, &original_idx) in observation_mapping.iter() {
        full_result[original_idx] = filtered_result[*filtered_idx];
        full_projected[original_idx] = filtered_projected[*filtered_idx];
    }

    ViterbiResult {
        matched_segments: full_result,
        valid_indices: valid_observations,
        projected_points: full_projected,
    }
}

/// Find best candidate by emission probability alone
fn best_by_emission<'a>(
    candidates: &'a CandidateList,
    sigma: f64,
    gps_bearing: Option<f64>,
    sigma_bearing: f64,
    bearing_weight_factor: f64,
) -> Option<&'a Candidate> {
    candidates
        .iter()
        .max_by(|a, b| {
            let prob_a = emission_prob_log(
                a.distance,
                sigma,
                gps_bearing,
                a.segment_bearing,
                sigma_bearing,
                bearing_weight_factor,
            );
            let prob_b = emission_prob_log(
                b.distance,
                sigma,
                gps_bearing,
                b.segment_bearing,
                sigma_bearing,
                bearing_weight_factor,
            );
            prob_a.partial_cmp(&prob_b).unwrap_or(std::cmp::Ordering::Equal)
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_caches() -> (SpatialIndex, DirectionCache, SegmentCache) {
        // Create simple test data: 3 parallel road segments
        let segment_pks = vec![1, 2, 3];
        let directions = vec![0, 0, 0]; // All same direction
        let geometries = vec![
            vec![(-70.66, -33.45), (-70.65, -33.45)], // Segment 1
            vec![(-70.65, -33.45), (-70.64, -33.45)], // Segment 2
            vec![(-70.64, -33.45), (-70.63, -33.45)], // Segment 3
        ];
        let bearings = vec![Some(90.0), Some(90.0), Some(90.0)];

        let spatial_index = SpatialIndex::new(&segment_pks, &geometries, 20.0, true).unwrap();
        let direction_cache = DirectionCache::new(&segment_pks, &directions, &geometries).unwrap();
        let segment_cache = SegmentCache::new(&segment_pks, &geometries, &bearings).unwrap();

        (spatial_index, direction_cache, segment_cache)
    }

    #[test]
    fn test_viterbi_simple_trajectory() {
        let (spatial_index, direction_cache, segment_cache) = create_test_caches();

        // GPS trajectory along the road
        let gps_lons = vec![-70.658, -70.648, -70.638];
        let gps_lats = vec![-33.4501, -33.4501, -33.4501];

        let result = viterbi_match(
            &gps_lons,
            &gps_lats,
            &spatial_index,
            &direction_cache,
            &segment_cache,
            200.0,
            25.0,
            40.0,
            1,
            None,
            30.0,
            0.5,
            None,
        );

        // Should have valid matches
        assert!(!result.valid_indices.is_empty());

        // Segments should be matched in order
        let matched: Vec<_> = result.matched_segments.iter().flatten().collect();
        assert!(!matched.is_empty());
    }

    #[test]
    fn test_viterbi_empty_trajectory() {
        let (spatial_index, direction_cache, segment_cache) = create_test_caches();

        let result = viterbi_match(
            &[],
            &[],
            &spatial_index,
            &direction_cache,
            &segment_cache,
            200.0,
            25.0,
            40.0,
            2,
            None,
            30.0,
            0.5,
            None,
        );

        assert!(result.matched_segments.is_empty());
        assert!(result.valid_indices.is_empty());
    }

    #[test]
    fn test_viterbi_with_bearings() {
        let (spatial_index, direction_cache, segment_cache) = create_test_caches();

        let gps_lons = vec![-70.658, -70.648, -70.638];
        let gps_lats = vec![-33.4501, -33.4501, -33.4501];
        let gps_bearings = vec![Some(90.0), Some(90.0), Some(90.0)];

        let result = viterbi_match(
            &gps_lons,
            &gps_lats,
            &spatial_index,
            &direction_cache,
            &segment_cache,
            200.0,
            25.0,
            40.0,
            1,
            Some(&gps_bearings),
            30.0,
            0.5,
            None,
        );

        // Bearing should improve matching
        assert!(!result.valid_indices.is_empty());
    }
}
