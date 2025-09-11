import itertools
import json
from typing import List, Optional

import geojson
import geopandas as gpd
import networkx as nx
import pandas as pd
from config.paths import FIXTURE_PATH
from geojson.feature import Feature, FeatureCollection
from haversine import Unit, haversine
from networkx import Graph
from processors.geometry.point import Point as p
from processors.geometry.utils import (
    interpolate_points_by_distance,
    linestring_distance,
)
from processors.osm.query import ALAMEDA_QUERY, overpass_query
from pyproj.crs import CRS
from rest_api.models import Segment, Shape
from rest_api.util.shape import flush_shape_objects
from shapely.geometry import LineString
from shapely.geometry import LineString as shp_LineString
from shapely.geometry import Point
from shapely.ops import linemerge, snap, unary_union


# Separa el geojson en N linestring, con N el número de calles aisladas (alameda ida, alameda vuelta == 2)
def split_axis_by_direction(
    df: gpd.GeoDataFrame, bearing_threshold: float = 90.0
) -> List[gpd.GeoDataFrame]:
    """Split a GeoDataFrame by direction/bearing, useful for separating opposing traffic flows.

    Parameters
    ----------
    df : gpd.GeoDataFrame
        The input GeoDataFrame containing LineString geometries.
    bearing_threshold : float, default 45.0
        Maximum difference in bearing (degrees) to consider geometries as same direction.

    Returns
    -------
    List[gpd.GeoDataFrame]
        A list of GeoDataFrames, each containing geometries with similar bearings.
    """
    if df.empty:
        return []

    # Calculate bearings for all geometries
    df_with_bearings = df.copy()
    df_with_bearings["bearing"] = df_with_bearings.geometry.apply(calculate_bearing)

    # Group by similar bearings
    bearing_groups = {}

    for idx, row in df_with_bearings.iterrows():
        bearing = row["bearing"]
        if bearing is None:
            continue

        # Find the "oneway" tag safely
        oneway = (
            row["oneway"] if "oneway" in row and row["oneway"] is not None else "no"
        )

        # Find existing group with similar bearing
        assigned = False
        for group_bearing, group_indices in bearing_groups.items():
            bearing_diff = min(
                abs(bearing - group_bearing),
                360
                - abs(bearing - group_bearing),  # Handle wraparound (e.g., 350° vs 10°)
            )

            if oneway == "no":
                group_indices.append(idx)
                assigned = True

            if bearing_diff <= bearing_threshold:
                group_indices.append(idx)
                assigned = True

        # Create new group if no similar bearing found
        if not assigned:
            bearing_groups[bearing] = [idx]

    # Create separate GeoDataFrames for each bearing group
    result = []
    for group_indices in bearing_groups.values():
        group_df = df.loc[group_indices].copy()
        result.append(group_df)

    return result


def calculate_bearing(geometry):
    """Calculate the bearing of a LineString geometry.

    Parameters
    ----------
    geometry : shapely.geometry.LineString
        The geometry to calculate bearing for.

    Returns
    -------
    float or None
        Bearing in degrees (0-360), or None if calculation fails.
    """
    if not isinstance(geometry, LineString) or len(geometry.coords) < 2:
        return None

    import math

    # Get start and end points
    start = geometry.coords[0]
    end = geometry.coords[-1]

    # Convert to radians
    lat1, lon1 = math.radians(start[1]), math.radians(start[0])
    lat2, lon2 = math.radians(end[1]), math.radians(end[0])

    # Calculate bearing
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        dlon
    )

    bearing = math.atan2(y, x)
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360  # Normalize to 0-360

    return round(bearing, 2)


def merge_lines_with_metadata(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Merge touching LineStrings into as few LineStrings as possible,
    preserving and aggregating metadata from the original GeoDataFrame.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Input GeoDataFrame with LineString geometries and metadata.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with merged LineStrings and aggregated metadata.
    """
    if gdf.empty:
        return gdf

    # Build connectivity graph
    G = Graph()
    for idx, geom in gdf.geometry.items():
        G.add_node(idx)
    for i, geom_i in gdf.geometry.items():
        for j, geom_j in gdf.geometry.items():
            if i >= j:
                continue
            if geom_i.touches(geom_j) or geom_i.intersects(geom_j):
                G.add_edge(i, j)

    groups = list(nx.connected_components(G))

    merged_geoms = []
    merged_metadata = []

    for group in groups:
        group_df = gdf.loc[list(group)]
        # Merge geometries
        merged_union = unary_union(group_df.geometry)
        if merged_union.geom_type == "LineString":
            merged_geom = merged_union
        else:
            merged_geom = linemerge(merged_union)
        merged_geoms.append(merged_geom)
        # Aggregate metadata extract the most common value for each column
        meta = group_df.drop(columns="geometry").mode().iloc[0].to_dict()
        merged_metadata.append(meta)

    # Build new GeoDataFrame
    result_gdf = gpd.GeoDataFrame(merged_metadata, geometry=merged_geoms, crs=gdf.crs)
    result_gdf = filter_short_lines(result_gdf, min_length_m=300.0)
    return result_gdf


def filter_short_lines(
    gdf: gpd.GeoDataFrame, min_length_m: float = 10.0
) -> gpd.GeoDataFrame:
    """Filter out LineStrings shorter than min_length_m (in meters) after the merge.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Input GeoDataFrame with LineString geometries.
    min_length_m : float, optional
        Minimum length in meters to keep a LineString, by default 10.0

    Returns
    -------
    gpd.GeoDataFrame
        Filtered GeoDataFrame with only LineStrings longer than min_length_m.
    """
    if gdf.empty:
        return gdf

    # Ensure CRS is set; Overpass / raw features often lack explicit CRS though they are WGS84
    if gdf.crs is None:
        # Assume WGS84 (lat/lon) if missing
        try:
            # Simple string approach
            gdf.set_crs("EPSG:4326", inplace=True)
        except Exception as e1:
            try:
                # Using CRS object properly
                gdf.set_crs(CRS.from_epsg(4326), inplace=True)
            except Exception as e2:
                # Last resort
                gdf.set_crs(CRS.from_user_input("EPSG:4326"), inplace=True)
                print(f"Warning: Used fallback method to set CRS: {e1}, {e2}")

    # Try to pick an appropriate projected CRS for length measurement
    try:
        metric_crs = gdf.estimate_utm_crs()
        gm = gdf.to_crs(metric_crs).copy()
    except Exception:
        # Fallback to simple length calculation
        gm = gdf.copy()
        print(
            "[filter_short_lines] Warning: failed to project geometries; lengths may be inaccurate."
        )

    gm["length_m"] = gm.geometry.length
    filtered_gm = gm[gm["length_m"] >= min_length_m]
    # Reproject back only if projection succeeded and original CRS exists
    if gm.crs != gdf.crs:
        try:
            filtered_gm = filtered_gm.to_crs(gdf.crs)
        except Exception:
            pass
    return filtered_gm


def connect_lines(gdf: gpd.GeoDataFrame) -> Optional[gpd.GeoDataFrame]:
    """
    Function to connect gaps between LineStrings in a GeoDataFrame. This gaps can be up to 250 meters long.
    For example, in the axis Alameda, there is a gap between Avenida Nueva Providencia and Avenida Providencia a section of Avenida Vitacura is in between.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Input GeoDataFrame with LineString geometries.
    Returns
    -------
    Optional[gpd.GeoDataFrame]
        GeoDataFrame with connected LineStrings or None if input is empty.
    """
    if gdf.empty:
        print("Input GeoDataFrame is empty. No lines to connect.")
        return None

    try:
        # Ensure the GeoDataFrame has a valid CRS
        if gdf.crs is None:
            print(
                "Input GeoDataFrame has no CRS. Setting to WGS84 (EPSG:4326) by default."
            )
            gdf = gdf.set_crs(epsg=4326, inplace=True)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        # Ensure that it have more than one line to connect
        if len(gdf) < 2:
            print(
                "Input GeoDataFrame has less than two LineStrings. No connections needed."
            )
            return gdf

        # Get the extremes points of each LineString, is not sure that coords[0] is the start or the end
        extremes = []
        for idx, geom in enumerate(gdf.geometry):
            if isinstance(geom, LineString):
                extremes.append(
                    {"line_id": idx, "end_idx": 0, "geometry": Point(geom.coords[0])}
                )
                extremes.append(
                    {"line_id": idx, "end_idx": -1, "geometry": Point(geom.coords[-1])}
                )
            else:
                print("Non-LineString geometry found. Skipping.")
                continue
        extremes_gdf = gpd.GeoDataFrame(extremes, crs=gdf.crs).to_crs(epsg=3857)
        # Find pairs of extremes that are within 250 meters
        shortest_distance = float("inf")
        closest_pair = None
        for row1, row2 in itertools.product(
            extremes_gdf.itertuples(index=False), repeat=2
        ):
            if row1.line_id == row2.line_id:
                continue
            dist = row1.geometry.distance(row2.geometry)
            if dist < shortest_distance and dist <= 350:
                shortest_distance = dist
                closest_pair = (row1, row2)
        if not closest_pair:
            print("No pairs of extremes found within 350 meters. No connections made.")
            return gdf

        line1 = gdf.iloc[closest_pair[0].line_id].geometry
        line2 = gdf.iloc[closest_pair[1].line_id].geometry

        # Reordenar coordenadas según el extremo seleccionado
        coords1 = list(line1.coords)
        coords2 = list(line2.coords)

        if closest_pair[0].end_idx == 0:
            coords1 = coords1[::-1]
        if closest_pair[1].end_idx == -1:
            coords2 = coords2[::-1]

        new_coords = coords1 + coords2
        new_line = LineString(new_coords)

        # Create a new GeoDataFrame with the new connected line
        new_gdf = gpd.GeoDataFrame(geometry=[new_line], crs=gdf.crs)
        remaining_gdf = gdf.drop(
            index=[closest_pair[0].line_id, closest_pair[1].line_id]
        ).reset_index(drop=True)
        result_gdf = pd.concat([remaining_gdf, new_gdf], ignore_index=True)
        result_gdf = result_gdf.to_crs(epsg=4326)

        # Retrun a LineString if only one line remains
        if len(result_gdf) == 1:
            return result_gdf.geometry.iloc[0]

        print("Multiple lines remain after merging.")
        return result_gdf

    except Exception as e:
        print(f"Error connecting lines: {e}")
        return gdf


def iterate_coords(geom):
    """Iterate over the coordinates of a geometry. If the geometry is a MultiGeometry, it will iterate over all sub-geometries.

    Parameters
    ----------
    geom : shapely.geometry.base.BaseGeometry
        The geometry to iterate over.

    Yields
    ------
    tuple
        A tuple representing the (longitude, latitude) coordinates of each point in the geometry.
    """
    if geom.geom_type.startswith("Multi"):
        for g in geom.geoms:
            for c in g.coords:
                yield c
    else:
        for c in geom.coords:
            yield c


def segment_shape_by_distance(
    shape: shp_LineString,
    distance_threshold: float = 500,
    distance_algorithm: str = "euclidean",
):
    if distance_threshold <= 0:
        raise ValueError("distance_threshold must be greater than 0.")
    output_linestrings = []
    geom = shape

    previous_point = None
    segment = []
    distance_accum = 0
    for point in iterate_coords(geom):
        lon, lat = point
        current_point = Point(lon, lat)
        if previous_point is None:
            previous_point = current_point
            segment.append(current_point)
            continue
        previous_point_aux = p(latitude=previous_point.y, longitude=previous_point.x)
        current_point_aux = p(latitude=current_point.y, longitude=current_point.x)
        distance = previous_point_aux.distance(
            current_point_aux, algorithm=distance_algorithm
        )
        if distance_accum + distance >= distance_threshold:
            left = distance_threshold - distance_accum
            if left > 1:
                interpolated_point_coords = interpolate_points_by_distance(
                    previous_point, current_point, distance_in_meters=left
                )
                current_point = Point(interpolated_point_coords)
            segment.append(current_point)
            line = shp_LineString(segment)
            output_linestrings.append(line)
            previous_point = current_point
            segment = [current_point]
            if point == geom.geoms[-1].coords[-1]:
                segment = []
            distance_accum = 0
        else:
            distance_accum += distance
            previous_point = current_point
            segment.append(current_point)
    if len(segment) != 0:
        output_linestrings.append(shp_LineString(segment))
    return output_linestrings


def save_segmented_shape_to_db(segmented_shape: List[shp_LineString], shape_name: str):
    shape = Shape.objects.create(**{"name": shape_name})
    for sequence, segment in enumerate(segmented_shape):
        shape.add_segment(sequence=sequence, geometry=segment)


def save_all_segmented_shapes_to_db(segmented_shapes: List[List[shp_LineString]]):
    flush_shape_objects()
    for idx, segmented_shape in enumerate(segmented_shapes):
        save_segmented_shape_to_db(segmented_shape, shape_name=f"shape_{idx}")


# Crea la consulta, separa los distintos shapes, los mergea y divide en segmentos de 'distance_threshold' metros."
# Almacena toda la información en la db
def process_shape_data(distance_threshold: float = 500.0):
    print("Downloading OSM Overpass data...")
    print(f"Query:\n{ALAMEDA_QUERY}")
    query = overpass_query(ALAMEDA_QUERY)
    print(f"Number of features downloaded: {len(query['features'])}")
    # Save result
    filepath = "osm_overpass_query_result.geojson"
    print(f"Saving Overpass query result to {filepath}...")
    with open(filepath, "w", encoding="utf-8") as f:
        geojson.dump(query, f, ensure_ascii=False, indent=2)
    # Extract features with valid geometry
    query_data = gpd.GeoDataFrame.from_features(query, crs="EPSG:4326")
    print(f"Created GeoDataFrame with {len(query_data)} features")
    print(f"Columns: {query_data.columns.tolist()}")
    print(
        f"Tags example: {query_data['tags'].iloc[0] if 'tags' in query_data.columns else 'N/A'}"
    )
    print("splitting by shape..")
    splitted_geojson = split_axis_by_direction(query_data, bearing_threshold=90.0)
    segmented_shapes = []
    print(f"Got {len(splitted_geojson)} different shapes")
    for feature in splitted_geojson:
        merged = merge_lines_with_metadata(feature)
        connected = connect_lines(merged)
        segmented = segment_shape_by_distance(
            connected, distance_threshold, distance_algorithm="haversine"
        )
        segmented_shapes.append(segmented)
    save_all_segmented_shapes_to_db(segmented_shapes)


def process_fixture_data(distance_threshold: float = 500.0):
    try:
        gdf = gpd.read_file(FIXTURE_PATH)
        if gdf.crs is None:
            gdf.set_crs(CRS.from_string("EPSG:4326"), inplace=True)
    except Exception:
        with open(FIXTURE_PATH, "r") as f:
            data = json.load(f)
        features_with_geometry = [
            feature
            for feature in data["features"]
            if feature.get("geometry") is not None
        ]

        gdf = gpd.GeoDataFrame.from_features(features_with_geometry)
        if gdf.geometry.name not in gdf.columns:
            gdf.set_geometry("geometry", inplace=True)
        gdf.set_crs(CRS.from_string("EPSG:4326"), inplace=True)
    segmented_shapes = []
    for idx, feature in gdf.iterrows():
        merged = feature.geometry
        segmented = segment_shape_by_distance(
            merged, distance_threshold, distance_algorithm="haversine"
        )
        segmented_shapes.append(segmented)
    save_all_segmented_shapes_to_db(segmented_shapes)
