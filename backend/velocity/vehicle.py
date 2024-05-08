from velocity.grid import GridManager
from velocity.gps import GPSPulse
from velocity.expedition import ExpeditionData


class VehicleData:
    def __init__(self, license_plate: str, grid_manager: GridManager):
        self.license_plate = license_plate
        self.grid_manager = grid_manager
        self.expeditions = dict()

    def add_gps_pulse(self, gps_point: GPSPulse, license_plate: str, shape_id: str, route_id: str | None,
                      start_date: str | None, start_time: str | None):
        new_exp = ExpeditionData(self.grid_manager, license_plate, shape_id, route_id,
                                 start_date, start_time)
        if new_exp not in self.expeditions:
            self.expeditions[new_exp] = new_exp
        self.expeditions[new_exp].add_gps_point(gps_point)


class VehicleManager:
    def __init__(self, grid_manager: GridManager):
        self.vehicles = dict()
        self.grid_manager = grid_manager

    def add_data(self, license_plate: str, gps_pulse: GPSPulse, route_id: str | None, start_date: str | None, start_time: str | None):
        vehicle_data = VehicleData(license_plate, self.grid_manager)
        if vehicle_data not in self.vehicles:
            self.vehicles[vehicle_data] = vehicle_data


