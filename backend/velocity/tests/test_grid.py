from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import geopandas as gpd
from django.test import SimpleTestCase
from shapely.geometry import LineString, Point
from velocity.expedition import ExpeditionData
from velocity.grid import GridManager

LAT = -33.45
LON = -70.66
START = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
SHAPE_EAST = "shape-east"
SHAPE_WEST = "shape-west"
SHAPE_NORTH = "shape-north"


def make_gdf(rows):
    """Build an axis GeoDataFrame from (segment_pk, shape_pk, direction, start_m, coords)."""
    return gpd.GeoDataFrame(
        {
            "segment_pk": [row[0] for row in rows],
            "shape_pk": [row[1] for row in rows],
            "shape_id": [row[1] for row in rows],
            "direction": [row[2] for row in rows],
            "sequence": list(range(len(rows))),
            "bearing": [None] * len(rows),
            "distance_start": [row[3] for row in rows],
        },
        geometry=[LineString(row[4]) for row in rows],
        crs="EPSG:4326",
    )


def make_pulse(lon, lat, bearing, seconds):
    return SimpleNamespace(
        longitude=lon,
        latitude=lat,
        bearing=bearing,
        timestamp=START + timedelta(seconds=seconds),
    )


class ExpeditionAcrossAxesTest(SimpleTestCase):
    """Each expedition must hold distances of a single shape and no matches may be lost."""

    def setUp(self):
        self.grid = GridManager()
        self.axis_a = make_gdf(
            [
                (1, SHAPE_EAST, 0, 0.0, [(LON, LAT), (LON + 0.01, LAT)]),
                (2, SHAPE_WEST, 1, 5000.0, [(LON + 0.01, LAT), (LON, LAT)]),
            ]
        )
        self.axis_b = make_gdf(
            [(3, SHAPE_NORTH, 0, 20000.0, [(LON + 0.02, LAT), (LON + 0.02, LAT + 0.01)])]
        )
        self.gps_points = [make_pulse(LON, LAT, 90, i * 30) for i in range(4)]
        self.expedition = self.make_expedition()
        self.vehicle = SimpleNamespace(expeditions={self.expedition: self.expedition})

    def make_expedition(self):
        expedition = ExpeditionData(
            grid_manager=self.grid,
            route_id="506",
            timestamp=START,
            license_plate="TEST-01",
        )
        expedition.gps_points = self.gps_points
        return expedition

    def apply_axis(self, expedition, segments_gdf, matches):
        """Run one axis like the matching loops do; matches is {gps index: segment_pk}."""
        size = len(self.gps_points)
        matched = [matches.get(i) for i in range(size)]
        points = [
            Point(LON + 0.001 * i, LAT) if i in matches else None for i in range(size)
        ]
        new_set = self.grid._determine_shape_pk_from_matched_segments(
            expedition, self.vehicle, matched, sorted(matches), points, segments_gdf
        )
        for expedition, valid_id, matched_seg, proj_points in new_set.values():
            self.grid._update_expedition_from_hmm_results(
                expedition, matched_seg, valid_id, proj_points, segments_gdf
            )
        return expedition

    def indices_by_shape(self):
        return {
            expedition.shape_id: [
                i
                for i, distance in enumerate(expedition.gps_distance_on_route)
                if distance is not None
            ]
            for expedition in self.vehicle.expeditions
        }

    def test_second_axis_does_not_overwrite_the_first(self):
        last = self.apply_axis(self.expedition, self.axis_a, {0: 1, 1: 1})
        self.apply_axis(last, self.axis_b, {2: 3, 3: 3})
        self.assertEqual(
            self.indices_by_shape(), {SHAPE_EAST: [0, 1], SHAPE_NORTH: [2, 3]}
        )

    def test_axis_after_a_split_keeps_every_copy(self):
        last = self.apply_axis(self.expedition, self.axis_a, {0: 1, 1: 2})
        self.apply_axis(last, self.axis_b, {2: 3, 3: 3})
        self.assertEqual(
            self.indices_by_shape(),
            {SHAPE_EAST: [0], SHAPE_WEST: [1], SHAPE_NORTH: [2, 3]},
        )

class SerialMatchingAcrossAxesTest(SimpleTestCase):
    def test_vehicle_crossing_two_axes_gets_one_expedition_per_shape(self):
        axis_a = make_gdf(
            [(1, SHAPE_EAST, 0, 0.0, [(LON, LAT), (LON + 0.01, LAT)])]
        ).drop(columns=["distance_start"])
        axis_b = make_gdf(
            [(3, SHAPE_NORTH, 0, 0.0, [(LON + 0.02, LAT), (LON + 0.02, LAT + 0.01)])]
        ).drop(columns=["distance_start"])

        grid = GridManager()
        expedition = ExpeditionData(grid, "506", START, "TEST-01")
        expedition.gps_points = [
            make_pulse(LON + 0.002, LAT, 90, 0),
            make_pulse(LON + 0.004, LAT, 90, 30),
            make_pulse(LON + 0.02, LAT + 0.002, 0, 60),
            make_pulse(LON + 0.02, LAT + 0.004, 0, 90),
        ]
        vehicle = SimpleNamespace(expeditions={expedition: expedition})
        vm = SimpleNamespace(vehicles={"TEST-01": vehicle})

        with mock.patch.object(
            grid.shape_manager,
            "get_segments_gdf",
            return_value={"Axis A": axis_a, "Axis B": axis_b},
        ):
            grid.run_hmm_map_matching(vm)

        by_shape = {
            exp.shape_id: [
                i for i, d in enumerate(exp.gps_distance_on_route) if d is not None
            ]
            for exp in vehicle.expeditions
        }
        self.assertEqual(by_shape, {SHAPE_EAST: [0, 1], SHAPE_NORTH: [2, 3]})
