from typing import Dict, Tuple, List
import logging
import math
from processors.geometry.point import Point
from processors.geometry.line import PolylineSegment

logger = logging.getLogger(__name__)
DISTANCE_THRESHOLD = 25  # meters


class GridCell:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.stops = []
        self.route_segments = {}


class GridManager(Dict[Tuple[int, int], GridCell]):
    def __init__(self, stops: list, shapes_dict: dict):
        super().__init__()
        self.shapes_dict = shapes_dict
        self.expected_cell_size_in_meters = 500
        self.grid_latitude_distance = 0
        self.grid_longitude_distance = 0
        self.grid_min_latitude = 0
        self.grid_min_longitude = 0
        self.latitude_cells_number = 0
        self.longitude_cells_number = 0

        self.grid = None

    def process(self, shapes_dict):
        grid = self.__create_grid()

    def __create_grid(self):
        grid_min_lat = 90
        grid_max_lat = -90
        grid_min_lon = 180
        grid_max_lon = -180

    @staticmethod
    def __get_distances_from_segments(point: Point, segments: List[PolylineSegment], distance_threshold,
                                      previous_distance=None, ) -> Tuple[float, float] or None:
        closest_distance = math.inf
        closest_on_route_distance = math.inf
        for segment in segments:
            aux_dist, aux_proj = segment.on_route_distances(point)

            if (previous_distance is not None and previous_distance <= aux_proj) or previous_distance is None:
                if aux_dist < closest_distance:
                    closest_distance = aux_dist
                    closest_on_route_distance = aux_proj
        if closest_distance <= distance_threshold:
            return closest_distance, closest_on_route_distance
        return None, None

    def get_indexes_from_point(self, lat: float, lon: float) -> Tuple[int, int]:
        lat_index = int((lat - self.grid_min_latitude) / self.grid_latitude_distance)
        lon_index = int((lon - self.grid_min_longitude) / self.grid_longitude_distance)
        return lat_index, lon_index

    def get_on_route_distances(self, point: Point, shape_id: str, previous_distance=None,
                               threshold=DISTANCE_THRESHOLD) -> Tuple[float, float] or None:
        segments = set()

        lat_index, lon_index = self.get_indexes_from_point(point.latitude, point.longitude)
        for i in range(lat_index - 1, lat_index + 2):
            for j in range(lon_index - 1, lon_index + 2):
                cell_data: GridCell = self.grid.get((i, j))

                if cell_data is None or shape_id not in cell_data.route_segments:
                    continue
                segments.update(cell_data.route_segments[shape_id])

        segments = list(segments)
        segments = sorted(segments, key=lambda x: x.sequence)

        logger.debug(list(map(lambda x: str(x), segments)))

        projection = None
        distance = None

        if previous_distance is None:
            if len(segments) > 1:
                max_index = max(segments, key=lambda x: x.sequence).sequence
                min_index = min(segments, key=lambda x: x.sequence).sequence

                if max_index - min_index + 1 == len(segments):
                    distance, projection = self.__get_distances_from_segments(point, segments, threshold)
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
                            distance_aux, projection_aux = segments[0].on_route_distances(point)
                        else:
                            distance_aux, projection_aux = self.__get_distances_from_segments(point, segment_group,
                                                                                              threshold)
                        if distance_aux is not None and distance_aux < distance:
                            distance = distance_aux
                            projection = projection_aux
            elif len(segments) == 1:
                distance, projection = segments[0].on_route_distances(point)
        else:
            distance, projection = self.__get_distances_from_segments(point, segments, threshold, previous_distance)
        return distance, projection


def generate_grid() -> GridManager:
    logger.info("Generating grid object...")
    grid_obj = GridManager()
    grid_obj.process()
    return grid_obj
