from typing import Dict, Tuple

from processors.models.shapes import Shape
from rest_api.util.shape import ShapeManager
from processors.geometry.point import Point
from typing import List
from rest_api.models import Segment


class GridCell:
    def __init__(self, i: int, j: int):
        self.i: i
        self.j = j

        self.route_segments = dict()


class GridManager(Dict[Tuple[int, int], GridCell]):
    def __init__(self):
        super().__init__()
        self.shapes = ShapeManager()
        self.expected_cell_size_in_meters = 500

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

    def __create_grid(self):
        bbox = self.shapes.get_bbox()

        grid_min_lon = bbox[0] - 0.001
        grid_min_lat = bbox[1] - 0.001
        grid_max_lon = bbox[2] + 0.001
        grid_max_lat = bbox[3] + 0.001

        lon_dist = Point(grid_min_lat, grid_min_lon).distance(Point(grid_min_lat, grid_max_lon))
        lat_dist = Point(grid_min_lat, grid_min_lon).distance(Point(grid_max_lat, grid_min_lon))

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
        segments: List[Segment] = self.shapes.get_segments()
        for segment in segments:
            points = segment.geometry
            pass

