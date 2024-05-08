from velocity.grid import GridManager
from velocity.gps import GPSPulse


class ExpeditionData:
    MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES = 60 * 10  # in seconds

    def __init__(self, grid_manager: GridManager, license_plate: str, shape_id: int, sequence_number: int,
                 start_date: str | None, start_time: str | None):
        self.grid_manager = grid_manager
        self.license_plate = license_plate
        self.shape_id = shape_id
        self.sequence_number = sequence_number
        self.start_date = start_date
        self.start_time = start_time

        self.gps_points = []
        self.gps_distance_to_route = []
        self.gps_distance_on_route = []
        self.gps_distance_on_route_dict = dict()

        self.ignored_gps_pulses = 0
        self.ignored_segments_because_time_between_gps_pulses = 0

    def add_gps_point(self, gps_pulse: GPSPulse):
        if len(self.gps_points) == 0:
            dist_to_route, dist_on_route = self.grid_manager.get_on_route_distances(gps_pulse, self.shape_id)
            if dist_to_route is None or dist_on_route is None:
                print(f"It could not calculate projection from point {gps_pulse} \
                to shape_id {self.shape_id}: ({dist_to_route}, {dist_on_route})")
            else:
                self.gps_distance_to_route.append(dist_to_route)
                self.gps_distance_on_route.append(dist_on_route)
                self.gps_distance_on_route_dict[gps_pulse] = dist_on_route
                self.gps_points.append(gps_pulse)
        elif gps_pulse.timestamp > self.gps_points[-1].timestamp:
            previous_distance = self.gps_distance_on_route[-1]
            dist_to_route, dist_on_route = self.grid_manager.get_on_route_distances(gps_pulse, self.shape_id,
                                                                                    previous_distance)
            if dist_to_route is None or dist_on_route is None:
                print(f"it could not calculate projection from point {gps_pulse} to shape_id {self.shape_id}")
            else:
                self.gps_distance_to_route.append(dist_to_route)
                self.gps_distance_on_route.append(dist_on_route)
                self.gps_distance_on_route_dict[gps_pulse] = dist_on_route
                self.gps_points.append(gps_pulse)
        elif gps_pulse.timestamp == self.gps_points[-1].timestamp:
            print(f'gps point {gps_pulse} is equal to previous gps point {gps_pulse}.')
            self.ignored_gps_pulses += 1
        elif gps_pulse.timestamp < self.gps_points[-1].timestamp:
            print(f'gps point {gps_pulse} is older than latest gps point {gps_pulse}.')
            self.ignored_gps_pulses += 1
