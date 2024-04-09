from typing import Dict, Tuple
from processors.data import ProtoFileProcessor
import logging

logger = logging.getLogger(__name__)


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




def generate_grid() -> GridManager:
    logger.info("Generating grid object...")
    grid_obj = GridManager()
    grid_obj.process()
    return grid_obj
