from __future__ import annotations

import math
import traceback
from collections import Counter
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import geopandas as gpd
import pandas as pd
from django.utils import timezone
from geojson import Feature
from geojson import Point as GeoPoint
from gtfs_rt.models import GPSPulse
from gtfs_rt.services import get_gps_data_from_last_15_minutes
from processors.geometry.line import PolylineSegment
from processors.geometry.point import Point
from rest_api.models import Segment
from rest_api.util.hmm.hmm import haversine_distance, viterbi
from rest_api.util.shape import ShapeManager
from shapely.geometry import LineString as shp_LineString
from shapely.geometry import Point as shp_Point
from velocity.expedition import ExpeditionData

if TYPE_CHECKING:
    from velocity.vehicle import VehicleManager

DISTANCE_THRESHOLD = 40  # meters


class GridCell:
    def __init__(self, i: int, j: int):
        self.i = i
        self.j = j

        self.route_segments = dict()


class GridManager(Dict[Tuple[int, int], GridCell]):
    def __init__(self):
        super().__init__()
        self.shape_manager = ShapeManager()
        self.expected_cell_size_in_meters = 500.0

        # Distance between cells in the latitudinal and longitudinal directions.
        self.grid_latitude_distance = 0
        self.grid_longitude_distance = 0

        # Minimum latitude and longitude of the grid
        self.grid_min_latitude = 0
        self.grid_min_longitude = 0

        # Number of cells in the longitudinal and latitudinal directions
        self.longitude_cells_number = 0
        self.latitude_cells_number = 0

        # Matrix representing the grid
        self.grid = None
        self.bbox = None

    def get_gps_gdf(self, queryset):
        features = []
        for gps in queryset:
            timestamp = gps.timestamp
            timestamp = timezone.localtime(value=timestamp)
            route_id = gps.route_id
            direction = gps.direction
            license_plate = gps.license_plate
            bearing = gps.bearing
            feat = Feature(
                geometry=GeoPoint(coordinates=[gps.longitude, gps.latitude]),
                properties=dict(
                    route_id=route_id,
                    direction=direction,
                    bearing=bearing,
                    license_plate=license_plate,
                    timestamp=timestamp,
                ),
            )
            features.append(feat)
        gdf = gpd.GeoDataFrame.from_features(features)
        return gdf

    def filter_gps(self):
        queryset = get_gps_data_from_last_15_minutes()
        gps_gdf = self.get_gps_gdf(queryset)
        return gps_gdf

    def filter_gps_from_dates(self, start_date, end_date):
        queryset = GPSPulse.objects.filter(
            timestamp__gte=start_date, timestamp__lte=end_date
        )
        gps_gdf = self.get_gps_gdf(queryset)
        return gps_gdf

    def process(self):
        grid = self.__create_grid()
        grid = self.__process_routes(grid)
        self.grid = grid

    def set_bbox(self, bbox: Tuple[int, int, int, int]):
        self.bbox = bbox

    def get_bbox(self) -> Tuple[int, int, int, int]:
        return self.bbox

    def contains_gps(self, gps_point):
        grid_min_lon, grid_min_lat, grid_max_lon, grid_max_lat = self.get_bbox()
        gps_lat = gps_point.latitude
        gps_lon = gps_point.longitude
        lat_cond = grid_min_lat <= gps_lat <= grid_max_lat
        lon_cond = grid_min_lon <= gps_lon <= grid_max_lon
        return lat_cond and lon_cond

    def get_grid(self):
        output_dict = dict()
        for k, v in self.grid.items():
            cell_dict = output_dict.get(str(k)) or dict()
            for shape_id, segments in v.route_segments.items():
                out_segments = []
                for segment in segments:
                    out_segments.append(str(segment))
                cell_dict[shape_id] = out_segments
            output_dict[str(k)] = cell_dict
        return output_dict

    def __create_grid(self):
        bbox = self.shape_manager.get_bbox()

        grid_min_lon = bbox[0]
        grid_min_lat = bbox[1]
        grid_max_lon = bbox[2]
        grid_max_lat = bbox[3]

        lat_dist = Point(grid_min_lat, grid_min_lon).distance(
            Point(grid_max_lat, grid_min_lon), algorithm="haversine"
        )
        lon_dist = Point(grid_min_lat, grid_min_lon).distance(
            Point(grid_min_lat, grid_max_lon), algorithm="haversine"
        )

        # Calcular número de celdas (truncar para obtener celdas completas)
        lat_cells_complete = int(lat_dist / self.expected_cell_size_in_meters)
        lon_cells_complete = int(lon_dist / self.expected_cell_size_in_meters)

        # Calcular distancia restante
        lat_remainder = lat_dist - (
            lat_cells_complete * self.expected_cell_size_in_meters
        )
        lon_remainder = lon_dist - (
            lon_cells_complete * self.expected_cell_size_in_meters
        )

        # Si el resto es menor a 0.75 * expected_cell_size, se junta con la última celda
        # De lo contrario, se crea una celda adicional
        if lat_remainder >= 0.75 * self.expected_cell_size_in_meters:
            self.latitude_cells_number = lat_cells_complete + 1
        else:
            self.latitude_cells_number = lat_cells_complete

        if lon_remainder >= 0.75 * self.expected_cell_size_in_meters:
            self.longitude_cells_number = lon_cells_complete + 1
        else:
            self.longitude_cells_number = lon_cells_complete

        delta_lat = grid_max_lat - grid_min_lat
        delta_lon = grid_max_lon - grid_min_lon

        # Calculate the distance between latitude and longitude cells
        self.grid_latitude_distance = delta_lat / self.latitude_cells_number
        self.grid_longitude_distance = delta_lon / self.longitude_cells_number

        # Store grid parameters
        self.grid_min_latitude = grid_min_lat
        self.grid_min_longitude = grid_min_lon

        grid_min_lon -= 0.001
        grid_min_lat -= 0.001
        grid_max_lon += 0.001
        grid_max_lat += 0.001

        self.set_bbox((grid_min_lon, grid_min_lat, grid_max_lon, grid_max_lat))

        # Return an empty dictionary
        return {}

    def __process_routes(
        self, grid: Dict[Tuple[int, int], GridCell]
    ) -> Dict[Tuple[int, int], GridCell]:
        segments: Dict[int, List[Segment]] = self.shape_manager.get_segments()
        for shape_id, segments in segments.items():
            shape_id = str(shape_id)
            prev_tuple: List[float] | None = None
            current_distance = 0
            current_sequence = 0
            for segment in segments:
                coords: List[List[float]] = segment.geometry
                for coord in coords:
                    if prev_tuple is None:
                        prev_tuple = coord
                        continue
                    prev_latitude = prev_tuple[1]
                    prev_longitude = prev_tuple[0]
                    curr_lat = coord[1]
                    curr_lon = coord[0]
                    p1 = Point(latitude=prev_latitude, longitude=prev_longitude)
                    p2 = Point(latitude=curr_lat, longitude=curr_lon)

                    segment_obj = PolylineSegment(
                        p1, p2, current_distance, current_sequence
                    )
                    if segment_obj.length == 0:  # Skip segments with zero length
                        prev_tuple = coord
                        continue

                    current_distance += segment_obj.length
                    current_sequence += 1

                    affected_cells = self.__process_segment(p1, p2)

                    for cell in affected_cells:
                        cell_data = grid.get((cell[0], cell[1])) or GridCell(
                            cell[0], cell[1]
                        )
                        segment_array = cell_data.route_segments.get(shape_id) or []
                        segment_array.append(segment_obj)
                        cell_data.route_segments[shape_id] = segment_array

                        grid[cell[0], cell[1]] = cell_data
                    prev_tuple = coord
        return grid

    def get_cell_indexes_from_point(self, lat: float, lon: float) -> Tuple[int, int]:
        lat_index = int((lat - self.grid_min_latitude) / self.grid_latitude_distance)
        lon_index = int((lon - self.grid_min_longitude) / self.grid_longitude_distance)

        # Asegurar que los índices estén dentro del rango válido
        lat_index = min(lat_index, self.latitude_cells_number - 1)
        lon_index = min(lon_index, self.longitude_cells_number - 1)
        lat_index = max(lat_index, 0)
        lon_index = max(lon_index, 0)

        return lat_index, lon_index

    def __process_segment(self, p1: Point, p2: Point) -> List[Tuple[int, int]]:
        current_segment = shp_LineString(coordinates=[p1.coordinates, p2.coordinates])
        p1_cell = self.get_cell_indexes_from_point(p1.latitude, p1.longitude)
        p2_cell = self.get_cell_indexes_from_point(p2.latitude, p2.longitude)

        affected_cells = []

        # Line in the same grid
        if p1_cell[0] == p2_cell[0] and p1_cell[1] == p2_cell[1]:
            affected_cells.append(p1_cell)

        elif p1_cell[0] == p2_cell[0]:
            for j in range(
                min(p1_cell[1], p2_cell[1]), max(p1_cell[1], p2_cell[1]) + 1
            ):
                affected_cells.append((p1_cell[0], j))

        elif p1_cell[1] == p2_cell[1]:
            for i in range(
                min(p1_cell[0], p2_cell[0]), max(p1_cell[0], p2_cell[0]) + 1
            ):
                affected_cells.append((i, p1_cell[1]))

        else:
            pa = Point(min(p1.latitude, p2.latitude), min(p1.longitude, p2.longitude))
            pb = Point(max(p1.latitude, p2.latitude), max(p1.longitude, p2.longitude))

            pa_indexes = self.get_cell_indexes_from_point(pa.latitude, pa.longitude)
            pb_indexes = self.get_cell_indexes_from_point(pb.latitude, pb.longitude)

            for i in range(pa_indexes[0], pb_indexes[0] + 1):
                for j in range(pa_indexes[1], pb_indexes[1] + 1):
                    cell_segments = self.__get_cell_segments(i, j)

                    s0 = cell_segments[0].intersects(current_segment)
                    s1 = cell_segments[1].intersects(current_segment)
                    s2 = cell_segments[2].intersects(current_segment)
                    s3 = cell_segments[3].intersects(current_segment)

                    if s0 or s1 or s2 or s3:
                        affected_cells.append((i, j))
        return affected_cells

    def __get_cell_segments(self, i: int, j: int) -> List[shp_LineString]:
        v1 = (
            self.grid_min_latitude + (self.grid_latitude_distance * i),
            self.grid_min_longitude + (self.grid_longitude_distance * j),
        )

        v2 = (
            self.grid_min_latitude + (self.grid_latitude_distance * (i + 1)),
            self.grid_min_longitude + (self.grid_longitude_distance * j),
        )

        v3 = (
            self.grid_min_latitude + (self.grid_latitude_distance * (i + 1)),
            self.grid_min_longitude + (self.grid_longitude_distance * (j + 1)),
        )

        v4 = (
            self.grid_min_latitude + (self.grid_latitude_distance * i),
            self.grid_min_longitude + (self.grid_longitude_distance * (j + 1)),
        )

        segments = [
            shp_LineString(coordinates=[v1, v2]),
            shp_LineString(coordinates=[v2, v3]),
            shp_LineString(coordinates=[v3, v4]),
            shp_LineString(coordinates=[v4, v1]),
        ]
        return segments

    def get_on_route_distances(
        self,
        point: Point,
        shape_id: str,
        previous_distance=None,
        threshold=DISTANCE_THRESHOLD,
    ) -> Optional[Tuple[float, float]]:
        segments = set()
        lat_index, lon_index = self.get_cell_indexes_from_point(
            point.latitude, point.longitude
        )

        for i in range(lat_index - 1, lat_index + 2):
            for j in range(lon_index - 1, lon_index + 2):
                cell_data = self.grid.get((i, j))
                if cell_data is None or shape_id not in cell_data.route_segments:
                    continue
                else:
                    segments.update(cell_data.route_segments[shape_id])
        segments = list(segments)
        segments = sorted(segments, key=lambda x: x.sequence)

        projection = None
        distance = None

        if previous_distance is None:
            if len(segments) > 1:
                max_index = max(segments, key=lambda x: x.sequence).sequence
                min_index = min(segments, key=lambda x: x.sequence).sequence

                if max_index - min_index + 1 == len(segments):
                    distance, projection = self.__get_distances_from_segments(
                        point, segments, threshold
                    )

                else:
                    segment_groups = [[]]
                    group_index = 0
                    segment_index = segments[0].sequence - 1
                    for segment in segments:
                        if segment.sequence == segment_index + 1:
                            segment_groups[group_index].append(segment)
                            segment_index = segment.sequence
                        else:
                            segment_groups.append([segment])
                            segment_index = segment.sequence
                            group_index += 1

                    distance = math.inf
                    for segment_group in segment_groups:
                        if len(segment_group) == 1:
                            distance_aux, projection_aux = segments[
                                0
                            ].on_route_distances(point)
                        else:
                            distance_aux, projection_aux = (
                                self.__get_distances_from_segments(
                                    point, segment_group, threshold
                                )
                            )
                        if distance_aux is not None and distance_aux < distance:
                            distance = distance_aux
                            projection = projection_aux
            elif len(segments) == 1:
                distance, projection = segments[0].on_route_distances(point)
            else:
                raise ValueError("GPS Pulse has no associate cells.")
        else:
            distance, projection = self.__get_distances_from_segments(
                point, segments, threshold, previous_distance
            )
        if distance is None or projection is None:
            raise ValueError(
                f"It could not calculate projection from point {point} to shape_id {shape_id}"
            )
        return distance, projection

    @staticmethod
    def __get_distances_from_segments(
        point: Point,
        segments: List[PolylineSegment],
        distance_threshold,
        previous_distance=None,
    ) -> Optional[Tuple[float, float]]:
        closest_distance = math.inf
        closest_on_route_distance = math.inf

        for segment in segments:
            aux_dist, aux_proj = segment.on_route_distances(point)
            if (
                previous_distance is not None and previous_distance <= aux_proj
            ) or previous_distance is None:
                if aux_dist < closest_distance:
                    closest_distance = aux_dist
                    closest_on_route_distance = aux_proj
        if closest_distance <= distance_threshold:
            return closest_distance, closest_on_route_distance
        else:
            return None, None

    @staticmethod
    def _determine_shape_pk_from_matched_segments(
        expedition,
        vehicle_data,
        matched_segments: List[Optional[int]],
        valid_indices: List[int],
        projected_points: List[Optional[shp_Point]],
        segments_gdf: gpd.GeoDataFrame,
    ) -> Optional[
        Dict[str, Tuple[List[Optional[int]], List[int], List[Optional[shp_Point]]]]
    ]:
        """
        Determina el shape_pk de los segmentos matcheados. Si hay más de un shape_pk,
        crea una expedición por cada shape_pk.

        Parameters
        ----------
        matched_segments : List[Optional[int]]
            Lista de segment PKs de longitud igual al número de GPS points.
        valid_indices : List[int]
            Índices ORIGINALES de GPS points que tienen match.
        segments_gdf : gpd.GeoDataFrame
            GeoDataFrame con información de segmentos.

        Returns
        -------
        int or None
            Diccionario con expediciones como llaves y tuplas (expedición, segmentos_matcheados, puntos_proyectados) como valores.
        """
        shape_pks = dict()
        for idx in valid_indices:
            seg_pk = matched_segments[idx]
            if seg_pk is not None:
                row = segments_gdf[segments_gdf.segment_pk == seg_pk]
                if not row.empty:
                    shape_pk = row.iloc[0]["shape_pk"]
                    if shape_pk not in shape_pks:
                        shape_pks[shape_pk] = ([], [])
                    shape_pks[shape_pk][0].append(idx)
                    shape_pks[shape_pk][1].append(seg_pk)

        if not shape_pks:
            return None

        if len(shape_pks) == 1:
            expedition.shape_id = next(iter(shape_pks))
            return {
                expedition: (
                    expedition,
                    valid_indices,
                    matched_segments,
                    projected_points,
                )
            }
        vehicle_data.expeditions.pop(expedition)
        new_set = {}
        for shape_pk, (idxs, seg_pks) in shape_pks.items():
            expedition_copy = ExpeditionData(
                grid_manager=expedition.grid_manager,
                route_id=expedition.route_id,
                timestamp=expedition.timestamp,
                license_plate=expedition.license_plate,
            )
            expedition_copy.shape_id = shape_pk
            expedition_copy.gps_points = expedition.gps_points
            matched_segments_copy = [None] * len(matched_segments)
            projected_points_copy = [None] * len(projected_points)
            for idx in idxs:  # idxs contiene solo los índices de este shape_pk
                matched_segments_copy[idx] = matched_segments[idx]
                projected_points_copy[idx] = projected_points[idx]
            vehicle_data.expeditions[expedition_copy] = expedition_copy
            new_set[expedition_copy] = (
                expedition_copy,
                idxs,
                matched_segments_copy,
                projected_points_copy,
            )

        return new_set

    @staticmethod
    def _calculate_cumulative_distance(
        segment_pk: int, projected_point: shp_Point, segments_gdf: gpd.GeoDataFrame
    ) -> Optional[float]:
        """
        Calcula la distancia acumulada desde el inicio de la ruta hasta el punto proyectado.

        Parameters
        ----------
        segment_pk : int
            PK del segmento.
        projected_point : shp_Point
            Punto proyectado en el segmento.
        segments_gdf : gpd.GeoDataFrame
            GeoDataFrame con información de segmentos.

        Returns
        -------
        float or None
            Distancia acumulada o None si no se encuentra el segmento.
        """
        segment_row = segments_gdf[segments_gdf.segment_pk == segment_pk]
        if segment_row.empty:
            return None

        segment_row = segment_row.iloc[0]
        distance_to_segment_start = segment_row.get("distance_start", 0)
        segment_geom = segment_row.geometry
        coords = list(segment_geom.coords)
        distance_along_segment = 0

        for i in range(len(coords) - 1):
            lon1, lat1 = coords[i]
            lon2, lat2 = coords[i + 1]
            point_on_segment = shp_Point(lon1, lat1)

            # Si el punto proyectado está entre coord[i] y coord[i+1]
            # calculamos la distancia hasta ese punto
            if (
                segment_geom.project(shp_Point(lon1, lat1))
                <= segment_geom.project(projected_point)
                <= segment_geom.project(shp_Point(lon2, lat2))
            ):
                # Distancia acumulada hasta coord[i]
                distance_along_segment += haversine_distance(
                    lat1, lon1, projected_point.y, projected_point.x
                )
                break
            else:
                # Sumar distancia completa del sub-segmento
                distance_along_segment += haversine_distance(lat1, lon1, lat2, lon2)

        return distance_to_segment_start + distance_along_segment

    def _update_expedition_from_hmm_results(
        self,
        expedition,
        matched_segments: List[Optional[int]],
        valid_indices: List[int],
        projected_points: List[Optional[shp_Point]],
        segments_gdf: gpd.GeoDataFrame,
    ):
        """
        Parameters
        ----------
        expedition : ExpeditionData
            Expedición a actualizar.
        matched_segments : List[Optional[int]]
            Lista de segment PKs de longitud igual a len(expedition.gps_points).
        valid_indices : List[int]
            Lista de índices ORIGINALES de GPS que tienen match.
        projected_points : List[Optional[shp_Point]]
            Lista de puntos proyectados del HMM (no utilizados - se recalculan con grilla).
        segments_gdf : gpd.GeoDataFrame
            GeoDataFrame con información de segmentos.
        """
        # Obtener shape_id de la expedición
        if expedition.shape_id is None:
            print("WARNING: expedition.shape_id is None, cannot calculate distances")
            return

        # Inicializar listas si están vacías
        if not expedition.gps_distance_on_route:
            expedition.gps_distance_on_route = [None] * len(expedition.gps_points)
        if not expedition.gps_distance_to_route:
            expedition.gps_distance_to_route = [None] * len(expedition.gps_points)

        # Llenar con proyecciones del HMM
        for idx in valid_indices:
            segment_pk = matched_segments[idx]
            projected_point = projected_points[idx]

            if segment_pk is not None and projected_point is not None:
                try:
                    # Calcular distancia acumulada en la ruta
                    distance_on_route = self._calculate_cumulative_distance(
                        segment_pk, projected_point, segments_gdf
                    )
                    if distance_on_route is not None:
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
                except Exception as e:
                    print(f"Error processing GPS point {idx}: {e}")
                    continue

    def run_hmm_map_matching(
        self,
        vm: VehicleManager,
        max_distance: int = 40,
        sigma: float = 25,
        beta: float = 40,
        min_candidates: int = 2,
        sigma_bearing: float = 40,
        bearing_weight_factor: float = 0.5,
    ):
        segments_gdfs: Dict[str, gpd.GeoDataFrame] = (
            self.shape_manager.get_segments_gdf()
        )

        # Add cumulative distance column to each segments_gdf
        for axis_id, gdf in segments_gdfs.items():
            if not gdf.empty and "distance_start" not in gdf.columns:
                # Group by shape_id and calculate cumulative distance
                gdf_with_distance = []
                for shape_id in gdf["shape_id"].unique():
                    shape_segments = gdf[gdf["shape_id"] == shape_id].copy()
                    shape_segments = shape_segments.sort_values("sequence")

                    # Calculate cumulative distance using actual segment distances
                    cumulative_dist = 0
                    distances_start = []
                    for idx, row in shape_segments.iterrows():
                        distances_start.append(cumulative_dist)
                        # Calculate actual distance for this segment using haversine
                        coords = list(row.geometry.coords)
                        segment_distance = 0
                        for i in range(len(coords) - 1):
                            lon1, lat1 = coords[i]
                            lon2, lat2 = coords[i + 1]
                            from rest_api.util.hmm.hmm import haversine_distance

                            segment_distance += haversine_distance(
                                lat1, lon1, lat2, lon2
                            )
                        cumulative_dist += segment_distance

                    shape_segments["distance_start"] = distances_start
                    gdf_with_distance.append(shape_segments)

                if gdf_with_distance:
                    segments_gdfs[axis_id] = pd.concat(
                        gdf_with_distance, ignore_index=True
                    )

        # Precalculate shapes caches
        self.shape_manager.shapes_cache(segments_gdfs=segments_gdfs)

        vehicle_data_values = list(vm.vehicles.values())
        segments_cnt = set()
        for vehicle_data in vehicle_data_values:
            expeditions = list(vehicle_data.expeditions.values())
            for expedition in expeditions:
                trajectory = [
                    shp_Point(gps_point.longitude, gps_point.latitude)
                    for gps_point in expedition.gps_points
                ]
                bearings = [gps_point.bearing for gps_point in expedition.gps_points]
                excluded_indices = set()
                per_traj_results: Dict[
                    str,
                    Tuple[List[Optional[int]], List[int], List[Optional[shp_Point]]],
                ] = {}
                for axis_id in segments_gdfs.keys():
                    matched_segments, valid_indices, projected_points = viterbi(
                        trajectory,
                        self.shape_manager.direction_caches[axis_id],
                        self.shape_manager.spatial_indices[axis_id],
                        self.shape_manager.segment_caches[axis_id],
                        max_distance=max_distance,
                        sigma=sigma,
                        beta=beta,
                        min_candidates=min_candidates,
                        excluded_indices=excluded_indices,
                        gps_bearings=bearings,
                        sigma_bearing=sigma_bearing,
                        bearing_weight_factor=bearing_weight_factor,
                    )
                    segments_cnt.update(
                        matched_seg
                        for matched_seg in matched_segments
                        if matched_seg is not None
                    )
                    if valid_indices:
                        # Actualizar la expedición directamente con los resultados
                        try:
                            new_set = self._determine_shape_pk_from_matched_segments(
                                expedition,
                                vehicle_data,
                                matched_segments,
                                valid_indices,
                                projected_points,
                                segments_gdfs[axis_id],
                            )
                            if new_set is None:
                                continue
                            for (
                                expedition,
                                valid_id,
                                matched_seg,
                                proj_points,
                            ) in new_set.values():
                                self._update_expedition_from_hmm_results(
                                    expedition,
                                    matched_seg,
                                    valid_id,
                                    proj_points,
                                    segments_gdfs[axis_id],
                                )
                                # Solo excluir índices si la actualización fue exitosa
                                excluded_indices.update(valid_id)
                            # Continuar procesando otros ejes para permitir matches en múltiples ejes
                        except Exception as e:
                            print(
                                f"Error processing {expedition} for axis {axis_id}: {e}"
                            )
                            tb = traceback.format_exc()
                            print(tb)
                            continue

        # Estadísticas de matching por shape_id
        shape_stats = {}
        for vehicle_data in vehicle_data_values:
            for expedition in vehicle_data.expeditions.values():
                if expedition.shape_id is not None:
                    shape_stats[expedition.shape_id] = (
                        shape_stats.get(expedition.shape_id, 0) + 1
                    )

        print(
            f"HMM map matching completed. Processed expeditions from {len(vm.vehicles)} vehicles."
        )
        print(f"Unique matched segments: {len(segments_cnt)}")
        print(f"Expeditions per shape_id:")
        for shape_id, count in sorted(
            shape_stats.items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  - {shape_id}: {count} expeditions")
