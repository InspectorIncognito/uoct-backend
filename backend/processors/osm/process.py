import itertools
import json
from typing import Dict, List, Optional

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
from processors.osm.query import EJES_PRINCIPALES, OSMDownloader, get_axis_config
from pyproj.crs import CRS
from rest_api.models import Segment, Shape
from rest_api.util.shape import flush_shape_objects
from shapely import Point, to_geojson
from shapely.geometry import LineString as shp_LineString
from shapely.geometry import MultiLineString as shp_MultiLineString
from shapely.geometry import Point as shp_Point
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
        # Handle nan values from pandas DataFrame, is is nan, convert to "no"
        if not isinstance(oneway, str):
            oneway = "no"

        # Find existing group with similar bearing
        assigned = False
        for group_bearing, group_indices in bearing_groups.items():
            bearing_diff = min(
                abs(bearing - group_bearing),
                360
                - abs(bearing - group_bearing),  # Handle wraparound (e.g., 350° vs 10°)
            )

            if oneway == "no" or oneway == "false" or oneway == "0":
                group_indices.append(idx)
                assigned = True

            if bearing_diff <= bearing_threshold:
                if idx not in group_indices:
                    group_indices.append(idx)
                assigned = True

        # Create new group if no similar bearing found
        if not assigned:
            bearing_groups[bearing] = [idx]

    # Create separate GeoDataFrames for each bearing group
    result = []
    for group_indices in bearing_groups.values():
        group_df = df.loc[group_indices].copy()
        group_df.set_crs(df.crs, allow_override=True, inplace=True)
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
    if not isinstance(geometry, shp_LineString) or len(geometry.coords) < 2:
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

    # Find connected components (groups of touching lines)
    import networkx as nx
    from networkx import Graph

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
        meta = filter_metadata(meta)
        meta["group_size"] = len(group_df)
        merged_metadata.append(meta)

    # Build new GeoDataFrame
    result_gdf = gpd.GeoDataFrame(merged_metadata, geometry=merged_geoms, crs=gdf.crs)
    return result_gdf


def filter_short_lines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Filter out the shortest LineStrings if there is more than one.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Input GeoDataFrame with LineString geometries.

    Returns
    -------
    gpd.GeoDataFrame
        Filtered GeoDataFrame with only LineStrings longer than min_length_m.
    """
    if gdf.empty:
        return gdf
    orig_crs = gdf.crs
    metric_crs = gdf.estimate_utm_crs() or "EPSG:3857"
    gm = gdf.to_crs(metric_crs).copy()
    gm["length_m"] = gm.geometry.length
    if len(gm) > 1:
        return gm[gm["length_m"] == gm["length_m"].max()].to_crs(orig_crs)
    return gdf


def filter_metadata(metadata: dict) -> dict:
    """Filter metadata dictionary to keep only specified keys."""
    bus_metadata = [
        "lanes:bus",
        "bus",
        "psv:lanes",
    ]
    for key in bus_metadata:
        if key in metadata and metadata[key] in ["yes", "designated", "lane"]:
            metadata["bus"] = True
            break
    else:
        metadata["bus"] = False

    keys_to_keep = [
        "highway",
        "lanes",
        "bus",
        "oneway",
        "direction_group",
        "group_size",
        "eje_name",
        "length_m",
    ]

    return {k: v for k, v in metadata.items() if k in keys_to_keep}


def keep_main_axis_lines(gdf, tol=1e-6):
    """
    Filtra un GeoDataFrame con una sola fila de tipo MultiLineString,
    eliminando líneas paralelas y ramas (salidas) que no corresponden al eje principal.
    """
    if gdf.empty:
        return gdf

    orig_crs = gdf.crs
    # Asegurar CRS de entrada y reproyectar a CRS métrico para distancias
    if gdf.crs is None:
        # Si no hay CRS original, asumimos WGS84 para devolver en ese CRS
        orig_crs = "EPSG:4326"
        gdf = gdf.set_crs(4326, allow_override=True)
    metric_crs = gdf.estimate_utm_crs() or "EPSG:3857"
    gdf_copy = gdf.to_crs(metric_crs)  # Usar CRS métrico para cálculos de distancia

    multi = gdf_copy.geometry.iloc[0]
    if multi.geom_type != "MultiLineString":
        return gdf

    lines = list(multi.geoms)
    endpoints = [(Point(l.coords[0]), Point(l.coords[-1])) for l in lines]

    parallel_keep, parallel_drop = set(), set()

    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            s1, e1 = endpoints[i]
            s2, e2 = endpoints[j]

            # --- misma lógica que tu función original ---
            same_start = s1.distance(s2) < tol or s1.distance(e2) < tol
            same_end = e1.distance(s2) < tol or e1.distance(e2) < tol

            if same_start and same_end:
                # Líneas paralelas
                # Quedarse con la más corta
                drop = i if lines[i].length > lines[j].length else j
                parallel_drop.add(drop)
                parallel_keep.add(j if drop == i else i)
                continue

    keep_idx = [k for k in range(len(lines)) if k not in parallel_drop]

    # Eliminar las branches
    branches_idx = remove_branches(lines, keep_idx, parallel_keep)
    keep_idx = [k for k in keep_idx if k not in branches_idx]

    # Crear nuevo GeoDataFrame
    attrs = gdf_copy.iloc[0].drop("geometry").to_dict()
    geoms_to_keep = [lines[k] for k in keep_idx]
    rows = [attrs] * len(geoms_to_keep)
    result_gdf = gpd.GeoDataFrame(rows, geometry=geoms_to_keep, crs=gdf_copy.crs)
    result_gdf = result_gdf.to_crs(orig_crs)
    return result_gdf


def remove_branches(lines, keep_idx, parallel_keep, tol=1e-6):
    """
    Detecta y elimina líneas que son ramas o salidas del eje principal.
    Una rama se define como una línea que comparte un extremo con otra línea,
    pero cuyo otro extremo está alejado (más allá de una tolerancia).

    Parámetros
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame con las líneas a analizar.
    keep_idx : list
        Índices de las líneas que se mantienen (no paralelas).
    tol : float
        Tolerancia en metros para considerar dos puntos como iguales.

    Returns
    -------
    set
        Conjunto de índices de líneas que son ramas y deben eliminarse.
    """
    endpoints = [(Point(l.coords[0]), Point(l.coords[-1])) for l in lines]
    branches = set()
    keep_idx = set(keep_idx) - set(parallel_keep)
    for i in keep_idx:
        for j in keep_idx:
            if i == j:
                continue
            s1, e1 = endpoints[i]
            s2, e2 = endpoints[j]

            # Caso: comparten un extremo (start o end) pero el otro extremo está alejado
            shared_start = s1.distance(s2) < tol or s1.distance(e2) < tol
            shared_end = e1.distance(s2) < tol or e1.distance(e2) < tol

            if shared_start and not shared_end:
                drop = i if lines[i].length < lines[j].length else j
                branches.add(drop)

    return branches


def _get_linestring_extremes(idx: int, geom: shp_LineString) -> list:
    """Extract extreme points from a LineString geometry.

    Parameters
    ----------
    idx : int
        Index of the geometry in the GeoDataFrame
    geom : LineString
        The LineString geometry

    Returns
    -------
    list
        List of dictionaries containing line_id, end_idx, and geometry (Point)
    """
    return [
        {"line_id": idx, "end_idx": 0, "geometry": Point(geom.coords[0])},
        {"line_id": idx, "end_idx": -1, "geometry": Point(geom.coords[-1])},
    ]


def _get_multilinestring_extremes(idx: int, geom: shp_MultiLineString) -> list:
    """Extract extreme points from a MultiLineString geometry.

    Parameters
    ----------
    idx : int
        Index of the geometry in the GeoDataFrame
    geom : MultiLineString
        The MultiLineString geometry

    Returns
    -------
    list
        List of dictionaries containing line_id, end_idx, and geometry (Point)
    """
    lines = list(geom.geoms)
    if not lines:
        return []

    # Consider the first and last coordinates of the first and last LineString
    return [
        {
            "line_id": idx,
            "end_idx": 0,
            "geometry": Point(lines[0].coords[0]),
        },
        {
            "line_id": idx,
            "end_idx": -1,
            "geometry": Point(lines[-1].coords[-1]),
        },
    ]


def connect_lines(
    gdf: gpd.GeoDataFrame, max_distance_m: float = 450.0
) -> Optional[gpd.GeoDataFrame]:
    """
    Function to connect gaps between LineStrings in a GeoDataFrame.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Input GeoDataFrame with LineString or MultiLineString geometries.
    max_distance_m : float, default 450.0
        Maximum distance in meters to consider for connections.

    Returns
    -------
    Optional[gpd.GeoDataFrame]
        GeoDataFrame with connected LineStrings or None if input is empty.
    """
    if gdf.empty:
        return None

    try:
        # Ensure the GeoDataFrame has a valid CRS
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326, allow_override=True)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        # Ensure that it have more than one line to connect
        if len(gdf) < 2:
            if isinstance(gdf.iloc[0].geometry, shp_MultiLineString):
                if len(gdf.iloc[0].geometry.geoms) < 2:
                    return gdf
            elif isinstance(gdf.iloc[0].geometry, shp_LineString):
                return gdf

        # Get the extremes points of each geometry
        extremes = []
        for idx, geom in enumerate(gdf.geometry):
            if isinstance(geom, shp_LineString) or geom.geom_type == "LineString":
                extremes.extend(_get_linestring_extremes(idx, geom))
            elif (
                isinstance(geom, shp_MultiLineString)
                or geom.geom_type == "MultiLineString"
            ):
                extremes.extend(_get_multilinestring_extremes(idx, geom))
            else:
                continue

        if len(extremes) < 4:  # Need at least 2 geometries with 2 extremes each
            return gdf

        extremes_gdf = gpd.GeoDataFrame(extremes, crs=gdf.crs).to_crs(epsg=3857)

        # Find pairs of extremes that are within max_distance_m
        shortest_distance = float("inf")
        closest_pair = None
        for row1, row2 in itertools.product(
            extremes_gdf.itertuples(index=False), repeat=2
        ):
            if row1.line_id == row2.line_id:
                continue
            dist = row1.geometry.distance(row2.geometry)
            if dist < shortest_distance and dist <= max_distance_m:
                shortest_distance = dist
                closest_pair = (row1, row2)

        if not closest_pair:
            return gdf

        line1 = gdf.iloc[closest_pair[0].line_id].geometry
        line2 = gdf.iloc[closest_pair[1].line_id].geometry

        # Extract all coordinates from geometries
        def extract_all_coords(geom):
            """Extract all coordinates from LineString or MultiLineString."""
            if isinstance(geom, shp_MultiLineString):
                all_coords = []
                for line in geom.geoms:
                    all_coords.extend(list(line.coords))
                return all_coords
            else:
                return list(geom.coords)

        coords1 = extract_all_coords(line1)
        coords2 = extract_all_coords(line2)

        # Reorder coordinates according to the selected extreme
        if closest_pair[0].end_idx == 0:
            coords1 = coords1[::-1]
        if closest_pair[1].end_idx == -1:
            coords2 = coords2[::-1]

        new_coords = coords1 + coords2
        new_line = shp_LineString(new_coords)

        # Create a new GeoDataFrame with the new connected line
        new_gdf = gpd.GeoDataFrame(geometry=[new_line], crs=gdf.crs)
        # Add metadata if available
        for col in gdf.columns:
            if col != "geometry":
                new_gdf[col] = gdf.iloc[closest_pair[0].line_id][col]
        remaining_gdf = gdf.drop(
            index=[closest_pair[0].line_id, closest_pair[1].line_id]
        ).reset_index(drop=True)
        result_gdf = pd.concat([remaining_gdf, new_gdf], ignore_index=True)
        result_gdf = result_gdf.to_crs(epsg=4326)

        if len(result_gdf) == 1:
            return result_gdf
        else:
            return connect_lines(result_gdf, max_distance_m)

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
    shape: gpd.GeoDataFrame,
    distance_threshold: float = 500,
    distance_algorithm: str = "euclidean",
) -> List[shp_LineString]:
    if distance_threshold <= 0:
        raise ValueError("distance_threshold must be greater than 0.")
    output_linestrings = []
    geom = shape.geometry.iloc[0]
    if not isinstance(geom, (shp_LineString, shp_MultiLineString)):
        raise ValueError("Input geometry must be a LineString or MultiLineString.")

    previous_point = None
    segment = []
    distance_accum = 0

    # Get the last coordinate to check against later
    last_point = None
    if geom.geom_type.startswith("Multi"):
        last_point = list(geom.geoms[-1].coords)[-1]
    else:
        last_point = list(geom.coords)[-1]

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
            if point == last_point:
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


def save_all_segmented_shapes_to_db(
    segmented_shapes: List[List[shp_LineString]], flush: bool = True
):
    if flush:
        flush_shape_objects()
    for idx, segmented_shape in enumerate(segmented_shapes):
        save_segmented_shape_to_db(segmented_shape, shape_name=f"shape_{idx}")


# Funtion to process all the shape data from OSM
def process_osm_queries(distance_threshold: float = 500.0, use_fixtures: bool = False):
    """Process all the queries in EJES_PRINCIPALES, downloading data from OSM Overpass API,
    or using local fixtures if use_fixtures is True. Segments the shapes by distance_threshold
    """
    if use_fixtures:
        process_fixture_data(distance_threshold)
    else:
        osm_downloader = OSMDownloader()
        for idx, query_name in enumerate(EJES_PRINCIPALES.keys()):
            axis_config = get_axis_config(query_name)
            query = osm_downloader.build_overpass_query(
                place=axis_config["city"],
                highway_type=axis_config["highway_type"],
                streets=axis_config["streets"],
            )
            axis = osm_downloader.execute_query(query)
            if idx == 0:
                flush = True
            else:
                flush = False
            process_shape_data(query_name, axis, distance_threshold, flush=flush)


# Crea la consulta, separa los distintos shapes, los mergea y divide en segmentos de 'distance_threshold' metros."
# Almacena toda la información en la db
def process_shape_data(
    axis_name: str, axis: Dict, distance_threshold: float = 500.0, flush: bool = True
):
    # Extract features with valid geometry
    query_data = gpd.GeoDataFrame.from_features(axis, crs="EPSG:4326")
    splitted_gdf = split_axis_by_direction(query_data, bearing_threshold=90.0)
    segmented_shapes = []
    for i, group_gdf in enumerate(splitted_gdf):
        group_gdf["direction_group"] = i
        group_gdf["group_size"] = len(group_gdf)
        group_gdf["eje_name"] = axis_name
        merged = merge_lines_with_metadata(group_gdf)
        one_road_gdf = keep_main_axis_lines(merged)
        conected_gdf = connect_lines(one_road_gdf, max_distance_m=500.0)
        filtered_gdf = filter_short_lines(conected_gdf)
        segmented = segment_shape_by_distance(
            filtered_gdf, distance_threshold, distance_algorithm="haversine"
        )
        segmented_shapes.append(segmented)
    save_all_segmented_shapes_to_db(segmented_shapes, flush=flush)


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
