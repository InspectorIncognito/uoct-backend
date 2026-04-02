import itertools
import math
import os
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from haversine import Unit, haversine
from rest_api.models import Axles, Shape, TrafficSignal
from rest_api.util.shape import flush_shape_objects
from shapely import Point
from shapely.geometry import LineString as shp_LineString
from shapely.geometry import MultiLineString as shp_MultiLineString
from shapely.ops import linemerge, unary_union

from processors.geometry.point import Point as p
from processors.geometry.utils import interpolate_points_by_distance
from processors.osm.query import INDEPENDENCIA_QUERY, VESPUCIO_QUERY, OSMDownloader

# ============================================================================
# Configuration for traffic signal-based segmentation
# ============================================================================
TRAFFIC_SIGNAL_CONFIG = {
    "buffer_m": 10.0,  # Buffer in meters to detect intersection with ways
    "min_major_ways": 2,  # Minimum number of major ways (motorway/primary/secondary/tertiary) at intersection
    "fallback_distance_m": 500.0,  # Fallback max distance between cuts when no signals
    "min_segment_length_m": 350.0,  # Minimum segment length (avoid very short segments)
    "max_segment_length_m": 650.0,  # Maximum segment length (avoid very long segments)
}


def bearing_from_coords(a, b) -> float:
    """
    Calculate bearing from coord a -> b (lon, lat) in degrees [0, 360).
    """
    lat1, lon1 = math.radians(a[1]), math.radians(a[0])
    lat2, lon2 = math.radians(b[1]), math.radians(b[0])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        dlon
    )
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360) % 360


def calculate_bearing(geometry):
    """Calculate the weighted bearing of a LineString using geodesic formulas.
    Uses all segments and weights by real length in meters.
    Returns bearing in degrees (0-360)."""
    if not isinstance(geometry, shp_LineString) or len(geometry.coords) < 2:
        return None

    coords = list(geometry.coords)
    sum_sin = 0.0
    sum_cos = 0.0
    total_len = 0.0

    for (lon1, lat1), (lon2, lat2) in zip(coords[:-1], coords[1:]):
        seg_len = haversine((lat1, lon1), (lat2, lon2), unit=Unit.METERS)
        if seg_len == 0:
            continue

        bearing_deg = bearing_from_coords((lon1, lat1), (lon2, lat2))
        bearing_rad = math.radians(bearing_deg)
        sum_sin += seg_len * math.sin(bearing_rad)
        sum_cos += seg_len * math.cos(bearing_rad)
        total_len += seg_len

    if total_len == 0:
        return None

    mean_rad = math.atan2(sum_sin, sum_cos)
    bearing = (math.degrees(mean_rad) + 360) % 360
    return round(bearing, 2)


def split_axis_by_direction(
    df: gpd.GeoDataFrame,
    bearing_threshold: float = 80.0,
) -> List[gpd.GeoDataFrame]:
    """Split a GeoDataFrame by direction using graph connectivity.

    1. Explodes bidirectional lines into two directed lines.
    2. Builds a graph where edges connect lines that are spatially close and angularly aligned.
    3. Returns connected components as separate groups.
    """
    if df.empty:
        return []

    # Ensure we are working with a copy
    df = df.copy()

    # Pre-calculate bearings if not present
    if "bearing" not in df.columns:
        df["bearing"] = df.geometry.apply(calculate_bearing)

    # 1. Explode bidirectional lines
    new_rows = []
    for idx, row in df.iterrows():
        geom = row.geometry
        bearing = row["bearing"]
        if bearing is None:
            continue

        oneway = str(row.get("oneway", "no")).lower()

        # Add original (forward)
        row_dict = row.to_dict()
        row_dict["original_idx"] = idx
        row_dict["reversed"] = False
        new_rows.append(row_dict)

        # If bidirectional, add reversed
        if oneway in ["no", "false", "0"]:
            reversed_geom = shp_LineString(list(geom.coords)[::-1])
            reversed_bearing = (bearing + 180) % 360

            rev_row = row.to_dict()
            rev_row["geometry"] = reversed_geom
            rev_row["bearing"] = reversed_bearing
            rev_row["original_idx"] = idx
            rev_row["reversed"] = True
            new_rows.append(rev_row)

    expanded_df = gpd.GeoDataFrame(new_rows, crs=df.crs)
    if expanded_df.empty:
        return []

    # 2. Build Graph
    G = nx.Graph()
    for idx in expanded_df.index:
        G.add_node(idx)

    # Create spatial index
    sindex = expanded_df.sindex

    # Helper for distance (approximate in degrees for speed, or project?)
    # Let's project to 3857 for accurate distance checks
    expanded_metric = expanded_df.to_crs("EPSG:3857")

    # We iterate over the metric dataframe for distance checks
    for idx, row in expanded_metric.iterrows():
        geom = row.geometry
        bearing = expanded_df.at[idx, "bearing"]

        # Query neighbors within ~1km (0.01 deg) buffer to ensure we catch 550m gaps
        # geom is in 4326
        search_bounds = expanded_df.at[idx, "geometry"].buffer(0.01).bounds
        possible_matches = list(sindex.intersection(search_bounds))

        p_end = Point(geom.coords[-1])

        candidates = []

        for match_idx in possible_matches:
            if match_idx == idx:
                continue

            match_geom = expanded_metric.at[match_idx, "geometry"]
            match_bearing = expanded_df.at[match_idx, "bearing"]

            # Check alignment first (fastest)
            diff = min(abs(bearing - match_bearing), 360 - abs(bearing - match_bearing))
            if diff > bearing_threshold:
                continue

            # Check connectivity: End of A -> Start of B
            p_start_match = Point(match_geom.coords[0])

            # Distance check
            dist = p_end.distance(p_start_match)

            if dist < 550.0:
                candidates.append((match_idx, dist))

        # Adaptive Distance Threshold
        # Connect to the closest match(es) within a small buffer (e.g. 15m) of the minimum distance.
        if candidates:
            # Sort by distance
            candidates.sort(key=lambda x: x[1])
            min_dist = candidates[0][1]
            dist_threshold = min_dist + 15.0

            # Filter by distance
            dist_survivors = []
            for match_idx, dist in candidates:
                if dist <= dist_threshold:
                    # Re-calculate angle diff for sorting
                    match_bearing = expanded_df.at[match_idx, "bearing"]
                    diff = min(
                        abs(bearing - match_bearing),
                        360 - abs(bearing - match_bearing),
                    )
                    dist_survivors.append((match_idx, diff))
                else:
                    break

            # Angle Prioritization
            # If we have a straight-ish match, ignore sharp turns
            if dist_survivors:
                dist_survivors.sort(key=lambda x: x[1])
                best_diff = dist_survivors[0][1]

                if best_diff < 65.0:
                    angle_threshold = best_diff + 30.0
                    final_matches = [
                        m for m, d in dist_survivors if d <= angle_threshold
                    ]
                else:
                    final_matches = [m for m, d in dist_survivors]

                for match_idx in final_matches:
                    G.add_edge(idx, match_idx)

    # 3. Get Components
    components = list(nx.connected_components(G))

    # 4. Sort by total length (approx number of lines for now)
    # Better: sort by total length in meters
    component_stats = []
    for comp in components:
        comp_indices = list(comp)
        # Calculate total length
        total_len = expanded_metric.loc[comp_indices].geometry.length.sum()
        component_stats.append((comp_indices, total_len))

    # Sort by length descending
    component_stats.sort(key=lambda x: x[1], reverse=True)

    # Return top 2 groups
    result = []
    if len(component_stats) > 2:
        print(
            f"Warning: more than two components detected ({len(component_stats)}). "
            "Merging components with similar bearings."
        )

        # Group components by average bearing
        groups = {}  # key: group average bearing, value: accumulated GeoDataFrame

        for comp_indices, _ in component_stats:
            group_df = expanded_df.loc[comp_indices].copy()
            avg_bearing = group_df["bearing"].mean()

            # Try to assign this component to an existing group
            assigned = False
            for key_bearing in list(groups.keys()):
                diff = min(
                    abs(key_bearing - avg_bearing),
                    360 - abs(key_bearing - avg_bearing),
                )

                # If bearings are similar -> merge
                if diff < 120.0:  # Reasonable threshold to separate forward/backward
                    groups[key_bearing] = pd.concat(
                        [groups[key_bearing], group_df], ignore_index=True
                    )
                    assigned = True
                    break

            # If it doesn't fit any group, create a new one
            if not assigned:
                groups[avg_bearing] = group_df

        # Now sort groups by total length (in meters)
        grouped_stats = []
        for key_bearing, gdf in groups.items():
            gdf_metric = gdf.to_crs("EPSG:3857")
            total_len = gdf_metric.geometry.length.sum()
            grouped_stats.append((gdf, total_len))

        grouped_stats.sort(key=lambda x: x[1], reverse=True)

        # Keep only the two largest groups
        result = [gdf for gdf, _ in grouped_stats[:2]]

        return result

    # Simple case: exactly two components
    for comp_indices, _ in component_stats[:2]:
        group_df = expanded_df.loc[comp_indices].copy()
        result.append(group_df)

    return result


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

    # Build connectivity graph to find connected components
    G = nx.Graph()
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
        print(f"Filtering out short lines, keeping the longest of {len(gm)} lines.")
        return gm[gm["length_m"] == gm["length_m"].max()].to_crs(orig_crs)
    return gdf


def filter_metadata(metadata: dict) -> dict:
    """Filter metadata dictionary to keep only specified keys."""
    bus_metadata = [
        "lanes:bus",
        "psv:lanes",
        "bus:lanes",
        "psv:lanes",
    ]
    for key in bus_metadata:
        if (key in metadata) and (metadata[key]):
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
        "bearing",
    ]

    return {k: v for k, v in metadata.items() if k in keys_to_keep}


def keep_main_axis_lines(gdf, tol=10.0):
    """
    Filters a GeoDataFrame with a single MultiLineString row,
    removing parallel lines and branches (exits) that do not correspond to the main axis.

    Parameters
    ----------
    tol : float
        Tolerance in meters to consider two points as connected (default 10m).
    """
    if gdf.empty:
        return gdf

    orig_crs = gdf.crs
    # Ensure input CRS and reproject to metric CRS for distances
    if gdf.crs is None:
        # If no original CRS, assume WGS84
        orig_crs = "EPSG:4326"
        gdf = gdf.set_crs(4326, allow_override=True)
    metric_crs = gdf.estimate_utm_crs() or "EPSG:3857"
    gdf_copy = gdf.to_crs(metric_crs)  # Use metric CRS for distance calculations

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

            same_start = s1.distance(s2) < tol or s1.distance(e2) < tol
            same_end = e1.distance(s2) < tol or e1.distance(e2) < tol

            if same_start and same_end:
                # Parallel lines
                # Keep the longest one
                drop = i if lines[i].length > lines[j].length else j
                parallel_drop.add(drop)
                parallel_keep.add(j if drop == i else i)
                continue

    keep_idx = [k for k in range(len(lines)) if k not in parallel_drop]

    # Remove branches
    branches_idx = remove_branches(lines, keep_idx, parallel_keep)
    keep_idx = [k for k in keep_idx if k not in branches_idx]
    print(f"Parallel lines removed: {parallel_drop}")
    print(f"Branches removed: {branches_idx}")
    # Create new GeoDataFrame
    attrs = gdf_copy.iloc[0].drop("geometry").to_dict()
    geoms_to_keep = [lines[k] for k in keep_idx]
    rows = [attrs] * len(geoms_to_keep)
    result_gdf = gpd.GeoDataFrame(rows, geometry=geoms_to_keep, crs=gdf_copy.crs)
    result_gdf = result_gdf.to_crs(orig_crs)
    return result_gdf


def remove_branches(lines, keep_idx, parallel_keep, tol=10.0):
    """
    Detects and removes lines that are branches or exits from the main axis.
    A branch is defined as a line that shares one endpoint with another line,
    but whose other endpoint is far away (beyond a tolerance).

    Parameters
    ----------
    lines : list
        List of LineStrings to analyze.
    keep_idx : list
        Indices of the lines being kept (non-parallel).
    parallel_keep : set
        Indices of parallel lines being kept.
    tol : float
        Tolerance in meters to consider two points as connected (default 10m).

    Returns
    -------
    set
        Set of indices of lines that are branches and should be removed.
    """
    endpoints = [(Point(l.coords[0]), Point(l.coords[-1])) for l in lines]
    branches = set()
    keep_idx = set(keep_idx) - set(parallel_keep)
    for i in keep_idx:
        for j in keep_idx:
            if i == j or i in branches or j in branches:
                continue
            s1, e1 = endpoints[i]
            s2, e2 = endpoints[j]

            # Case: share one endpoint (start or end) but the other is far away
            shared_start = s1.distance(s2) < tol or s1.distance(e2) < tol
            shared_end = e1.distance(s2) < tol or e1.distance(e2) < tol

            if shared_start and not shared_end:
                print(f"Line {i} is a branch of {j} (shared start)")
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
    gdf: gpd.GeoDataFrame,
    max_distance_m: float = 450.0,
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


def line_first_last_bearing(line) -> Optional[float]:
    """
    Bearing using first and last point of a LineString.
    """
    if line is None or line.is_empty or not hasattr(line, "coords"):
        return None
    coords = list(line.coords)
    if len(coords) < 2:
        return None
    return round(bearing_from_coords(coords[0], coords[-1]), 2)


def orient_linestring_by_bearing(
    line: shp_LineString,
    target_bearing: float,
) -> shp_LineString:
    """
    Reorders the LineString so its initial bearing is consistent with target_bearing (0-360).
    If the difference is greater than 90°, it reverses the line.
    """
    coords = list(line.coords)
    start_bearing = bearing_from_coords(coords[0], coords[-1])
    diff = min(
        abs(start_bearing - target_bearing),
        360 - abs(start_bearing - target_bearing),
    )
    if diff > 90:  # It is almost reversed
        return shp_LineString(coords[::-1])
    return line


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
) -> gpd.GeoDataFrame:
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

    if len(output_linestrings) >= 2:
        last_line = output_linestrings[-1]
        prev_line = output_linestrings[-2]
        if last_line.length < 0.75 * distance_threshold:
            # Create a new LineString concatenating coordinates
            merged_coords = list(prev_line.coords) + list(last_line.coords)[1:]
            output_linestrings[-2] = shp_LineString(merged_coords)
            output_linestrings.pop(-1)

    # Path rectification using Douglas-Peucker algorithm
    gdf_segments = gpd.GeoDataFrame(geometry=output_linestrings, crs="EPSG:4326")
    gdf_segments = gdf_segments.to_crs("EPSG:3857")  # reproject to meters
    gdf_segments["geometry"] = gdf_segments.simplify(
        tolerance=4, preserve_topology=True
    )  # 4 meters tolerance
    gdf_segments = gdf_segments.to_crs("EPSG:4326")

    # Add per-segment bearing (first -> last point)
    gdf_segments["bearing"] = gdf_segments.geometry.apply(line_first_last_bearing)

    # Add metadata to segments
    for col in shape.columns:
        if col != "geometry" and col not in gdf_segments.columns:
            gdf_segments[col] = shape.iloc[0][col]

    return gdf_segments


# ============================================================================
# Traffic Signal-Based Segmentation Functions
# ============================================================================


def extract_streets_and_signals(
    osm_data: Dict,
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Extract streets and traffic signals from OSM response (streets + signals query).

    Parameters
    ----------
    osm_data : Dict
        GeoJSON response from Overpass API (streets with signals query).

    Returns
    -------
    Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]
        (streets_gdf, signals_gdf)
        - streets_gdf: LineStrings of the target axis streets
        - signals_gdf: Points of traffic signals on those streets (with 'id' column for OSM node ID)
    """
    features = osm_data.get("features", [])
    if not features:
        return (
            gpd.GeoDataFrame(crs="EPSG:4326"),
            gpd.GeoDataFrame(crs="EPSG:4326"),
        )

    streets = []
    signals = []

    for feature in features:
        geom_type = feature.get("geometry", {}).get("type", "")
        props = feature.get("properties", {})

        if geom_type == "Point" and props.get("highway") == "traffic_signals":
            # Preserve the feature ID (OSM node ID) in properties
            # GeoJSON 'id' field is not captured by from_features(), so we copy it
            feature_id = feature.get("id", "")
            if feature_id:
                # The ID format from Overpass is typically "node/123456789"
                # Extract just the numeric part
                if "/" in str(feature_id):
                    feature_id = str(feature_id).split("/")[-1]
                props["id"] = feature_id
            signals.append(feature)
        elif geom_type == "LineString" or geom_type == "MultiLineString":
            streets.append(feature)

    streets_gdf = (
        gpd.GeoDataFrame.from_features(streets, crs="EPSG:4326")
        if streets
        else gpd.GeoDataFrame(crs="EPSG:4326")
    )
    signals_gdf = (
        gpd.GeoDataFrame.from_features(signals, crs="EPSG:4326")
        if signals
        else gpd.GeoDataFrame(crs="EPSG:4326")
    )

    return streets_gdf, signals_gdf


def extract_relevant_ways(osm_data: Dict) -> gpd.GeoDataFrame:
    """
    Extract relevant ways (primary/secondary/tertiary) from OSM response.

    Parameters
    ----------
    osm_data : Dict
        GeoJSON response from Overpass API (relevant ways query).

    Returns
    -------
    gpd.GeoDataFrame
        LineStrings of all primary/secondary/tertiary ways in the area.
    """
    features = osm_data.get("features", [])
    if not features:
        return gpd.GeoDataFrame(crs="EPSG:4326")

    ways = []
    for feature in features:
        geom_type = feature.get("geometry", {}).get("type", "")
        props = feature.get("properties", {})

        if geom_type == "LineString" or geom_type == "MultiLineString":
            highway_type = props.get("highway", "")
            if highway_type in ("primary", "secondary", "tertiary"):
                ways.append(feature)

    return (
        gpd.GeoDataFrame.from_features(ways, crs="EPSG:4326")
        if ways
        else gpd.GeoDataFrame(crs="EPSG:4326")
    )


def identify_relevant_traffic_signals(
    signals_gdf: gpd.GeoDataFrame,
    ways_gdf: gpd.GeoDataFrame,
    buffer_m: float = None,
    min_major_ways: int = None,
) -> gpd.GeoDataFrame:
    """
    Identify traffic signals at relevant intersections.

    A traffic signal is "relevant" if it's near an intersection with at least
    `min_major_ways` major roads (primary, secondary, or tertiary).

    Parameters
    ----------
    signals_gdf : gpd.GeoDataFrame
        GeoDataFrame with traffic signal Points.
    ways_gdf : gpd.GeoDataFrame
        GeoDataFrame with all relevant ways (primary/secondary/tertiary).
    buffer_m : float, optional
        Buffer radius in meters for intersection detection.
        Defaults to TRAFFIC_SIGNAL_CONFIG["buffer_m"].
    min_major_ways : int, optional
        Minimum number of major ways that must intersect at the signal location.
        Defaults to TRAFFIC_SIGNAL_CONFIG["min_major_ways"].

    Returns
    -------
    gpd.GeoDataFrame
        Filtered GeoDataFrame with only relevant traffic signals.
    """
    if buffer_m is None:
        buffer_m = TRAFFIC_SIGNAL_CONFIG["buffer_m"]
    if min_major_ways is None:
        min_major_ways = TRAFFIC_SIGNAL_CONFIG["min_major_ways"]

    if signals_gdf.empty or ways_gdf.empty:
        return signals_gdf

    # Project to metric CRS for accurate buffer calculations
    metric_crs = signals_gdf.estimate_utm_crs() or "EPSG:3857"
    signals_metric = signals_gdf.to_crs(metric_crs)
    ways_metric = ways_gdf.to_crs(metric_crs)

    # Create spatial index for ways
    ways_sindex = ways_metric.sindex

    relevant_indices = []

    for idx, signal in signals_metric.iterrows():
        # Create buffer around the signal
        signal_buffer = signal.geometry.buffer(buffer_m)

        # Find ways that intersect this buffer
        possible_matches_idx = list(ways_sindex.intersection(signal_buffer.bounds))
        if not possible_matches_idx:
            continue

        # Count unique ways that actually intersect
        intersecting_ways = ways_metric.iloc[possible_matches_idx]
        actual_intersections = intersecting_ways[
            intersecting_ways.geometry.intersects(signal_buffer)
        ]

        # Count by unique way IDs (if available) or by geometry
        if "id" in actual_intersections.columns:
            way_count = actual_intersections["id"].nunique()
        else:
            way_count = len(actual_intersections)

        if way_count >= min_major_ways:
            relevant_indices.append(idx)

        # Add the name of the ways to the signal metadata for later use (e.g. naming segments)
        if not actual_intersections.empty:
            way_names = actual_intersections["name"].dropna().unique()
            if len(way_names) > 0:
                signals_gdf.at[idx, "intersecting_ways"] = ", ".join(way_names)

    if not relevant_indices:
        return gpd.GeoDataFrame(
            {"geometry": []}, geometry="geometry", crs=signals_gdf.crs
        )

    return signals_gdf.loc[relevant_indices].copy()


def project_point_onto_line(point: Point, line: shp_LineString) -> Tuple[float, Point]:
    """
    Project a point onto a line and return the distance along the line and projected point.

    Parameters
    ----------
    point : Point
        The point to project.
    line : LineString
        The line to project onto.

    Returns
    -------
    Tuple[float, Point]
        (distance_along_line, projected_point)
    """
    distance_along = line.project(point)
    projected_point = line.interpolate(distance_along)
    return distance_along, projected_point


def get_cut_points_from_signals(
    line: shp_LineString,
    signals_gdf: gpd.GeoDataFrame,
    buffer_m: float = None,
    min_segment_length_m: float = None,
    max_segment_length_m: float = None,
) -> List[Tuple[float, Optional[str]]]:
    """
    Get sorted list of cut points along the line based on nearby traffic signals.

    Parameters
    ----------
    line : LineString
        The axis line geometry (in metric CRS).
    signals_gdf : gpd.GeoDataFrame
        GeoDataFrame with relevant traffic signals (in metric CRS).
        Expected to have 'id' column with OSM node ID.
    buffer_m : float, optional
        Maximum distance from line to consider a signal.
        Defaults to TRAFFIC_SIGNAL_CONFIG["buffer_m"].
    min_segment_length_m : float, optional
        Minimum distance between cut points.
        Defaults to TRAFFIC_SIGNAL_CONFIG["min_segment_length_m"].

    Returns
    -------
    List[Tuple[float, Optional[str]]]
        Sorted list of (distance_along_line, osm_id) tuples.
        osm_id is the OSM node ID of the traffic signal at that cut point.
    """
    if buffer_m is None:
        buffer_m = TRAFFIC_SIGNAL_CONFIG["buffer_m"]
    if min_segment_length_m is None:
        min_segment_length_m = TRAFFIC_SIGNAL_CONFIG["min_segment_length_m"]
    if max_segment_length_m is None:
        max_segment_length_m = TRAFFIC_SIGNAL_CONFIG["max_segment_length_m"]

    if signals_gdf.empty:
        return []

    # List of (distance, osm_id) tuples
    cut_points = []
    line_length = line.length

    # Create buffer around the line to find nearby signals
    line_buffer = line.buffer(buffer_m * 1.5)  # Slightly larger buffer for search

    for idx, signal in signals_gdf.iterrows():
        if not line_buffer.contains(signal.geometry):
            # Quick filter: skip signals far from line
            if signal.geometry.distance(line) > buffer_m * 2:
                continue

        # Project signal onto line
        dist_along, projected = project_point_onto_line(signal.geometry, line)

        # Check if projection is actually close to the signal
        if projected.distance(signal.geometry) <= buffer_m:
            # Avoid cuts at the very start or end
            if min_segment_length_m < dist_along < (line_length - min_segment_length_m):
                # Extract OSM ID - try 'id' column first, then '@id', then index
                osm_id = None
                if "id" in signals_gdf.columns and pd.notna(signal.get("id")):
                    osm_id = str(signal["id"])
                elif "@id" in signals_gdf.columns and pd.notna(signal.get("@id")):
                    osm_id = str(signal["@id"])
                else:
                    # Use the DataFrame index as fallback
                    osm_id = str(idx)
                cut_points.append((dist_along, osm_id))

    # Sort by distance
    cut_points = sorted(cut_points, key=lambda x: x[0])

    # Merge cuts that are too close together (keep the first one)
    if len(cut_points) > 1:
        merged_cuts = [cut_points[0]]
        for cut in cut_points[1:]:
            if cut[0] - merged_cuts[-1][0] >= min_segment_length_m:
                merged_cuts.append(cut)
        cut_points = merged_cuts

    return cut_points


def add_fallback_cuts(
    cut_distances: List[float],
    line_length: float,
    fallback_distance_m: float = None,
    min_segment_length_m: float = None,
) -> List[float]:
    """
    Add fallback cut points when segments are too long (no signals in between).

    Parameters
    ----------
    cut_distances : List[float]
        Existing cut distances along the line.
    line_length : float
        Total length of the line in meters.
    fallback_distance_m : float, optional
        Maximum distance between cuts.
        Defaults to TRAFFIC_SIGNAL_CONFIG["fallback_distance_m"].
    min_segment_length_m : float, optional
        Minimum segment length.
        Defaults to TRAFFIC_SIGNAL_CONFIG["min_segment_length_m"].

    Returns
    -------
    List[float]
        Updated list of cut distances with fallback cuts added.
    """
    if fallback_distance_m is None:
        fallback_distance_m = TRAFFIC_SIGNAL_CONFIG["fallback_distance_m"]
    if min_segment_length_m is None:
        min_segment_length_m = TRAFFIC_SIGNAL_CONFIG["min_segment_length_m"]

    # Add virtual start and end points
    all_points = [0.0] + cut_distances + [line_length]

    new_cuts = list(cut_distances)

    for i in range(len(all_points) - 1):
        start = all_points[i]
        end = all_points[i + 1]
        segment_length = end - start

        # If segment is too long, add intermediate cuts
        if segment_length > fallback_distance_m:
            num_new_cuts = int(segment_length / fallback_distance_m)
            step = segment_length / (num_new_cuts + 1)

            for j in range(1, num_new_cuts + 1):
                new_cut = start + j * step
                # Avoid placing cut too close to existing cuts
                if all(abs(new_cut - c) >= min_segment_length_m for c in all_points):
                    new_cuts.append(new_cut)

    return sorted(set(new_cuts))


def segment_shape_by_traffic_signals(
    shape: gpd.GeoDataFrame,
    signals_gdf: gpd.GeoDataFrame,
    fallback_distance_m: float = None,
    buffer_m: float = None,
    min_segment_length_m: float = None,
    max_segment_length_m: float = None,
) -> gpd.GeoDataFrame:
    """
    Segment a shape by traffic signal locations with validation and fallback.

    This function cuts the axis at relevant traffic signal locations. If a segment
    would be shorter than min_segment_length_m or longer than max_segment_length_m,
    it uses fallback_distance_m-based cuts instead.

    Parameters
    ----------
    shape : gpd.GeoDataFrame
        GeoDataFrame with a single LineString or MultiLineString geometry.
    signals_gdf : gpd.GeoDataFrame
        GeoDataFrame with relevant traffic signals (already filtered).
        Expected to have 'id' column with OSM node ID.
    fallback_distance_m : float, optional
        Distance for fallback cuts when signal-based segments are invalid.
        Defaults to TRAFFIC_SIGNAL_CONFIG["fallback_distance_m"].
    buffer_m : float, optional
        Buffer for projecting signals onto line.
        Defaults to TRAFFIC_SIGNAL_CONFIG["buffer_m"].
    min_segment_length_m : float, optional
        Minimum valid segment length (default: 350m).
        Defaults to TRAFFIC_SIGNAL_CONFIG["min_segment_length_m"].
    max_segment_length_m : float, optional
        Maximum valid segment length (default: 650m).
        Defaults to TRAFFIC_SIGNAL_CONFIG["max_segment_length_m"].

    Returns
    -------
    gpd.GeoDataFrame
        Segmented GeoDataFrame with LineString geometries and columns:
        - start_signal_osm_id: OSM ID of signal at segment start (or None)
        - end_signal_osm_id: OSM ID of signal at segment end (or None)
    """
    if fallback_distance_m is None:
        fallback_distance_m = TRAFFIC_SIGNAL_CONFIG["fallback_distance_m"]
    if buffer_m is None:
        buffer_m = TRAFFIC_SIGNAL_CONFIG["buffer_m"]
    if min_segment_length_m is None:
        min_segment_length_m = TRAFFIC_SIGNAL_CONFIG["min_segment_length_m"]
    if max_segment_length_m is None:
        max_segment_length_m = TRAFFIC_SIGNAL_CONFIG["max_segment_length_m"]

    geom = shape.geometry.iloc[0]
    if not isinstance(geom, (shp_LineString, shp_MultiLineString)):
        raise ValueError("Input geometry must be a LineString or MultiLineString.")

    # Convert MultiLineString to single LineString by extracting all coords
    if isinstance(geom, shp_MultiLineString):
        all_coords = []
        for line in geom.geoms:
            all_coords.extend(list(line.coords))
        geom = shp_LineString(all_coords)

    # Project to metric CRS
    orig_crs = shape.crs or "EPSG:4326"
    metric_crs = shape.estimate_utm_crs() or "EPSG:3857"

    shape_metric = shape.to_crs(metric_crs)
    geom_metric = shape_metric.geometry.iloc[0]

    if isinstance(geom_metric, shp_MultiLineString):
        all_coords = []
        for line in geom_metric.geoms:
            all_coords.extend(list(line.coords))
        geom_metric = shp_LineString(all_coords)

    # Convert signals to same CRS
    if not signals_gdf.empty:
        signals_metric = signals_gdf.to_crs(metric_crs)
    else:
        signals_metric = signals_gdf

    line_length = geom_metric.length

    # Get cut points from traffic signals: List[(distance, osm_id)]
    signal_cut_points = get_cut_points_from_signals(
        geom_metric, signals_metric, buffer_m, min_segment_length_m
    )

    print(f"  Found {len(signal_cut_points)} traffic signal cut points")
    if signal_cut_points:
        print(f"    First 5 cut points: {signal_cut_points[:5]}")

    # Validate and process cut points with min/max segment length constraints
    # Build final cut points with signal tracking
    validated_cuts = _validate_and_build_cuts(
        signal_cut_points,
        line_length,
        min_segment_length_m,
        max_segment_length_m,
        fallback_distance_m,
    )

    print(f"  Total validated cut points: {len(validated_cuts)}")
    if validated_cuts:
        signal_cuts = [c for c in validated_cuts if c[1] is not None]
        print(f"    Cut points with signals: {len(signal_cuts)}")

    # Build segments with signal metadata
    # validated_cuts is List[(distance, osm_id_or_none)]
    # We need to track start/end signal for each segment
    output_data = _build_segments_with_signals(
        geom_metric, validated_cuts, line_length, min_segment_length_m
    )

    if not output_data:
        # Fallback: return entire line as single segment with no signals
        output_data = [
            {
                "geometry": geom_metric,
                "start_signal_osm_id": None,
                "end_signal_osm_id": None,
            }
        ]

    # Create GeoDataFrame in metric CRS
    gdf_segments = gpd.GeoDataFrame(output_data, crs=metric_crs)

    # Simplify (Douglas-Peucker)
    gdf_segments["geometry"] = gdf_segments.simplify(
        tolerance=4, preserve_topology=True
    )

    # Reproject back to original CRS
    gdf_segments = gdf_segments.to_crs(orig_crs)

    # Add per-segment bearing
    gdf_segments["bearing"] = gdf_segments.geometry.apply(line_first_last_bearing)

    # Add metadata from original shape
    for col in shape.columns:
        if col != "geometry" and col not in gdf_segments.columns:
            gdf_segments[col] = shape.iloc[0][col]

    return gdf_segments


def _validate_and_build_cuts(
    signal_cut_points: List[Tuple[float, Optional[str]]],
    line_length: float,
    min_segment_length_m: float,
    max_segment_length_m: float,
    fallback_distance_m: float,
) -> List[Tuple[float, Optional[str]]]:
    """
    Validate signal-based cuts and add fallback cuts where needed.

    Rules (per user requirement):
    - If a segment between signals would be < min_segment_length_m OR > max_segment_length_m:
      Use fallback_distance_m cuts instead (no signal association for that stretch).
    - If segment is between min and max: Use the traffic signal cut.

    Parameters
    ----------
    signal_cut_points : List[Tuple[float, Optional[str]]]
        Raw cut points from signals: (distance, osm_id)
    line_length : float
        Total length of the line in meters.
    min_segment_length_m : float
        Minimum valid segment length (350m).
    max_segment_length_m : float
        Maximum valid segment length (650m).
    fallback_distance_m : float
        Distance for fallback cuts when segments are invalid (500m).

    Returns
    -------
    List[Tuple[float, Optional[str]]]
        Validated cut points with fallback cuts added where needed.
    """
    final_cuts = []
    current_pos = 0.0
    signal_idx = 0
    signals_used = 0

    while current_pos < line_length:
        # Find the next signal after current_pos
        next_signal_dist = None
        next_signal_osm_id = None

        while signal_idx < len(signal_cut_points):
            sig_dist, sig_osm_id = signal_cut_points[signal_idx]
            if sig_dist > current_pos:
                next_signal_dist = sig_dist
                next_signal_osm_id = sig_osm_id
                break
            signal_idx += 1

        if next_signal_dist is None:
            # No more signals - fill remaining distance with fallback cuts
            remaining = line_length - current_pos
            if remaining > max_segment_length_m:
                fallback = _generate_distance_cuts(
                    current_pos, line_length, fallback_distance_m
                )
                final_cuts.extend(fallback)
            break

        segment_length = next_signal_dist - current_pos

        if segment_length < min_segment_length_m:
            # Segment too short - skip this signal, try the next one
            signal_idx += 1
            continue

        elif segment_length > max_segment_length_m:
            # Segment too long - add fallback cuts up to (but not including) the signal
            # Then check if we can use the signal for the next segment
            fallback = _generate_distance_cuts(
                current_pos, next_signal_dist, fallback_distance_m
            )
            final_cuts.extend(fallback)

            # Move current_pos to the last fallback cut (or close to the signal)
            if fallback:
                current_pos = fallback[-1][0]
            else:
                current_pos = next_signal_dist

            # Now check if we can use this signal
            new_segment_length = next_signal_dist - current_pos
            if min_segment_length_m <= new_segment_length <= max_segment_length_m:
                # We can use this signal
                final_cuts.append((next_signal_dist, next_signal_osm_id))
                current_pos = next_signal_dist
                signals_used += 1
            # Either way, move to check next signal
            signal_idx += 1

        else:
            # Segment length is valid (between min and max) - use the signal
            final_cuts.append((next_signal_dist, next_signal_osm_id))
            current_pos = next_signal_dist
            signals_used += 1
            signal_idx += 1

    # Sort and deduplicate by distance
    final_cuts = sorted(set(final_cuts), key=lambda x: x[0])

    print(f"    Valid signal cuts used: {signals_used}")
    print(f"    Final cuts (with fallbacks): {len(final_cuts)}")

    return final_cuts


def _generate_distance_cuts(
    start_dist: float,
    end_dist: float,
    distance_m: float,
) -> List[Tuple[float, Optional[str]]]:
    """
    Generate distance-based cut points between start and end.

    These cuts have no signal association (osm_id = None).

    Parameters
    ----------
    start_dist : float
        Start distance along the line.
    end_dist : float
        End distance along the line.
    distance_m : float
        Target distance between cuts.

    Returns
    -------
    List[Tuple[float, Optional[str]]]
        List of (distance, None) tuples for fallback cuts.
    """
    cuts = []
    segment_length = end_dist - start_dist

    if segment_length <= distance_m:
        return cuts

    num_cuts = int(segment_length / distance_m)
    step = segment_length / (num_cuts + 1)

    for i in range(1, num_cuts + 1):
        cut_dist = start_dist + i * step
        cuts.append((cut_dist, None))

    return cuts


def _build_segments_with_signals(
    line: shp_LineString,
    validated_cuts: List[Tuple[float, Optional[str]]],
    line_length: float,
    min_segment_length_m: float,
) -> List[Dict]:
    """
    Build segment geometries with signal metadata.

    Parameters
    ----------
    line : LineString
        The axis line geometry (in metric CRS).
    validated_cuts : List[Tuple[float, Optional[str]]]
        Validated cut points: (distance, osm_id_or_none)
    line_length : float
        Total length of the line.
    min_segment_length_m : float
        Minimum segment length for merging short final segments.

    Returns
    -------
    List[Dict]
        List of dicts with 'geometry', 'start_signal_osm_id', 'end_signal_osm_id'
    """
    # Build all cut points including start (0) and end (line_length)
    all_points = [(0.0, None)] + validated_cuts + [(line_length, None)]

    output_data = []

    for i in range(len(all_points) - 1):
        start_dist, start_osm_id = all_points[i]
        end_dist, end_osm_id = all_points[i + 1]

        if start_dist >= end_dist:
            continue

        # Extract substring from line via interpolation
        num_points = max(int((end_dist - start_dist) / 10), 2)
        distances = np.linspace(start_dist, end_dist, num_points)
        coords = [line.interpolate(d).coords[0] for d in distances]

        if len(coords) >= 2:
            segment_line = shp_LineString(coords)
            output_data.append(
                {
                    "geometry": segment_line,
                    "start_signal_osm_id": start_osm_id,
                    "end_signal_osm_id": end_osm_id,
                }
            )

    # Merge very short last segment with previous
    if len(output_data) >= 2:
        last_seg = output_data[-1]
        if last_seg["geometry"].length < 0.75 * min_segment_length_m:
            prev_seg = output_data[-2]
            merged_coords = (
                list(prev_seg["geometry"].coords)
                + list(last_seg["geometry"].coords)[1:]
            )
            output_data[-2]["geometry"] = shp_LineString(merged_coords)
            # Keep the end_signal from the merged segment
            output_data[-2]["end_signal_osm_id"] = last_seg["end_signal_osm_id"]
            output_data.pop(-1)

    return output_data


def save_segmented_shape_to_db(
    segmented_shape: List[shp_LineString],
    shape_name: str,
    bearing: List[float] = None,
    direction: int = None,
    start_signal_osm_ids: List[Optional[str]] = None,
    end_signal_osm_ids: List[Optional[str]] = None,
    signals_map: Dict[str, TrafficSignal] = None,
):
    """
    Save segmented shape to database.

    Parameters
    ----------
    segmented_shape : List[shp_LineString]
        List of LineString geometries for each segment.
    shape_name : str
        Name for the shape.
    bearing : List[float], optional
        List of bearings for each segment.
    direction : int, optional
        Direction indicator for all segments.
    start_signal_osm_ids : List[Optional[str]], optional
        List of OSM IDs for start signals (one per segment, can be None).
    end_signal_osm_ids : List[Optional[str]], optional
        List of OSM IDs for end signals (one per segment, can be None).
    signals_map : Dict[str, TrafficSignal], optional
        Mapping of osm_id -> TrafficSignal instance for FK lookup.
    """
    shape = Shape.objects.create(**{"name": shape_name})

    for sequence, segment in enumerate(segmented_shape):
        # Look up start/end signals from map
        start_signal = None
        end_signal = None

        if signals_map:
            if start_signal_osm_ids and start_signal_osm_ids[sequence]:
                start_signal = signals_map.get(start_signal_osm_ids[sequence])
            if end_signal_osm_ids and end_signal_osm_ids[sequence]:
                end_signal = signals_map.get(end_signal_osm_ids[sequence])

        shape.add_segment(
            sequence=sequence,
            geometry=segment,
            bearing=bearing[sequence] if bearing else None,
            direction=direction,
            start_signal=start_signal,
            end_signal=end_signal,
        )


def save_all_segmented_shapes_to_db(
    segmented_shapes: List[gpd.GeoDataFrame],
    flush: bool = True,
    shape_name: str = None,
    signals_map: Dict[str, TrafficSignal] = None,
):
    """
    Save all segmented shapes to database.

    Parameters
    ----------
    segmented_shapes : List[gpd.GeoDataFrame]
        List of GeoDataFrames, each containing segments for one direction.
    flush : bool
        If True, delete all existing shapes before saving.
    shape_name : str
        Base name for shapes (direction index will be appended).
    signals_map : Dict[str, TrafficSignal], optional
        Mapping of osm_id -> TrafficSignal instance for FK lookup.
    """
    if flush:
        flush_shape_objects()

    for idx, segmented_shape in enumerate(segmented_shapes):
        if shape_name is not None:
            shape_name_ = f"{shape_name}_{segmented_shape['direction_group'].iloc[0]}"
            direction = segmented_shape["direction_group"].iloc[0]

        # Extract signal OSM IDs from GeoDataFrame columns if present
        start_signal_osm_ids = None
        end_signal_osm_ids = None

        if "start_signal_osm_id" in segmented_shape.columns:
            start_signal_osm_ids = segmented_shape["start_signal_osm_id"].tolist()
        if "end_signal_osm_id" in segmented_shape.columns:
            end_signal_osm_ids = segmented_shape["end_signal_osm_id"].tolist()

        save_segmented_shape_to_db(
            segmented_shape.geometry.tolist(),
            shape_name=shape_name_,
            bearing=segmented_shape.bearing.tolist(),
            direction=direction,
            start_signal_osm_ids=start_signal_osm_ids,
            end_signal_osm_ids=end_signal_osm_ids,
            signals_map=signals_map,
        )


def normalize_geometry_by_bearing(
    gdf: gpd.GeoDataFrame,
    target_bearing: float,
) -> gpd.GeoDataFrame:
    """
    Normalizes all geometries to point in the direction of target_bearing.
    Uses the weighted bearing of each geometry to decide whether to reverse.
    """
    gdf = gdf.copy()

    for idx, row in gdf.iterrows():
        geom = row.geometry

        if isinstance(geom, shp_LineString):
            current_bearing = calculate_bearing(geom)
            if current_bearing is not None:
                diff = min(
                    abs(current_bearing - target_bearing),
                    360 - abs(current_bearing - target_bearing),
                )
                if diff > 90:  # Pointing in opposite direction
                    gdf.at[idx, "geometry"] = shp_LineString(list(geom.coords)[::-1])

        elif isinstance(geom, shp_MultiLineString):
            # For MultiLineString, check general direction
            lines = list(geom.geoms)
            if lines:
                # Use the bearing of the first and last coordinate of the set
                first_coord = list(lines[0].coords)[0]
                last_coord = list(lines[-1].coords)[-1]
                temp_line = shp_LineString([first_coord, last_coord])
                current_bearing = calculate_bearing(temp_line)

                if current_bearing is not None:
                    diff = min(
                        abs(current_bearing - target_bearing),
                        360 - abs(current_bearing - target_bearing),
                    )
                    if diff > 90:
                        # Reverse the entire MultiLineString
                        reversed_lines = [
                            shp_LineString(list(line.coords)[::-1])
                            for line in reversed(lines)
                        ]
                        gdf.at[idx, "geometry"] = shp_MultiLineString(reversed_lines)

    return gdf


def process_osm_queries(
    distance_threshold: float = 500.0,
    use_fixtures: bool = False,
    use_traffic_signals: bool = True,
):
    """Process all the queries in EJES_PRINCIPALES, downloading data from OSM Overpass API,
    or using local fixtures if use_fixtures is True.

    Parameters
    ----------
    distance_threshold : float
        Distance in meters to segment shapes (default: 500.0).
        When use_traffic_signals=True, this is used as fallback_distance.
    use_fixtures : bool
        If True, use local fixtures instead of downloading from OSM.
    use_traffic_signals : bool
        If True, segment by traffic signals with fallback to distance_threshold.
        If False, use traditional fixed-distance segmentation.
    """
    osm_downloader = OSMDownloader()
    axles_qs = Axles.objects.all().order_by("id")
    if not axles_qs.exists():
        print("No Axles found in database. Run: python manage.py seed_axles")
        return

    # Flush traffic signals at the start if using traffic signal mode
    # This ensures we start fresh before any axis saves its signals
    if use_traffic_signals:
        from rest_api.util.traffic_signals import flush_traffic_signals_from_db

        flush_traffic_signals_from_db()
        print("Flushed existing traffic signals from DB")

    # Download relevant ways once for the entire area (if using traffic signals)
    relevant_ways_gdf = None
    if use_traffic_signals:
        # Get the first axis city to download relevant ways (assumes all axes share same city)
        first_axle = axles_qs.first()
        if first_axle:
            print("=" * 50)
            print(f"Downloading relevant ways for area: {first_axle.city}...")
            try:
                ways_query = osm_downloader.build_relevant_ways_query(first_axle.city)
                ways_data = osm_downloader.execute_query(ways_query)
                relevant_ways_gdf = extract_relevant_ways(ways_data)
                print(
                    f"  Downloaded {len(relevant_ways_gdf)} relevant ways (motorway/primary/secondary/tertiary)"
                )
            except Exception as e:
                print(f"  Warning: Could not download relevant ways: {e}")
                print("  Will fall back to distance-based segmentation")

    for idx, axle in enumerate(axles_qs):
        axis_config = {"city": axle.city, "streets": axle.streets}
        try:
            if axle.name == "Eje Américo Vespucio":
                query = VESPUCIO_QUERY
                # Vespucio uses special query, can't use traffic signals template
                use_signals_for_axis = True
            elif axle.name == "Eje Independencia":
                query = INDEPENDENCIA_QUERY
                # Independencia uses special query, can't use traffic signals template
                use_signals_for_axis = True
            else:
                # Use streets+signals template when traffic signals mode is enabled
                query = osm_downloader.build_overpass_query(
                    place=axis_config["city"],
                    streets=axis_config["streets"],
                    include_traffic_signals=use_traffic_signals,
                )
                use_signals_for_axis = (
                    use_traffic_signals and relevant_ways_gdf is not None
                )

            axis = osm_downloader.execute_query(query)
        except Exception as e:
            print(f"Error downloading axis '{axle.name}': {e}")
            continue

        flush = idx == 0
        process_shape_data(
            axle.name,
            axis,
            distance_threshold,
            flush=flush,
            use_traffic_signals=use_signals_for_axis,
            relevant_ways_gdf=relevant_ways_gdf,
        )


def process_shape_data(
    axis_name: str,
    axis: Dict,
    distance_threshold: float = 500.0,
    flush: bool = True,
    use_traffic_signals: bool = False,
    relevant_ways_gdf: gpd.GeoDataFrame = None,
):
    """
    Creates the query, separates shapes, merges them and divides into segments.
    When use_traffic_signals=True, segments are delimited by traffic signals at
    relevant intersections, with fallback to distance_threshold for long gaps.
    Stores all information in the db.

    Parameters
    ----------
    axis_name : str
        Name of the axis being processed.
    axis : Dict
        GeoJSON response from Overpass API (streets + signals query).
    distance_threshold : float
        Distance in meters for segmentation (default: 500.0).
        Used as fallback when use_traffic_signals=True.
    flush : bool
        If True, flush existing shape objects before saving.
    use_traffic_signals : bool
        If True, segment by traffic signals with fallback to distance_threshold.
        If False, use traditional fixed-distance segmentation.
    relevant_ways_gdf : gpd.GeoDataFrame, optional
        Pre-downloaded GeoDataFrame with relevant ways (primary/secondary/tertiary).
        Required when use_traffic_signals=True.
    """
    print("=" * 50)
    print(f"\nProcessing axis: {axis_name} with {len(axis['features'])} features...")
    if use_traffic_signals:
        print("  Mode: Traffic signal-based segmentation")
    else:
        print(f"  Mode: Fixed distance segmentation ({distance_threshold}m)")

    # Validate that we have features to process
    if not axis.get("features") or len(axis["features"]) == 0:
        raise ValueError(
            f"No features found for axis '{axis_name}'. "
            "Please verify that the streets configuration is correct and matches existing OSM data."
        )

    # Extract traffic signals if using traffic signal mode
    relevant_signals = gpd.GeoDataFrame(
        {"geometry": []}, geometry="geometry", crs="EPSG:4326"
    )
    signals_map = {}  # osm_id -> TrafficSignal mapping

    if use_traffic_signals:
        if relevant_ways_gdf is None or relevant_ways_gdf.empty:
            print(
                "  Warning: No relevant ways provided, falling back to distance-based segmentation"
            )
            use_traffic_signals = False
        else:
            streets_gdf, signals_gdf = extract_streets_and_signals(axis)
            print(
                f"  Extracted: {len(streets_gdf)} street segments, {len(signals_gdf)} traffic signals"
            )
            if not signals_gdf.empty:
                print(f"  Signal columns: {list(signals_gdf.columns)}")
            print(f"  Using {len(relevant_ways_gdf)} pre-downloaded relevant ways")

            if not signals_gdf.empty:
                relevant_signals = identify_relevant_traffic_signals(
                    signals_gdf, relevant_ways_gdf
                )
                print(
                    f"  Identified {len(relevant_signals)} relevant traffic signals at major intersections"
                )

                # Save relevant traffic signals to DB BEFORE processing segments
                if not relevant_signals.empty:
                    from rest_api.util.traffic_signals import (
                        save_relevant_traffic_signals,
                    )

                    print(f"  Saving {len(relevant_signals)} traffic signals to DB...")
                    signals_map = save_relevant_traffic_signals(relevant_signals)
                    print(f"  Saved {len(signals_map)} traffic signals to DB")
            else:
                print(
                    "  Warning: No traffic signals found, falling back to distance-based segmentation"
                )

    # Extract features with valid geometry (only LineStrings for the axis)
    query_data = gpd.GeoDataFrame.from_features(axis, crs="EPSG:4326")

    # Filter to only keep LineString geometries (exclude Points which are traffic signals)
    query_data = query_data[query_data.geometry.type == "LineString"].copy()

    # STEP 1: Calculate original bearings
    query_data["original_bearing"] = query_data.geometry.apply(calculate_bearing)

    splitted_gdf = split_axis_by_direction(query_data, bearing_threshold=120.0)

    # STEP 2: Calculate target bearing for each group
    group_bearings = []
    for i, group_gdf in enumerate(splitted_gdf):
        bearings = []
        lengths = []
        for idx, row in group_gdf.iterrows():
            b = row.get("original_bearing") or calculate_bearing(row.geometry)
            if b is not None:
                bearings.append(b)
                geom_metric = gpd.GeoSeries([row.geometry], crs="EPSG:4326").to_crs(
                    "EPSG:3857"
                )[0]
                lengths.append(geom_metric.length)

        if bearings and lengths:
            sum_sin = sum(
                l * math.sin(math.radians(b)) for b, l in zip(bearings, lengths)
            )
            sum_cos = sum(
                l * math.cos(math.radians(b)) for b, l in zip(bearings, lengths)
            )
            target_bearing = (math.degrees(math.atan2(sum_sin, sum_cos)) + 360) % 360
            group_bearings.append(target_bearing)
            print(f"Direction group {i}: target bearing = {target_bearing:.2f}°")
        else:
            group_bearings.append(None)

    segmented_shapes = []

    for i, group_gdf in enumerate(splitted_gdf):
        target_bearing = group_bearings[i]
        if target_bearing is None:
            continue

        # STEP 3: Normalize geometries BEFORE any processing
        group_gdf = normalize_geometry_by_bearing(group_gdf, target_bearing)

        # Verify normalization
        normalized_bearings = group_gdf.geometry.apply(calculate_bearing)
        avg_normalized = normalized_bearings.mean()
        print(
            f"Group {i} - Bearing after normalization: {avg_normalized:.2f}° (target: {target_bearing:.2f}°)"
        )

        group_gdf["direction_group"] = i
        group_gdf["group_size"] = len(group_gdf)
        group_gdf["eje_name"] = axis_name
        group_gdf["target_bearing"] = target_bearing

        merged = merge_lines_with_metadata(group_gdf)
        print(f"Merged shape for direction group {i} has {len(merged)} lines.")

        one_road_gdf = keep_main_axis_lines(merged)
        print(f"One road shape for direction group {i} has {len(one_road_gdf)} lines.")

        conected_gdf = connect_lines(one_road_gdf, max_distance_m=510.0)
        print(f"Connected shape for direction group {i} has {len(conected_gdf)} lines.")

        filtered_gdf = filter_short_lines(conected_gdf)
        print(f"Filtered shape for direction group {i} has {len(filtered_gdf)} lines.")

        # STEP 4: Verify final orientation and correct if necessary
        final_bearing = calculate_bearing(filtered_gdf.geometry.iloc[0])

        # Handle case where bearing calculation returns None
        if final_bearing is None:
            print(
                f"Warning: Could not calculate final bearing for group {i}, using target bearing"
            )
            final_bearing = target_bearing

        bearing_diff = min(
            abs(final_bearing - target_bearing),
            360 - abs(final_bearing - target_bearing),
        )

        if bearing_diff > 90:
            print(
                f"Correcting final orientation: {final_bearing:.2f}° -> {target_bearing:.2f}°"
            )
            filtered_gdf["geometry"] = filtered_gdf.geometry.apply(
                lambda g: orient_linestring_by_bearing(g, target_bearing)
            )
            final_bearing = calculate_bearing(filtered_gdf.geometry.iloc[0])

        print(
            f"Final bearing for group {i}: {final_bearing:.2f}° (target: {target_bearing:.2f}°)"
        )
        print("=" * 50)

        # STEP 5: Segment - use traffic signals or distance-based
        if use_traffic_signals and not relevant_signals.empty:
            print(f"  Segmenting direction group {i} by traffic signals...")
            segmented = segment_shape_by_traffic_signals(
                filtered_gdf,
                relevant_signals,
                fallback_distance_m=distance_threshold,
            )
        else:
            segmented = segment_shape_by_distance(
                filtered_gdf, distance_threshold, distance_algorithm="haversine"
            )

        segmented["target_bearing"] = target_bearing

        file_path = "debug"
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        segmented.to_file(
            f"{file_path}/segmented_shape_{axis_name}_{i}.geojson", driver="GeoJSON"
        )
        segmented_shapes.append(segmented)
    print("Saving all segmented shapes to DB...")
    save_all_segmented_shapes_to_db(
        segmented_shapes, flush=flush, shape_name=axis_name, signals_map=signals_map
    )


def process_single_axis(
    axis_name: str,
    distance_threshold: float = 500.0,
    use_traffic_signals: bool = True,
):
    """
    Process a single axis without deleting existing data.
    First removes any existing shapes with the same name, then adds the new axis.

    Parameters
    ----------
    axis_name : str
        Name of the axis to process (must exist in Axles table)
    distance_threshold : float
        Distance in meters to segment shapes (default: 500.0).
        When use_traffic_signals=True, this is used as fallback_distance.
    use_traffic_signals : bool
        If True, segment by traffic signals with fallback to distance_threshold.
        If False, use traditional fixed-distance segmentation.
    """
    osm_downloader = OSMDownloader()

    # Get axis configuration from database
    try:
        axle = Axles.objects.get(name=axis_name)
        axis_config = {"city": axle.city, "streets": axle.streets}
    except Axles.DoesNotExist:
        raise ValueError(f"Axis '{axis_name}' not found in Axles table")

    # Remove existing shapes for this axis (both directions)
    existing_shapes = Shape.objects.filter(name__startswith=f"{axis_name}_")
    if existing_shapes.exists():
        print(f"Removing {existing_shapes.count()} existing shapes for {axis_name}")
        for shape in existing_shapes:
            # Remove segments and related data for this shape
            shape.segment_set.all().delete()
        existing_shapes.delete()

    # Download relevant ways if using traffic signals
    relevant_ways_gdf = None
    use_signals_for_axis = False

    if use_traffic_signals:
        # Check if this is a special axis that can't use traffic signals
        if axis_name in ("Eje Américo Vespucio", "Eje Independencia"):
            print(
                f"  Note: {axis_name} uses special query, traffic signals mode disabled"
            )
        else:
            print(f"Downloading relevant ways for area: {axis_config['city']}...")
            try:
                ways_query = osm_downloader.build_relevant_ways_query(
                    axis_config["city"]
                )
                ways_data = osm_downloader.execute_query(ways_query)
                relevant_ways_gdf = extract_relevant_ways(ways_data)
                print(f"  Downloaded {len(relevant_ways_gdf)} relevant ways")
                use_signals_for_axis = True
            except Exception as e:
                print(f"  Warning: Could not download relevant ways: {e}")

    # Download OSM data for the axis
    try:
        if axis_name == "Eje Américo Vespucio":
            query = VESPUCIO_QUERY
        elif axis_name == "Eje Independencia":
            query = INDEPENDENCIA_QUERY
        else:
            query = osm_downloader.build_overpass_query(
                place=axis_config["city"],
                streets=axis_config["streets"],
                include_traffic_signals=use_signals_for_axis,
            )

        axis = osm_downloader.execute_query(query)
    except Exception as e:
        raise Exception(f"Error downloading axis '{axis_name}': {e}")

    # Process the axis (flush=False to keep other data)
    process_shape_data(
        axis_name,
        axis,
        distance_threshold,
        flush=False,
        use_traffic_signals=use_signals_for_axis,
        relevant_ways_gdf=relevant_ways_gdf,
    )
