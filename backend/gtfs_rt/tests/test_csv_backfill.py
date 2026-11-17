import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase
from gtfs_rt.processors.csv_backfill import (
    compute_bearings,
    get_file_date,
    load_gps_gdf,
    load_route_dictionary,
    map_routes,
    read_gps_csv,
)
from rest_api.tests.tests_views_base import BaseTestCase

GPS_CSV = (
    "Patente;Latitud;Longitud;Tiempogps;Ruta;Velocidad;Ignición\n"
    "AAAA-11;-33.4400000;-70.6500000;20260722080000;T308 00R;0;SI\n"
    "AAAA-11;-33.4400000;-70.6500000;20260722080000;T308 00R;0;SI\n"
    "AAAA-11;-33.4410000;-70.6500000;20260722080030;T308 00R;0;SI\n"
    "AAAA-11;-33.4410000;-70.6500000;20260722080100;T308 00R;0;SI\n"
    "BBBB-22;-33.4500000;-70.6600000;20260722080000;T3TS 00I;0;SI\n"
    "BBBB-22;-33.4500000;-70.6610000;20260722080030;;0;SI\n"
    "CCCC-33;-33.4600000;-70.6700000;20260722080000;T307 00I;0;NO\n"
    "CCCC-33;-33.4600000;-70.6700000;20260722080030;T307 00I;0;NO\n"
)

DICTIONARY_CSV = (
    "﻿Route_ID;COD_USUARI;C CVGY;COD_SINRUT\r\n"
    "1;308;R;T308 00R\r\n"
    "2;308;I;T308 06I\r\n"
    "3;307;R;T307 00R\r\n"
)


class CsvBackfillTest(SimpleTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp_dir.name)
        self.csv_path = tmp / "Detalle_Registros_GPS_REP_20260722.csv"
        self.csv_path.write_bytes(GPS_CSV.encode("latin-1"))
        self.zip_path = tmp / "Detalle_Registros_GPS_REP_20260722.zip"
        with zipfile.ZipFile(self.zip_path, "w") as zf:
            zf.write(self.csv_path, self.csv_path.name)
        self.dictionary_path = tmp / "dictionary.csv"
        self.dictionary_path.write_text(DICTIONARY_CSV, encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_get_file_date(self):
        self.assertEqual(str(get_file_date(self.zip_path)), "2026-07-22")
        self.assertIsNone(get_file_date(Path("other.csv")))

    def test_read_gps_csv_converts_local_time_to_utc_and_dedupes(self):
        df = read_gps_csv(self.csv_path)
        self.assertEqual(len(df), 7)
        # July in Santiago is UTC-4
        self.assertEqual(
            df["timestamp"].min(), pd.Timestamp("2026-07-22 12:00:00", tz="UTC")
        )

    def test_read_gps_zip(self):
        self.assertEqual(len(read_gps_csv(self.zip_path)), 7)

    def test_map_routes(self):
        exact, fallback = load_route_dictionary(self.dictionary_path)
        routes = map_routes(
            pd.Series(["T308 00R", "T308 06I", "T307 00I", "T3TS 00I", None]),
            exact,
            fallback,
        )
        self.assertEqual(routes["route_id"].tolist()[:3], ["308", "308", "307"])
        self.assertTrue(routes["route_id"].iloc[3:].isna().all())
        self.assertEqual(routes["direction"].tolist(), [1, 0, 0, -1, -1])

    def test_compute_bearings(self):
        df = compute_bearings(read_gps_csv(self.csv_path))
        # CCCC-33 never moves, so it has no bearing and is dropped
        self.assertNotIn("CCCC-33", df["license_plate"].tolist())
        bus_a = df[df["license_plate"] == "AAAA-11"]["bearing"].tolist()
        # Moving south: 180 degrees, first and stationary pulses inherit it
        self.assertTrue(all(abs(b - 180) < 0.01 for b in bus_a))
        bus_b = df[df["license_plate"] == "BBBB-22"]["bearing"].tolist()
        # Moving west: 270 degrees
        self.assertTrue(all(abs(b - 270) < 0.1 for b in bus_b))

    def test_load_gps_gdf_schema(self):
        exact, fallback = load_route_dictionary(self.dictionary_path)
        gdf, stats = load_gps_gdf(self.zip_path, exact, fallback)
        self.assertEqual(stats["pulses"], 7)
        self.assertEqual(stats["unmapped_pulses"], 2)
        self.assertEqual(
            list(gdf.columns),
            ["route_id", "direction", "license_plate", "bearing", "timestamp", "geometry"],
        )
        self.assertEqual(str(gdf["direction"].dtype), "int8")
        self.assertEqual(str(gdf.crs), "EPSG:4326")


class BackfillSpeedCommandTest(BaseTestCase):
    def test_no_shapes_found(self):
        with tempfile.NamedTemporaryFile(
            suffix="_20260722.csv"
        ) as gps_file, tempfile.NamedTemporaryFile(suffix=".csv") as dictionary:
            with self.assertRaises(CommandError) as context:
                call_command(
                    "backfill_speed_from_csv",
                    input=gps_file.name,
                    dictionary=dictionary.name,
                )
        self.assertEqual("No shapes found", str(context.exception))
