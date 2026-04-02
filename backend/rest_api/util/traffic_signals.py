import uuid
from typing import Dict

import geopandas as gpd

from rest_api.models import TrafficSignal


def flush_traffic_signals_from_db():
    """Delete all traffic signals from the database."""
    TrafficSignal.objects.all().delete()


def save_relevant_traffic_signals(
    signals_gdf: gpd.GeoDataFrame,
) -> Dict[str, TrafficSignal]:
    """
    Save relevant traffic signals to the database.

    This function should be called BEFORE saving segments, since Segment
    has ForeignKey references to TrafficSignal.

    Parameters
    ----------
    signals_gdf : gpd.GeoDataFrame
        GeoDataFrame with relevant traffic signals. Expected columns:
        - geometry: Point geometry
        - id: OSM node ID (from Overpass API)
        - intersecting_ways: Optional, comma-separated way names

    Returns
    -------
    Dict[str, TrafficSignal]
        Mapping of osm_id -> TrafficSignal instance for later FK assignment.
    """
    if signals_gdf.empty:
        return {}

    signals_map = {}

    for idx, row in signals_gdf.iterrows():
        # Extract OSM ID from the row
        osm_id = str(row.get("id", ""))
        if not osm_id:
            # Generate a fallback ID if OSM ID is missing
            osm_id = f"generated_{uuid.uuid4().hex[:12]}"

        # Extract coordinates
        latitude = row.geometry.y
        longitude = row.geometry.x

        # Extract intersecting ways (if available)
        intersecting_ways = row.get("intersecting_ways", "") or ""

        # Create or update the traffic signal
        signal, created = TrafficSignal.objects.update_or_create(
            osm_id=osm_id,
            defaults={
                "signal_id": osm_id,  # Use OSM ID as internal ID
                "latitude": latitude,
                "longitude": longitude,
                "intersecting_ways": intersecting_ways,
            },
        )

        signals_map[osm_id] = signal

    return signals_map


def get_signals_map_from_db() -> Dict[str, TrafficSignal]:
    """
    Load all traffic signals from DB into a mapping.

    Returns
    -------
    Dict[str, TrafficSignal]
        Mapping of osm_id -> TrafficSignal instance.
    """
    return {signal.osm_id: signal for signal in TrafficSignal.objects.all()}
