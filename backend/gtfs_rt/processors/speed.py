import datetime
import time
from typing import List, Optional

import geopandas as gpd
import pandas as pd
from gtfs_rt.utils import get_last_temporal_range
from rest_api.models import Segment, Speed
from shapely.geometry import Point
from velocity.expedition import ExpeditionData
from velocity.grid import GridManager
from velocity.segment import FiveHundredMeterSegmentCriteria
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager


def calculate_speed(
    start_date: datetime.datetime = None, end_date: datetime.datetime = None
):
    print("Calling calculate_speed command...")
    if start_date is None or end_date is None:
        start_date, end_date = get_last_temporal_range()
    today_weekday = start_date.weekday()
    today_weekday = "L" if today_weekday < 5 else "S" if today_weekday == 5 else "D"

    grid_obj: GridManager = generate_grid()

    vm = VehicleManager(grid_obj)

    gps_df: pd.DataFrame = grid_obj.filter_gps_from_dates(start_date, end_date)
    print(f"Retrieved {len(gps_df)} GPS Pulses.")

    start_time = time.time()
    for _, gps in gps_df.iterrows():
        vm.add_data(gps)
    end_time = time.time()
    print(f"GPS processed in {int(end_time - start_time)} seconds.")

    print(f"Running HMM map matching for speed calculation...")
    start_time = time.time()
    batch_results = grid_obj.run_hmm_map_matching(vm)
    end_time = time.time()
    print(f"HMM map matching completed in {int(end_time - start_time)} seconds.")
    # TODO: usar los bacth_results para actualizar shape_id en las expediciones y otros parametros para calcular velocidades
    # Lo mas probable es que tenga que actaulizar calculate_speed

    # TODO: si hay mas de un shape_id crear una expedicion por shape_id
    def determine_shape_id_from_matched_segments_optimized(
        matched_segments: List[Optional[int]],
        valid_indices: List[int],
        segments_gdf: gpd.GeoDataFrame,
    ) -> int:
        """
        Determina el shape_id más frecuente, usando segments_gdf.
        """
        from collections import Counter

        # Asumiendo que segments_gdf tiene una columna 'shape_id'
        shape_ids = []
        for idx in valid_indices:
            seg_pk = matched_segments[idx]
            if seg_pk is not None:
                # Buscar en el GeoDataFrame
                row = segments_gdf[segments_gdf.segment_pk == seg_pk]
                if not row.empty:
                    shape_ids.append(row.iloc[0]["shape_id"])

        if not shape_ids:
            return None

        return Counter(shape_ids).most_common(1)[0][0]

    def calculate_cumulative_distance_from_hmm(
        segment_pk: int, projected_point: Point, segments_gdf: gpd.GeoDataFrame
    ) -> float:
        """
        Calcula la distancia acumulada desde el inicio de la ruta
        hasta el punto proyectado en el segmento.
        """
        # Obtener el segmento
        segment_row = segments_gdf[segments_gdf.segment_pk == segment_pk].iloc[0]

        # Distancia acumulada hasta el inicio de este segmento
        # (asumiendo que segments_gdf tiene una columna 'cumulative_distance' o similar)
        distance_to_segment_start = segment_row.get("distance_start", 0)

        # Distancia desde el inicio del segmento hasta el punto proyectado
        segment_geom = segment_row.geometry
        distance_along_segment = segment_geom.project(
            Point(projected_point.x, projected_point.y)
        )

        return distance_to_segment_start + distance_along_segment

    def update_expedition_from_hmm_results(
        expedition: ExpeditionData,
        axis_id: str,  # "Eje Alameda"
        matched_segments: List[Optional[int]],  # [seg_pk_1, seg_pk_2, ...]
        valid_indices: List[int],
        projected_points: List[Optional[Point]],
        segments_gdf: gpd.GeoDataFrame,  # GeoDataFrame del axis_id
    ):
        """
        Actualiza la expedición con los resultados del HMM.
        """
        # 1. Determinar el shape_id real (no el axis_id)
        shape_id = determine_shape_id_from_matched_segments_optimized(
            matched_segments, valid_indices, segments_gdf
        )

        if shape_id is None:
            raise ValueError(
                f"No se pudo determinar shape_id para expedición {expedition}"
            )

        expedition.shape_id = shape_id  # ✅ Ahora es el pk correcto

        # 2. Inicializar arrays
        expedition.gps_distance_on_route = [None] * len(expedition.gps_points)
        expedition.gps_distance_to_route = [None] * len(expedition.gps_points)

        # 3. Llenar con proyecciones del HMM
        for idx in valid_indices:
            segment_pk = matched_segments[idx]
            projected_point = projected_points[idx]

            if segment_pk is not None and projected_point is not None:
                # Calcular distancia acumulada en la ruta
                distance_on_route = calculate_cumulative_distance_from_hmm(
                    segment_pk, projected_point, segments_gdf
                )
                expedition.gps_distance_on_route[idx] = distance_on_route

                # Distancia perpendicular
                gps_point = expedition.gps_points[idx]
                distance_to_route = haversine_distance(
                    gps_point.latitude,
                    gps_point.longitude,
                    projected_point.y,
                    projected_point.x,
                )
                expedition.gps_distance_to_route[idx] = distance_to_route

    segment_criteria = FiveHundredMeterSegmentCriteria(grid_obj)
    speed_records = vm.calculate_speed(segment_criteria)
    df = pd.DataFrame.from_records(speed_records)[
        [
            "shape_id",
            "spatial_segment_index",
            "local_temporal_segment_index",
            "distance_mts",
            "time_secs",
        ]
    ]
    df = (
        df.groupby(
            ["shape_id", "spatial_segment_index", "local_temporal_segment_index"]
        )
        .agg({"distance_mts": "sum", "time_secs": "sum"})
        .reset_index()
    )
    df = df.round({"distance_mts": 2, "time_secs": 2})

    df["speed(km/h)"] = round(3.6 * df["distance_mts"] / df["time_secs"], 2)

    # Removing outliers
    # TODO: Remove outliers using historical data (with medians)
    lower_threshold = 4
    upper_threshold = 80
    df = df[
        (df["speed(km/h)"] > lower_threshold) & (df["speed(km/h)"] <= upper_threshold)
    ]

    for row, data in df.iterrows():
        shape_id = data["shape_id"]
        sequence = data["spatial_segment_index"]
        temporal_segment = data["local_temporal_segment_index"]
        distance = data["distance_mts"]
        time_secs = data["time_secs"]
        try:
            segment = Segment.objects.get(shape_id=shape_id, sequence=sequence)
        except Segment.DoesNotExist:
            print(f"Segment {sequence} from shape {shape_id} does not exists")
            continue
        else:
            speed_data = dict(
                segment=segment,
                temporal_segment=temporal_segment,
                day_type=today_weekday,
                distance=distance,
                time_secs=time_secs,
                timestamp=start_date,
            )
            Speed.objects.create(**speed_data)
    print("Speed records up to date.")
