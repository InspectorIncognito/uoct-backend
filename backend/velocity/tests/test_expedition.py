"""
Tests for ExpeditionData._get_stationary_indices and calculate_speed
focusing on:
  - stationary filtering logic
  - non-monotonic distance handling
  - small negative delta (formerly clamped to 0, now skipped)
  - bare ValueError messages
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from backend.velocity.expedition import ExpeditionData
from backend.velocity.gps import GPSPulse as GPS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTC = timezone.utc


def make_gps(lat: float, lon: float, offset_seconds: int) -> GPS:
    """Create a GPS pulse at a fixed base time + offset_seconds."""
    ts = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return GPS(timestamp=ts, bearing=0.0, latitude=lat, longitude=lon)


def make_expedition(route_id: str | None = None) -> ExpeditionData:
    """Create an ExpeditionData with a mocked GridManager."""
    grid_manager = MagicMock()
    ts = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
    exp = ExpeditionData(
        grid_manager=grid_manager,
        route_id=route_id,
        timestamp=ts,
        license_plate="TEST00",
    )
    return exp


# ---------------------------------------------------------------------------
# _get_stationary_indices
# ---------------------------------------------------------------------------


class TestGetStationaryIndices(SimpleTestCase):
    """Unit tests for _get_stationary_indices."""

    # ------------------------------------------------------------------
    # Route guard
    # ------------------------------------------------------------------

    def test_routed_expedition_never_filtered(self):
        """Expeditions with a valid route_id always return an empty set."""
        exp = make_expedition(route_id="101I")
        for i in range(10):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 60))
        # All distances the same → would normally be flagged as stationary
        exp.gps_distance_on_route = [0.0] * 10
        result = exp._get_stationary_indices()
        self.assertEqual(result, set())

    def test_nan_string_route_id_is_treated_as_no_route(self):
        """route_id='nan' (pandas category artifact) should be treated as unrouted."""
        exp = make_expedition(route_id="nan")
        for i in range(4):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 120))
        # Stationary for 6 min (> 5 min threshold)
        exp.gps_distance_on_route = [100.0, 100.0, 100.0, 100.0]
        result = exp._get_stationary_indices()
        self.assertGreater(len(result), 0)

    def test_none_route_id_is_treated_as_no_route(self):
        """route_id=None should be treated as unrouted."""
        exp = make_expedition(route_id=None)
        for i in range(4):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 120))
        exp.gps_distance_on_route = [100.0, 100.0, 100.0, 100.0]
        result = exp._get_stationary_indices()
        self.assertGreater(len(result), 0)

    # ------------------------------------------------------------------
    # Under-threshold stops
    # ------------------------------------------------------------------

    def test_short_stop_not_flagged(self):
        """A stop shorter than MAXIMUM_STATIONARY_TIME is not flagged."""
        exp = make_expedition(route_id=None)
        # 4 points, 60 s apart → 3 min total < 5 min threshold
        for i in range(4):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 60))
        exp.gps_distance_on_route = [100.0, 100.0, 100.0, 100.0]
        result = exp._get_stationary_indices()
        self.assertEqual(result, set())

    def test_exactly_at_threshold_not_flagged(self):
        """Elapsed time exactly equal to MAXIMUM_STATIONARY_TIME triggers the filter."""
        # MAXIMUM_STATIONARY_TIME = 300 s
        # Points at t=0, t=100, t=200, t=300 → elapsed at index 3 = 300 s
        exp = make_expedition(route_id=None)
        for i in range(4):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 100))
        exp.gps_distance_on_route = [100.0, 100.0, 100.0, 100.0]
        result = exp._get_stationary_indices()
        # elapsed == 300 satisfies `>= max_stationary`, so indices 0 and 3 are excluded
        self.assertIn(0, result)
        self.assertIn(3, result)

    # ------------------------------------------------------------------
    # Start index is included
    # ------------------------------------------------------------------

    def test_stationary_start_index_is_included(self):
        """The first index of a stationary period must be included once the threshold is exceeded."""
        exp = make_expedition(route_id=None)
        # 6 points, 120 s apart → after index 3 elapsed = 360 s > 300 s
        for i in range(6):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 120))
        exp.gps_distance_on_route = [500.0, 500.5, 500.5, 500.5, 500.5, 500.5]
        result = exp._get_stationary_indices()
        # stationary_start_idx = 1 (first point where delta < threshold)
        # threshold exceeded at i=3 (elapsed = 240 s) → NO, at i=3 elapsed=240 < 300
        # threshold exceeded at i=4 (elapsed = 360 s > 300 s)
        # → full range [1, 2, 3, 4] must be excluded
        self.assertIn(1, result, "Start index of stationary period must be excluded")
        self.assertIn(2, result, "Intermediate index must be excluded")
        self.assertIn(3, result, "Intermediate index must be excluded")
        self.assertIn(
            4, result, "Index where threshold is first crossed must be excluded"
        )

    def test_all_stationary_indices_after_threshold_included(self):
        """Every index from the start of the stationary period through the end is excluded."""
        exp = make_expedition(route_id=None)
        # 8 points × 120 s apart = 840 s total, all at the same distance.
        # stationary_start_idx = 0, threshold first crossed at i=3 (elapsed=360 s).
        # Expected excluded set: {0, 1, 2, 3, 4, 5, 6, 7}
        n = 8
        for i in range(n):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 120))
        exp.gps_distance_on_route = [1000.0] * n
        result = exp._get_stationary_indices()
        for i in range(n):
            self.assertIn(i, result, f"Index {i} should be excluded")

    # ------------------------------------------------------------------
    # None gaps reset tracking
    # ------------------------------------------------------------------

    def test_none_gap_resets_stationary_tracking(self):
        """A None in gps_distance_on_route resets the stationary period."""
        exp = make_expedition(route_id=None)
        # Two separate 4-min stops, separated by a None gap
        # First stop: indices 0–3, total elapsed = 240 s < 300 s → not flagged
        # Gap at index 4
        # Second stop: indices 5–8, total elapsed = 240 s < 300 s → not flagged
        for i in range(9):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 60))
        exp.gps_distance_on_route = [
            100.0,
            100.0,
            100.0,
            100.0,  # 0-3: 3 min stop
            None,  # 4: gap
            200.0,
            200.0,
            200.0,
            200.0,  # 5-8: second 3 min stop
        ]
        result = exp._get_stationary_indices()
        self.assertEqual(result, set(), "Neither stop exceeds threshold after reset")

    def test_long_stop_split_by_none_gap_hides_stop(self):
        """
        A stop > 5 min split by a None gap will not be flagged because the timer
        is reset. This documents the known limitation (see TODO in source).
        """
        exp = make_expedition(route_id=None)
        # 4-min stop, then a None, then another 4-min stop (8 min total but reset)
        times = [0, 60, 120, 180, 240, 300, 360, 420, 480]
        for t in times:
            exp.gps_points.append(make_gps(0.0, 0.0, t))
        exp.gps_distance_on_route = [
            100.0,
            100.0,
            100.0,
            100.0,  # 4 min at 100m
            None,  # gap resets timer
            100.0,
            100.0,
            100.0,
            100.0,  # another 4 min at 100m
        ]
        result = exp._get_stationary_indices()
        # Known limitation: gap resets timer, so despite 8 total stationary
        # minutes, nothing is flagged.
        self.assertEqual(result, set())

    # ------------------------------------------------------------------
    # Movement resets tracking
    # ------------------------------------------------------------------

    def test_movement_resets_stationary_period(self):
        """Movement > MINIMUM_MOVEMENT_THRESHOLD resets the stationary timer."""
        exp = make_expedition(route_id=None)
        # 3 min stop, then movement, then another 3 min stop
        for i in range(7):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 60))
        exp.gps_distance_on_route = [
            100.0,
            100.0,
            100.0,  # 3 min stop
            200.0,  # movement of 100 m → reset
            200.0,
            200.0,
            200.0,  # 3 min stop again
        ]
        result = exp._get_stationary_indices()
        self.assertEqual(result, set(), "Neither 3-min stop should be flagged")

    def test_continuous_stop_over_threshold_flagged(self):
        """A single continuous stop > 5 min is fully flagged."""
        exp = make_expedition(route_id=None)
        # 7 points × 60 s = 6 min total at the same distance
        for i in range(7):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 60))
        exp.gps_distance_on_route = [100.0] * 7
        result = exp._get_stationary_indices()
        self.assertIn(0, result)
        self.assertIn(5, result)
        self.assertIn(6, result)


# ---------------------------------------------------------------------------
# calculate_speed — non-monotonic distance handling
# ---------------------------------------------------------------------------


class TestCalculateSpeedNonMonotonic(SimpleTestCase):
    """
    Tests for the non-monotonic distance handling in calculate_speed.
    Uses a mock SegmentCriteria so we never need a real GridManager or DB.
    """

    def _make_segment_criteria_mock(self):
        """Return a SegmentCriteria mock that returns predictable segments."""
        from velocity.segment import TemporalSegment, SpatialSegment

        sc = MagicMock()
        # Fixed temporal and spatial segments so same-segment path is taken
        ts = TemporalSegment(
            index=32,
            start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 15, 8, 15, 0, tzinfo=UTC),
        )
        ss = SpatialSegment(index=2, start_distance=1000, end_distance=1500)
        sc.get_temporal_segment.return_value = ts
        sc.get_spatial_segment.return_value = ss
        sc.get_day_type.return_value = "L"
        return sc

    def _make_routed_exp_with_distances(self, distances: list) -> ExpeditionData:
        """
        Build an ExpeditionData with a valid route_id and the given
        gps_distance_on_route list. GPS points are 30 s apart.
        """
        exp = make_expedition(route_id="101I")
        exp.shape_id = "shape_1"
        for i, _ in enumerate(distances):
            exp.gps_points.append(make_gps(0.0, 0.0, i * 30))
        exp.gps_distance_on_route = distances
        return exp

    @patch("velocity.expedition.get_current_timezone")
    def test_large_negative_delta_is_skipped(self, mock_tz):
        """delta_distance < NON_MONOTONIC_DISTANCE_THRESHOLD produces no speed row."""
        mock_tz.return_value = UTC
        sc = self._make_segment_criteria_mock()
        # Distance drops by 200 m (well below -50 threshold)
        exp = self._make_routed_exp_with_distances([1000.0, 800.0, 850.0])
        rows = exp.calculate_speed(sc, local_timezone=UTC)
        # The drop (1000→800) is skipped; only 800→850 should produce a row
        self.assertEqual(len(rows), 1)
        self.assertEqual(exp.ignored_segments_because_non_monotonic, 1)

    @patch("velocity.expedition.get_current_timezone")
    def test_small_negative_delta_is_skipped_not_clamped(self, mock_tz):
        """
        delta_distance in (-50, 0) must be skipped (not produce a zero-distance row).
        Previously these were clamped to 0, biasing speed averages downward.
        """
        mock_tz.return_value = UTC
        sc = self._make_segment_criteria_mock()
        # Tiny backwards jitter: -3 m (HMM noise)
        exp = self._make_routed_exp_with_distances([1000.0, 997.0, 1050.0])
        rows = exp.calculate_speed(sc, local_timezone=UTC)
        # 1000→997 = -3 m → skipped; 997→1050 = +53 m → one row
        self.assertEqual(len(rows), 1)
        self.assertEqual(exp.ignored_segments_because_non_monotonic, 1)
        # The one row must have a positive distance
        self.assertGreater(rows[0]["distance_mts"], 0)

    @patch("velocity.expedition.get_current_timezone")
    def test_zero_distance_not_in_output(self, mock_tz):
        """No speed row should have distance_mts == 0 due to clamping."""
        mock_tz.return_value = UTC
        sc = self._make_segment_criteria_mock()
        # Mix of small negative deltas and a valid forward step
        distances = [1000.0, 999.5, 999.0, 1100.0]
        exp = self._make_routed_exp_with_distances(distances)
        rows = exp.calculate_speed(sc, local_timezone=UTC)
        for row in rows:
            self.assertGreater(
                row["distance_mts"],
                0,
                "No row should have distance_mts == 0 (clamping was removed)",
            )

    @patch("velocity.expedition.get_current_timezone")
    def test_positive_delta_produces_row(self, mock_tz):
        """A straightforward forward step produces exactly one speed row."""
        mock_tz.return_value = UTC
        sc = self._make_segment_criteria_mock()
        exp = self._make_routed_exp_with_distances([1000.0, 1100.0])
        rows = exp.calculate_speed(sc, local_timezone=UTC)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["distance_mts"], 100.0)
        self.assertEqual(exp.ignored_segments_because_non_monotonic, 0)

    @patch("velocity.expedition.get_current_timezone")
    def test_non_monotonic_counter_accumulates(self, mock_tz):
        """ignored_segments_because_non_monotonic increments for every skipped segment."""
        mock_tz.return_value = UTC
        sc = self._make_segment_criteria_mock()
        # Three backward steps of varying sizes
        exp = self._make_routed_exp_with_distances(
            [1000.0, 990.0, 980.0, 900.0, 1100.0]
        )
        exp.calculate_speed(sc, local_timezone=UTC)
        # 1000→990 = -10 (small negative, skipped)
        # 990→980 = -10 (small negative, skipped)
        # 980→900 = -80 (< -50, skipped)
        # 900→1100 = +200 (valid)
        self.assertEqual(exp.ignored_segments_because_non_monotonic, 3)


# ---------------------------------------------------------------------------
# calculate_speed — ValueError messages
# ---------------------------------------------------------------------------


class TestCalculateSpeedValueErrors(SimpleTestCase):
    def test_too_few_gps_points_raises_with_message(self):
        """ValueError for < 2 GPS points must include a descriptive message."""
        exp = make_expedition(route_id="101I")
        exp.gps_points.append(make_gps(0.0, 0.0, 0))
        with self.assertRaises(ValueError) as ctx:
            exp.calculate_speed(MagicMock(), local_timezone=UTC)
        self.assertIn("gps points", str(ctx.exception))

    def test_no_shape_id_raises_with_message(self):
        """ValueError when shape_id is None must include a descriptive message."""
        exp = make_expedition(route_id="101I")
        exp.gps_points = [make_gps(0.0, 0.0, 0), make_gps(0.0, 0.0, 30)]
        # gps_distance_on_route is empty, shape_id is None
        with self.assertRaises(ValueError) as ctx:
            exp.calculate_speed(MagicMock(), local_timezone=UTC)
        self.assertIn("shape_id", str(ctx.exception))

    def test_mismatched_distances_raises_with_message(self):
        """ValueError when distance list length != GPS points must include a message."""
        exp = make_expedition(route_id="101I")
        exp.shape_id = "shape_1"
        exp.gps_points = [make_gps(0.0, 0.0, 0), make_gps(0.0, 0.0, 30)]
        exp.gps_distance_on_route = [100.0]  # only one entry, should be 2
        with self.assertRaises(ValueError) as ctx:
            exp.calculate_speed(MagicMock(), local_timezone=UTC)
        self.assertIn("distance_on_route", str(ctx.exception))
