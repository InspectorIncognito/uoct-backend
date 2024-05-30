from velocity.grid import GridManager
from velocity.gps import GPSPulse as GPS
from gtfs_rt.models import GPSPulse
from velocity.expedition import ExpeditionData
from rest_api.util.services import get_all_services, get_shape_by_route_id
from velocity.segment import SegmentCriteria
from gtfs_rt.config import TIMEZONE


class VehicleData:
    def __init__(self, grid_manager: GridManager, license_plate: str):
        self.grid_manager = grid_manager
        self.expeditions = dict()
        self.license_plate = license_plate

    def add_gps_pulse(self, gps_point: GPS, shape_id: str, route_id: str, license_plate: str):
        new_exp = ExpeditionData(self.grid_manager, shape_id, route_id, timestamp=gps_point.timestamp,
                                 license_plate=license_plate)
        if new_exp not in self.expeditions:
            self.expeditions[new_exp] = new_exp
        self.expeditions[new_exp].add_gps_point(gps_point)

    def __eq__(self, other):
        return self.license_plate == other.license_plate

    def __hash__(self):
        return hash(self.license_plate)

    def __str__(self):
        return f"Vehicle {self.license_plate}"


class VehicleManager:
    def __init__(self, grid_manager: GridManager):
        self.vehicles = dict()
        self.grid_manager = grid_manager
        self.services = get_all_services()

        self.gps_ignored = 0

    def add_data(self, gps_pulse: GPSPulse):
        license_plate = gps_pulse.license_plate
        vehicle_data = VehicleData(self.grid_manager, license_plate=license_plate)
        if vehicle_data not in self.vehicles:
            self.vehicles[vehicle_data] = vehicle_data

        try:
            route_id = str(gps_pulse.route_id) + ("I" if gps_pulse.direction_id == 0 else "R")
            shape_id = get_shape_by_route_id(self.services, route_id)
            if shape_id is None:
                self.gps_ignored += 1
                raise ValueError(f"Skipping GPS pulse for route {route_id}.")
            gps_obj = GPS(latitude=gps_pulse.latitude, longitude=gps_pulse.longitude,
                          timestamp=gps_pulse.timestamp.astimezone(TIMEZONE))
            self.vehicles[vehicle_data].add_gps_pulse(gps_obj, shape_id, route_id, license_plate)
        except ValueError as e:
            pass
            # print(e)

    def calculate_speed(self, segment_criteria: SegmentCriteria):
        records = []
        expeditions_ignored = []
        total_expeditions = 0
        for vehicle in self.vehicles:
            # print(f"Processing vehicle {vehicle}...")
            total_expeditions += len(self.vehicles[vehicle].expeditions)
            for expedition in self.vehicles[vehicle].expeditions:
                try:
                    exp_records = expedition.calculate_speed(segment_criteria)
                    records.extend(exp_records)
                except ValueError as e:
                    expeditions_ignored.append(str(expedition))
                    # print(e)
        print("Total expeditions:", total_expeditions)
        print("Expeditions ignored:", len(expeditions_ignored))
        return records
