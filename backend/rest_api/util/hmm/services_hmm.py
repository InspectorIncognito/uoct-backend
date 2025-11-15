import os
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from rest_api.util.hmm.hmm import batch_match_trajectories_to_axes
# Reuse core HMM implementation

def match_shapes_to_axes(
    shapes_df: pd.DataFrame,
    axes: Dict[str, gpd.GeoDataFrame],
    *,
    max_distance: float = 50,
    sigma: float = 30,
    beta: float = 40,
    bearing_weight_factor: float = 0.5,
    sigma_bearing: float = 40,
):
    """Run batch HMM matching on shapes DataFrame.

    This function reuses batch_match_trajectories_to_axes by treating shape_id as
    license_plate for keying, but preserves shape metadata to emit later.

    Returns
    -------
    batch_results : dict
        shape_id -> { axis_id -> (matched_segments, valid_indices, projected_points) }
    """
    # Ensure required columns exist
    required = {"shape_id", "points", "bearings"}
    missing = required - set(shapes_df.columns)
    if missing:
        raise ValueError(f"shapes_df missing required columns: {missing}")

    # Directly call batch matcher using flexible id_column support (no masking needed)
    results = batch_match_trajectories_to_axes(
        shapes_df,
        axes,
        max_distance=max_distance,
        sigma=sigma,
        beta=beta,
        bearing_weight_factor=bearing_weight_factor,
        sigma_bearing=sigma_bearing,
        id_column="shape_id",
    )
    return results


def build_matched_features(
    batch_results: Dict[
        str, Dict[str, Tuple[List[Optional[int]], List[int], List[Optional[Point]]]]
    ],
    shapes_df: pd.DataFrame,
):
    """Convert batch matching results into GeoJSON-like features including
    route_id, direction_id, and shape_id attributes.
    """
    # Map shape metadata
    meta = shapes_df.set_index("shape_id")[
        [c for c in ["route_id", "direction"] if c in shapes_df.columns]
    ].to_dict(orient="index")

    features = []
    for shape_id, axis_results in batch_results.items():
        shape_meta = meta.get(shape_id, {})
        route_id = shape_meta.get("route_id")
        direction_id = shape_meta.get("direction")

        for axis_id, (
            matched_segments,
            valid_indices,
            projected_points,
        ) in axis_results.items():
            for idx in valid_indices:
                seg_idx = matched_segments[idx]
                point = projected_points[idx]
                if point is None or seg_idx is None:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "shape_id": shape_id,
                            "route_id": route_id,
                            "direction_id": direction_id,
                            "axis_id": axis_id,
                            "matched_segment_index": int(seg_idx),
                            "gps_point_index": int(idx),
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [point.x, point.y],
                        },
                    }
                )
    return features