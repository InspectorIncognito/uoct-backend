import json
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
from rest_api.models import Segment, Services, Shape
from rest_api.util.gtfs import GTFSShapeManager
from rest_api.util.hmm.services_hmm import build_matched_features, match_shapes_to_axes
from rest_api.util.shape import ShapeManager
from shapely.geometry import LineString as shp_LineString
from shapely.geometry import MultiLineString as shp_MultiLineString
from shapely.geometry import Point as shp_Point
from shapely.ops import nearest_points


def flush_services_from_db():
    print("Flushing all Services rows from DB")
    try:
        Services.objects.all().delete()
    except Exception as e:
        print(f"Failed to flush Services from DB: {e}")


def create_services(segment, services):
    try:
        Services.objects.create(segment=segment, services=services)
    except Exception as e:
        print(
            "Failed creating Services for segment=%s with services=%s: %s"
            % (getattr(segment, "segment_id", str(segment)), services, e)
        )


def _linestring_to_points(ls: shp_LineString) -> List[shp_Point]:
    return [shp_Point(x, y) for x, y in ls.coords]


def _multilinestring_to_points(mls: shp_MultiLineString) -> List[shp_Point]:
    pts: List[shp_Point] = []
    for ls in mls.geoms:
        pts.extend(_linestring_to_points(ls))
    return pts


def _compute_bearings(points: List[shp_Point]) -> List[Optional[float]]:
    """
    Compute bearings using geodesic formula (bearing_from_coords),
    assuming input points are in EPSG:4326 (lon/lat).
    """
    import math

    def bearing_from_coords(a, b) -> float:
        # a, b are tuples (lon, lat)
        lat1, lon1 = math.radians(a[1]), math.radians(a[0])
        lat2, lon2 = math.radians(b[1]), math.radians(b[0])
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
            lat2
        ) * math.cos(dlon)
        brng = math.degrees(math.atan2(y, x))
        return (brng + 360) % 360

    bearings: List[Optional[float]] = []
    prev: Optional[shp_Point] = None

    for p in points:
        if prev is None:
            bearings.append(None)
        else:
            # Convert shapely Point -> (lon, lat)
            a = (prev.x, prev.y)
            b = (p.x, p.y)

            # If same point → no bearing
            if a == b:
                bearings.append(None)
            else:
                bearings.append(bearing_from_coords(a, b))

        prev = p

    return bearings


def load_shapes_as_trajectories(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Convert GTFS routes them into trajectory rows.

    Returns a DataFrame with columns:
      - shape_id (str)
      - route_id (str|None)
      - direction_id (int|str|None)
      - points (List[Point])
      - bearings (List[Optional[float]])
      - n_points (int)
    """

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)

    print(f"Converting GTFS features to trajectories (input rows={len(gdf)})")

    # Identify columns
    shape_col = "shape_id" if "shape_id" in gdf.columns else None
    if shape_col is None:
        # Fallback to index
        gdf = gdf.copy()
        gdf["shape_id"] = gdf.index.astype(str)

    # Ensure presence of expected metadata columns (may be missing)
    for col in ["route_id", "direction_id"]:
        if col not in gdf.columns:
            gdf[col] = None

    rows = []
    for _, r in gdf.iterrows():
        geom = r.geometry
        if geom is None:
            continue
        if isinstance(geom, shp_LineString):
            pts = _linestring_to_points(geom)
        elif isinstance(geom, shp_MultiLineString):
            pts = _multilinestring_to_points(geom)
        else:
            continue

        # Remove consecutive duplicates
        cleaned = []
        for p in pts:
            if not cleaned or (p.x != cleaned[-1].x or p.y != cleaned[-1].y):
                cleaned.append(p)

        if len(cleaned) < 2:
            continue

        bearings = _compute_bearings(cleaned)

        rows.append(
            {
                "shape_id": str(r["shape_id"]),
                "route_id": None if pd.isna(r["route_id"]) else r["route_id"],
                "direction": (
                    None if pd.isna(r["direction_id"]) else r["direction_id"]
                ),
                # For reuse with existing batch matcher
                "license_plate": str(r["shape_id"]),
                "points": cleaned,
                "bearings": bearings,
                "n_points": len(cleaned),
            }
        )

    df = pd.DataFrame(rows)

    # Filter tiny shapes
    MIN_POINTS = 3
    df = df[df["n_points"] >= MIN_POINTS].reset_index(drop=True)
    print(f"Filtered trajectories: kept {len(df)} (min_points={MIN_POINTS})")
    return df


def load_segments_per_axis(shape_manager: ShapeManager) -> Dict[str, gpd.GeoDataFrame]:
    """Load segmented axes from a folder combining both directions per axis."""
    axis_segments: Dict[str, gpd.GeoDataFrame] = {}
    shapes = shape_manager.shapes.all()
    print(f"Loading segments per axis for {shapes.count()} shapes")
    for shape in shapes:
        axis_name = shape.name.rsplit("_", 1)[0]
        segments = shape.get_segments_gdf()
        # (debug removed)
        if axis_name in axis_segments:
            axis_segments[axis_name] = pd.concat(
                [axis_segments[axis_name], segments], ignore_index=True
            )
        else:
            axis_segments[axis_name] = segments

    return axis_segments


def assign_routes_to_segments(
    max_distance: float = 40.0,
    sigma: float = 20,
    beta: float = 40,
    bearing_weight_factor: float = 0.5,
    sigma_bearing: float = 40,
):
    """
    Asigna TODAS las rutas (GTFS) que pasan cerca de cada segmento y las guarda en DB.
    - Usa HMM para emparejar trayectorias (rutas GTFS) a ejes (segmentos por axis).
    - Agrega por segmento todas las route_id observadas.
    - Persiste usando create_services(segment, services).
    """
    # Limpia servicios previos para evitar duplicados/inconsistencias
    print("Starting assign_routes_to_segments")
    flush_services_from_db()

    gtfs_shape_manager = GTFSShapeManager()
    shape_manager = ShapeManager()

    # 1) Cargar rutas GTFS como FeatureCollection y a GeoDataFrame
    gtfs_routes = gtfs_shape_manager.to_geojson()
    try:
        gtfs_gdf = gpd.GeoDataFrame.from_features(gtfs_routes)
    except Exception as e:
        print(f"Failed to build GeoDataFrame from GTFS routes: {e}")
        raise
    print(f"Loaded GTFS routes: {len(gtfs_gdf)} features")

    # 2) Convertir rutas GTFS a trayectorias (lista de puntos + bearings)
    shapes_trajectories = load_shapes_as_trajectories(gtfs_gdf)
    print(f"Prepared {len(shapes_trajectories)} GTFS trajectories for matching")

    # 3) Construir GDF de segmentos por axis (concatenando direcciones del mismo eje)
    axis_segments = load_segments_per_axis(shape_manager)
    print(f"Prepared {len(axis_segments)} axes for matching")
    total_segments = sum(len(gdf) for gdf in axis_segments.values() if gdf is not None)
    print(f"Total segments available across axes: {total_segments}")

    # 4) Ejecutar el emparejamiento HMM en batch
    print(f"Running batch HMM matching on {len(shapes_trajectories)} trajectories")
    batch_results = match_shapes_to_axes(
        shapes_trajectories,
        axis_segments,
        max_distance=max_distance,
        sigma=sigma,
        beta=beta,
        bearing_weight_factor=bearing_weight_factor,
        sigma_bearing=sigma_bearing,
    )
    print(f"Batch matching completed: matched trajectories={len(batch_results)}")

    # 5) Mapa shape_id -> route_id para recuperar la ruta de cada shape
    #    (shapes_trajectories ya trae route_id por shape_id)
    route_by_shape = (
        shapes_trajectories[["shape_id", "route_id"]]
        .drop_duplicates()
        .set_index("shape_id")["route_id"]
        .to_dict()
    )

    # 6) Agregar por segmento todas las rutas observadas
    #    matched_segment_index es índice de fila en el GDF de ese axis.
    routes_per_segment: Dict[str, set] = {}

    for shape_id, axis_map in batch_results.items():
        route_id = route_by_shape.get(shape_id)
        if route_id is None or (isinstance(route_id, float) and pd.isna(route_id)):
            continue  # sin route_id, no se agrega servicio

        for axis_id, (
            matched_segments,
            valid_indices,
            _projected_points,
        ) in axis_map.items():
            gdf = axis_segments.get(axis_id)
            if gdf is None or gdf.empty:
                continue

            for idx in valid_indices:
                seg_idx = matched_segments[idx]
                if seg_idx is None:
                    continue
                try:
                    row = gdf.iloc[int(seg_idx)]
                except Exception:
                    continue

                # Se espera que el GDF tenga la columna 'segment_id' (UUID de Segment)
                seg_uuid = row.get("segment_id")
                if seg_uuid is None or (
                    isinstance(seg_uuid, float) and pd.isna(seg_uuid)
                ):
                    continue

                routes_per_segment.setdefault(str(seg_uuid), set()).add(str(route_id))

    print(f"Routes per segment found: {len(routes_per_segment)} segments")

    # 7) Resolver segmentos en un solo query y crear Services por segmento
    segment_ids = list(routes_per_segment.keys())
    seg_qs = Segment.objects.filter(segment_id__in=segment_ids)
    seg_map = {str(s.segment_id): s for s in seg_qs}

    created = 0
    for seg_id, routes in routes_per_segment.items():
        seg = seg_map.get(seg_id)
        if not seg:
            continue
        # create_services escribe 1 fila por segmento con el conjunto de rutas
        create_services(seg, sorted(routes))
        created += 1
    print(f"Created Services records: {created}")


def get_all_services():
    shape_data = {}
    for service in Services.objects.all():
        shape_id = service.segment.shape.pk
        set_services = shape_data.get(shape_id, set())
        set_services.update(service.services)
        shape_data[shape_id] = set_services
    return shape_data


def get_shape_by_route_id(shape_data, route_id):
    for shape_id in shape_data:
        if route_id in shape_data[shape_id]:
            return str(shape_id)
    return None
