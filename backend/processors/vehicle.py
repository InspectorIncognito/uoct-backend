import logging

from processors.grid import GridManager
from processors.gps import GPSPulse
from processors.expedition import ExpeditionData

logger = logging.getLogger(__name__)


class VehicleData:
    def __init__(self, license_plate: str, grid_manager: GridManager):
        self.license_plate = license_plate
        self.grid_manager = grid_manager
        self.expeditions = dict()

    def add_gps_pulse(self, gps_point: GPSPulse, license_plate: str, shape_id: str, trip_id: str, route_id: str | None,
                      direction_id: str | None, start_date: str | None, start_time: str | None):
        new_expedition = ExpeditionData(self.grid_manager, license_plate, shape_id, trip_id, route_id, direction_id,
                                        start_date, start_time)
        if new_expedition not in self.expeditions:
            self.expeditions[new_expedition] = new_expedition
        self.expeditions[new_expedition].add_gps_point(gps_point)

    def __eq__(self, other):
        return self.license_plate == other.license_plate

    def __hash__(self):
        return hash(self.license_plate)

    def __str__(self):
        return f'Vehicle ${self.license_plate}'


class VehicleManager:
    def __init__(self, grid_manager: GridManager, gtfs_manager: GTFSManager):
        self.vehicles = {}
        self.grid_manager = grid_manager
        self.gtfs_manager = gtfs_manager

        self.gtfs_timezone = self.gtfs_manager.get_timezone()
        self.trip_dict = self.gtfs_manager.get_trip_dict()

    # TODO: Ahora los datos no dependen del trip_id. Sólamente dependen de si se encuentran en cierta ruta
    # (ahora route_id es el identificador)
    def add_data(self, license_plate: str, gps_pulse: GPSPulse, trip_id: str, route_id: str | None,
                 direction_id: str | None, start_date: str | None, start_time: str | None):
        vehicle_data = VehicleData(license_plate, self.grid_manager)
        if vehicle_data not in self.vehicles:
            self.vehicles[vehicle_data] = vehicle_data

        try:
            shape_id = self.trip_dict[trip_id]['shape_id']
            self.vehicles[vehicle_data].add_gps_pulse(gps_pulse, license_plate, shape_id, trip_id, route_id,
                                                      direction_id, start_date, start_time)
        except KeyError:
            logger.error(f'trip_id "{trip_id}" does not exist in gtfs')

    def calculate_speed(self, segment_criteria: SegmentCriteria):
        records = []
        for vehicle in self.vehicles:
            logger.info(f"processing vehicle {vehicle}...")
            for expedition in self.vehicles[vehicle].expeditions:
                try:
                    logger.info(f'\tprocessing expedition {expedition}...')
                    exp_records = expedition.calculate_speed(segment_criteria, self.gtfs_timezone)
                    records.extend(exp_records)
                except ValueError as e:
                    logger.error(f'vehicle: {e}')
        return records
