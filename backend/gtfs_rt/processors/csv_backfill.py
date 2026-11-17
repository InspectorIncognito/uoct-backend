"""
Backfill of GPS pulses from the daily CSV exports (Detalle_Registros_GPS_REP_YYYYMMDD.csv).

The CSV files have the columns:
    Patente;Latitud;Longitud;Tiempogps;Ruta;Velocidad;Ignición
where Tiempogps is local time (America/Santiago) in YYYYMMDDHHMMSS format and Ruta is
the TS route code (e.g. "T308 00R"). This module converts them into the same GeoDataFrame
schema produced by GridManager.get_gps_gdf so they can be fed to calculate_speed.
"""

import re
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

CSV_TIMEZONE = "America/Santiago"
CSV_COLUMNS = ["license_plate", "latitude", "longitude", "timestamp", "ts_route"]
EARTH_RADIUS_MTS = 6371000.0
MIN_BEARING_DISTANCE_MTS = 5.0
DIRECTION_BY_SENSE = {"I": 0, "R": 1}
FILE_DATE_PATTERN = re.compile(r"_(\d{8})\.(csv|zip)$", re.IGNORECASE)


def get_file_date(path: Path):
    match = FILE_DATE_PATTERN.search(path.name)
    if match is None:
        return None
    return pd.to_datetime(match.group(1), format="%Y%m%d").date()


def load_route_dictionary(path) -> tuple[dict, dict]:
    """
    Read the services dictionary and return two lookups:
    - exact: COD_SINRUT (e.g. "T308 00R") -> COD_USUARI (e.g. "308")
    - fallback: COD_SINRUT without the variant token (e.g. "T308") -> COD_USUARI
    """
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str)
    df = df.dropna(subset=["COD_SINRUT", "COD_USUARI"])
    df["COD_SINRUT"] = df["COD_SINRUT"].str.strip()
    df["COD_USUARI"] = df["COD_USUARI"].str.strip()

    exact = dict(zip(df["COD_SINRUT"], df["COD_USUARI"]))

    fallback = dict()
    # Base variant ("00") wins over special variants when building the fallback
    df["is_base"] = df["COD_SINRUT"].str.rsplit(" ", n=1).str[-1].str.startswith("00")
    for row in df.sort_values("is_base").itertuples():
        prefix = row.COD_SINRUT.rsplit(" ", 1)[0]
        fallback[prefix] = row.COD_USUARI
    return exact, fallback


def map_routes(ts_routes: pd.Series, exact: dict, fallback: dict) -> pd.DataFrame:
    """
    Map TS route codes to (route_id, direction). Unmapped routes (empty or "T{n}TS")
    return route_id=None and direction=-1, like GTFS-RT pulses without trip.
    """
    mapping = dict()
    for ts_route in ts_routes.dropna().str.strip().unique():
        if not ts_route:
            continue
        sense = ts_route[-1]
        if sense not in DIRECTION_BY_SENSE:
            continue
        route_id = exact.get(ts_route)
        if route_id is None:
            route_id = fallback.get(ts_route.rsplit(" ", 1)[0])
        if route_id is None:
            continue
        mapping[ts_route] = (route_id, DIRECTION_BY_SENSE[sense])

    stripped = ts_routes.fillna("").str.strip()
    route_ids = stripped.map({k: v[0] for k, v in mapping.items()})
    directions = stripped.map({k: v[1] for k, v in mapping.items()}).fillna(-1)
    return pd.DataFrame({"route_id": route_ids, "direction": directions.astype("int8")})


def read_gps_csv(path) -> pd.DataFrame:
    """Read a daily GPS CSV (plain or zipped) and return timestamps in UTC."""
    path = Path(path)
    read_kwargs = dict(
        sep=";",
        encoding="latin-1",
        usecols=[0, 1, 2, 3, 4],
        names=CSV_COLUMNS,
        header=0,
        dtype={
            "license_plate": str,
            "latitude": "float64",
            "longitude": "float64",
            "timestamp": str,
            "ts_route": str,
        },
    )
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"{path} must contain exactly one CSV file")
            with zf.open(csv_names[0]) as raw:
                df = pd.read_csv(raw, **read_kwargs)
    else:
        df = pd.read_csv(path, **read_kwargs)

    df = df.dropna(subset=["license_plate", "latitude", "longitude", "timestamp"])
    df = df[(df["latitude"] != 0) & (df["longitude"] != 0)]
    df["timestamp"] = (
        pd.to_datetime(df["timestamp"], format="%Y%m%d%H%M%S", errors="coerce")
        .dt.tz_localize(CSV_TIMEZONE, ambiguous="NaT", nonexistent="shift_forward")
        .dt.tz_convert("UTC")
    )
    df = df.dropna(subset=["timestamp"])
    df = df.drop_duplicates(
        subset=["license_plate", "timestamp", "latitude", "longitude"]
    )
    return df.reset_index(drop=True)


def compute_bearings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the bearing of each pulse from the previous pulse of the same vehicle.
    Pulses closer than MIN_BEARING_DISTANCE_MTS inherit the last known bearing, since the
    HMM does not accept NaN bearings. Vehicles that never move are dropped.
    """
    df = df.sort_values(["license_plate", "timestamp"]).reset_index(drop=True)
    lat = np.radians(df["latitude"].to_numpy())
    lon = np.radians(df["longitude"].to_numpy())
    same_vehicle = df["license_plate"].to_numpy()[1:] == df["license_plate"].to_numpy()[:-1]

    lat1, lat2 = lat[:-1], lat[1:]
    dlon = lon[1:] - lon[:-1]
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    bearing = (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0

    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    distance = 2 * EARTH_RADIUS_MTS * np.arcsin(np.sqrt(a))

    valid = same_vehicle & (distance >= MIN_BEARING_DISTANCE_MTS)
    bearings = np.full(len(df), np.nan)
    bearings[1:] = np.where(valid, bearing, np.nan)
    df["bearing"] = bearings
    df["bearing"] = df.groupby("license_plate", sort=False)["bearing"].ffill()
    df["bearing"] = df.groupby("license_plate", sort=False)["bearing"].bfill()
    return df.dropna(subset=["bearing"]).reset_index(drop=True)


def to_gps_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Build the same GeoDataFrame schema as GridManager.get_gps_gdf."""
    out = pd.DataFrame(
        {
            "route_id": df["route_id"].astype("category"),
            "direction": df["direction"].fillna(-1).astype("int8"),
            "license_plate": df["license_plate"].astype("category"),
            "bearing": df["bearing"].astype("float32"),
            "timestamp": df["timestamp"],
        }
    )
    geometry = gpd.points_from_xy(
        df["longitude"].astype("float32"),
        df["latitude"].astype("float32"),
    )
    return gpd.GeoDataFrame(out, geometry=geometry, crs="EPSG:4326")


def load_gps_gdf(path, exact: dict, fallback: dict) -> tuple[gpd.GeoDataFrame, dict]:
    df = read_gps_csv(path)
    routes = map_routes(df["ts_route"], exact, fallback)
    df["route_id"] = routes["route_id"].to_numpy()
    df["direction"] = routes["direction"].to_numpy()
    stats = dict(
        pulses=len(df),
        unmapped_pulses=int(df["route_id"].isna().sum()),
    )
    df = compute_bearings(df)
    stats["pulses_with_bearing"] = len(df)
    return to_gps_gdf(df), stats
