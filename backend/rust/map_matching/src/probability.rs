//! Probability calculations for HMM map matching
//!
//! Implements emission and transition probabilities based on:
//! "Hidden Markov Map Matching Through Noise and Sparseness" by Newson and Krumm
//!
//! All probabilities are computed in log-space to avoid numerical underflow.

use std::f64::consts::PI;

use crate::geometry::{angle_difference, haversine_distance};

/// Pre-computed constant: -0.5 * ln(2 * pi)
const LOG_2PI_HALF: f64 = -0.5 * 1.8378770664093453; // -0.5 * ln(2*pi)

// ============================================================================
// Emission Probability
// ============================================================================

/// Calculate log emission probability
///
/// The emission probability models the likelihood of observing a GPS point
/// given that the vehicle is at a particular road segment position.
///
/// Uses a Gaussian distribution for distance with optional bearing weight.
///
/// # Arguments
/// * `distance` - Distance from GPS point to candidate segment (meters)
/// * `sigma` - GPS measurement noise standard deviation (meters)
/// * `gps_bearing` - Optional GPS heading (degrees)
/// * `segment_bearing` - Optional segment bearing (degrees)
/// * `sigma_bearing` - Bearing measurement noise standard deviation (degrees)
/// * `bearing_weight_factor` - Weight for bearing component (0-1)
///
/// # Returns
/// Log probability (negative value, higher = more likely)
#[inline]
pub fn emission_prob_log(
    distance: f64,
    sigma: f64,
    gps_bearing: Option<f64>,
    segment_bearing: Option<f64>,
    sigma_bearing: f64,
    bearing_weight_factor: f64,
) -> f64 {
    // Pre-compute sigma squared
    let sigma_sq = sigma * sigma;

    // Log of Gaussian probability for distance
    // log(1/(sqrt(2*pi)*sigma) * exp(-d^2/(2*sigma^2)))
    // = -0.5*log(2*pi) - log(sigma) - d^2/(2*sigma^2)
    let log_base_prob = LOG_2PI_HALF - sigma.ln() - (distance * distance) / (2.0 * sigma_sq);

    // Add bearing component if both bearings are available
    match (gps_bearing, segment_bearing) {
        (Some(gps_b), Some(seg_b)) => {
            let angle_diff = angle_difference(gps_b, seg_b);
            let sigma_b_sq = sigma_bearing * sigma_bearing;

            let log_bearing_prob =
                LOG_2PI_HALF - sigma_bearing.ln() - (angle_diff * angle_diff) / (2.0 * sigma_b_sq);

            log_base_prob + bearing_weight_factor * log_bearing_prob
        }
        _ => log_base_prob,
    }
}

/// Batch emission probability calculation
///
/// Optimized for multiple candidates at the same GPS point.
pub fn emission_prob_log_batch(
    distances: &[f64],
    sigma: f64,
    gps_bearing: Option<f64>,
    segment_bearings: &[Option<f64>],
    sigma_bearing: f64,
    bearing_weight_factor: f64,
) -> Vec<f64> {
    let sigma_sq = sigma * sigma;
    let sigma_term = LOG_2PI_HALF - sigma.ln();

    let sigma_b_sq = sigma_bearing * sigma_bearing;
    let sigma_b_term = LOG_2PI_HALF - sigma_bearing.ln();

    distances
        .iter()
        .zip(segment_bearings.iter())
        .map(|(&dist, seg_bearing)| {
            let log_base = sigma_term - (dist * dist) / (2.0 * sigma_sq);

            match (gps_bearing, seg_bearing) {
                (Some(gps_b), Some(seg_b)) => {
                    let angle_diff = angle_difference(gps_b, *seg_b);
                    let log_bearing = sigma_b_term - (angle_diff * angle_diff) / (2.0 * sigma_b_sq);
                    log_base + bearing_weight_factor * log_bearing
                }
                _ => log_base,
            }
        })
        .collect()
}

// ============================================================================
// Transition Probability
// ============================================================================

/// Calculate log transition probability
///
/// The transition probability models the likelihood of transitioning from
/// one road segment to another between consecutive GPS observations.
///
/// Uses an exponential distribution based on the difference between
/// great-circle distance and route distance.
///
/// # Arguments
/// * `prev_proj` - Previous projected point (lon, lat)
/// * `curr_proj` - Current projected point (lon, lat)
/// * `prev_gps` - Previous GPS point (lon, lat)
/// * `curr_gps` - Current GPS point (lon, lat)
/// * `beta` - Transition probability parameter
/// * `same_direction` - Whether segments are in the same direction group
///
/// # Returns
/// Log probability (negative value, higher = more likely)
#[inline]
pub fn transition_prob_log(
    prev_proj: (f64, f64),
    curr_proj: (f64, f64),
    prev_gps: (f64, f64),
    curr_gps: (f64, f64),
    beta: f64,
    route_distance: f64,
) -> f64 {
    // Great circle distance between GPS points
    let great_circle_dist = haversine_distance(prev_gps.1, prev_gps.0, curr_gps.1, curr_gps.0);

    // Difference between actual travel and GPS movement
    let distance_diff = (great_circle_dist - route_distance).abs();

    // Exponential distribution: P(d) = (1/beta) * exp(-d/beta)
    // log(P(d)) = -log(beta) - d/beta
    -beta.ln() - distance_diff / beta
}

/// Calculate transition probability with direction penalty
///
/// Adds a penalty when transitioning between different direction groups.
#[inline]
pub fn transition_prob_log_with_direction(
    prev_proj: (f64, f64),
    curr_proj: (f64, f64),
    prev_gps: (f64, f64),
    curr_gps: (f64, f64),
    beta: f64,
    route_distance: f64,
    same_direction: bool,
) -> f64 {
    if !same_direction {
        // Heavy penalty for cross-direction transitions
        // log(0.01) ≈ -4.605
        return -4.605;
    }

    transition_prob_log(prev_proj, curr_proj, prev_gps, curr_gps, beta, route_distance)
}

/// Calculate route distance between two projected points
///
/// For points on the same segment or adjacent segments, this uses
/// the projected distance along the unified direction line.
#[inline]
pub fn route_distance_estimate(
    prev_proj: (f64, f64),
    curr_proj: (f64, f64),
    prev_segment: i64,
    curr_segment: i64,
) -> f64 {
    if prev_segment == curr_segment {
        // Same segment: use direct distance between projections
        haversine_distance(prev_proj.1, prev_proj.0, curr_proj.1, curr_proj.0)
    } else {
        // Different segments: estimate via direct distance
        // (Full graph-based routing would be more accurate but expensive)
        haversine_distance(prev_proj.1, prev_proj.0, curr_proj.1, curr_proj.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_emission_prob_zero_distance() {
        // Zero distance should give highest probability
        let prob = emission_prob_log(0.0, 25.0, None, None, 30.0, 0.5);
        assert!(prob > -5.0); // Should be close to max
    }

    #[test]
    fn test_emission_prob_increases_with_distance() {
        let prob_close = emission_prob_log(10.0, 25.0, None, None, 30.0, 0.5);
        let prob_far = emission_prob_log(100.0, 25.0, None, None, 30.0, 0.5);
        assert!(prob_close > prob_far);
    }

    #[test]
    fn test_emission_prob_with_bearing() {
        // Good bearing match should increase probability
        let prob_good = emission_prob_log(10.0, 25.0, Some(45.0), Some(45.0), 30.0, 0.5);
        let prob_bad = emission_prob_log(10.0, 25.0, Some(45.0), Some(135.0), 30.0, 0.5);
        assert!(prob_good > prob_bad);
    }

    #[test]
    fn test_transition_prob_same_point() {
        let prob = transition_prob_log(
            (0.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
            25.0,
            0.0,
        );
        // Should be high (close to -log(beta))
        assert!(prob > -5.0);
    }

    #[test]
    fn test_transition_prob_direction_penalty() {
        let prob_same = transition_prob_log_with_direction(
            (0.0, 0.0),
            (0.001, 0.001),
            (0.0, 0.0),
            (0.001, 0.001),
            25.0,
            100.0,
            true,
        );
        let prob_diff = transition_prob_log_with_direction(
            (0.0, 0.0),
            (0.001, 0.001),
            (0.0, 0.0),
            (0.001, 0.001),
            25.0,
            100.0,
            false,
        );
        assert!(prob_same > prob_diff);
        assert!(prob_diff < -4.0); // Should be heavily penalized
    }
}
