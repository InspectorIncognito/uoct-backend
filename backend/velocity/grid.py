import math
from typing import Dict, Tuple

from rest_api.util.shape import ShapeManager
from processors.geometry.point import Point
from typing import List
from rest_api.models import Segment
from shapely.geometry import LineString as shp_LineString
from haversine import haversine, Unit
from processors.geometry.line import PolylineSegment

DISTANCE_THRESHOLD = 25  # meters


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

    def process(self):
        grid = self.__create_grid()
        grid = self.__process_routes(grid)
        self.grid = grid

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

        grid_min_lon = bbox[0] - 0.001
        grid_min_lat = bbox[1] - 0.001
        grid_max_lon = bbox[2] + 0.001
        grid_max_lat = bbox[3] + 0.001

        lat_dist = Point(grid_min_lat, grid_min_lon).distance(Point(grid_max_lat, grid_min_lon), algorithm='haversine')
        lon_dist = Point(grid_min_lat, grid_min_lon).distance(Point(grid_min_lat, grid_max_lon), algorithm='haversine')

        self.latitude_cells_number = round(lat_dist / self.expected_cell_size_in_meters)
        self.longitude_cells_number = round(lon_dist / self.expected_cell_size_in_meters)

        delta_lat = grid_max_lat - grid_min_lat
        delta_lon = grid_max_lon - grid_min_lon

        # Calculate the distance between latitude and longitude cells
        self.grid_latitude_distance = delta_lat / self.latitude_cells_number
        self.grid_longitude_distance = delta_lon / self.longitude_cells_number

        # Store grid parameters
        self.grid_min_latitude = grid_min_lat
        self.grid_min_longitude = grid_min_lon

        # Return an empty dictionary
        return {}

    def __process_routes(self, grid: Dict[Tuple[int, int], GridCell]) -> Dict[Tuple[int, int], GridCell]:
        segments: Dict[int, List[Segment]] = self.shape_manager.get_segments()
        for shape_id, segments in segments.items():
            prev_tuple = None
            current_distance = 0
            current_sequence = 1
            for segment in segments:
                coords: List[List[float]] = segment.geometry
                for coord in coords:
                    if prev_tuple is None:
                        prev_tuple = coord
                        continue
                    p1 = Point(prev_tuple[0], prev_tuple[1])
                    p2 = Point(coord[0], coord[1])

                    segment_obj = PolylineSegment(p1, p2, current_distance, current_sequence)

                    if segment_obj.length == 0:  # Skip segments with zero length
                        prev_tuple = coord
                        continue

                    current_distance += segment_obj.length
                    current_sequence += 1

                    affected_cells = self.__process_segment(p1, p2)

                    for cell in affected_cells:
                        cell_data = grid.get((cell[0], cell[1])) or GridCell(cell[0], cell[1])
                        segment_array = cell_data.route_segments.get(shape_id) or []
                        segment_array.append(segment_obj)
                        cell_data.route_segments[shape_id] = segment_array

                        grid[cell[0], cell[1]] = cell_data
                    prev_tuple = coord
        return grid

    def get_cell_indexes_from_point(self, lat: float, lon: float) -> Tuple[int, int]:
        lat_index = int((lat - self.grid_min_latitude) / self.grid_latitude_distance)
        lon_index = int((lon - self.grid_min_longitude) / self.grid_longitude_distance)

        return lat_index, lon_index

    def __process_segment(self, p1: Point, p2: Point) -> List[Tuple[int, int]]:
        current_segment = shp_LineString(coordinates=[p1.coordinates, p2.coordinates])
        p1_cell = self.get_cell_indexes_from_point(p1.y, p1.x)
        p2_cell = self.get_cell_indexes_from_point(p2.y, p2.x)

        affected_cells = []

        if p1_cell[0] == p2_cell[0] and p1_cell[1] == p2_cell[1]:
            affected_cells.append(p1_cell)

        elif p1_cell[0] == p2_cell[0]:
            for j in range(min(p1_cell[1], p2_cell[1]), max(p1_cell[1], p2_cell[1]) + 1):
                affected_cells.append((p1_cell[0], j))

        elif p1_cell[1] == p2_cell[1]:
            for i in range(min(p1_cell[0], p2_cell[0]), max(p1_cell[0], p2_cell[0]) + 1):
                affected_cells.append((i, p1_cell[1]))

        else:
            pa = Point(min(p1.y, p2.y), min(p1.x, p2.x))
            pb = Point(max(p1.y, p2.y), max(p1.x, p2.x))

            pa_indexes = self.get_cell_indexes_from_point(pa.y, pa.x)
            pb_indexes = self.get_cell_indexes_from_point(pb.y, pb.x)

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
            self.grid_min_longitude + (self.grid_longitude_distance * j)
        )

        v2 = (
            self.grid_min_latitude + (self.grid_latitude_distance * (i + 1)),
            self.grid_min_longitude + (self.grid_longitude_distance * j)
        )

        v3 = (
            self.grid_min_latitude + (self.grid_latitude_distance * (i + 1)),
            self.grid_min_longitude + (self.grid_longitude_distance * (j + 1))
        )

        v4 = (
            self.grid_min_latitude + (self.grid_latitude_distance * i),
            self.grid_min_longitude + (self.grid_longitude_distance * (j + 1))
        )

        segments = [
            shp_LineString(coordinates=[v1, v2]),
            shp_LineString(coordinates=[v2, v3]),
            shp_LineString(coordinates=[v3, v4]),
            shp_LineString(coordinates=[v4, v1])
        ]
        return segments

    def get_on_route_distances(self, point: Point, shape_id: int, previous_distance=None,
                               threshold=DISTANCE_THRESHOLD) -> Tuple[float, float] or None:
        segments = set()
        lat_index, lon_index = self.get_cell_indexes_from_point(point.y, point.x)

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

    def __get_distances_from_segments(self, point: Point, segments: List[shp_LineString], distance_threshold,
                                      previous_distance=None) -> Tuple[float, float] or None:
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
        else:
            return None, None
