from velocity.grid import GridManager
from velocity.gps import GPSPulse as GPS
from gtfs_rt.models import GPSPulse
from velocity.expedition import ExpeditionData
from rest_api.util.services import get_all_services, get_shape_by_route_id
from velocity.segment import SegmentCriteria


# TODO: Add vehicle license plate if necessary
class VehicleData:
    def __init__(self, grid_manager: GridManager, service: str):
        self.grid_manager = grid_manager
        self.expeditions = dict()
        self.service = service

    def add_gps_pulse(self, gps_point: GPS, shape_id: str, route_id: str or None):
        new_exp = ExpeditionData(self.grid_manager, shape_id, route_id, timestamp=gps_point.timestamp)
        if new_exp not in self.expeditions:
            self.expeditions[new_exp] = new_exp
        self.expeditions[new_exp].add_gps_point(gps_point)

    def __eq__(self, other):
        return self.service == other.service

    def __hash__(self):
        return hash(self.service)

    def __str__(self):
        return f"Vehicle {self.service}"


class VehicleManager:
    def __init__(self, grid_manager: GridManager):
        self.vehicles = dict()
        self.grid_manager = grid_manager
        self.services = get_all_services()

    def add_data(self, gps_pulse: GPSPulse):
        vehicle_data = VehicleData(self.grid_manager, gps_pulse.route_id)
        if vehicle_data not in self.vehicles:
            self.vehicles[vehicle_data] = vehicle_data

        try:
            route_id = str(gps_pulse.route_id) + ("I" if gps_pulse.direction_id == 0 else "R")
            shape_id = str(get_shape_by_route_id(self.services, route_id))
            if shape_id is None:
                raise ValueError(f"Skipping GPS pulse for route {shape_id}.")
            gps_obj = GPS(latitude=gps_pulse.latitude, longitude=gps_pulse.longitude, timestamp=gps_pulse.timestamp)
            self.vehicles[vehicle_data].add_gps_pulse(gps_obj, shape_id, route_id)
        except ValueError as e:
            print(e)

    def calculate_speed(self, segment_criteria: SegmentCriteria):
        records = []
        for vehicle in self.vehicles:
            print(f"Processing vehicle {vehicle}...")
            for expedition in self.vehicles[vehicle].expeditions:
                try:
                    print(f"Processing expedition {expedition}...")
                    exp_records = expedition.calculate_speed(segment_criteria)
                    records.extend(exp_records)
                except ValueError as e:
                    print(e)
