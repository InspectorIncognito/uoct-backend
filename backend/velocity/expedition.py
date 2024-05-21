from velocity.grid import GridManager
from velocity.gps import GPSPulse as GPS
from datetime import datetime
from velocity.segment import SegmentCriteria, PartialSpatialSegment, PartialTemporalSegment, TemporalSegment, \
    SpatialSegment
import pytz


# TODO: Add vehicle license plate if necessary
class ExpeditionData:
    MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES = 60 * 10  # in seconds

    def __init__(self, grid_manager: GridManager, shape_id: str, route_id: str, timestamp: datetime):
        self.grid_manager = grid_manager
        self.shape_id = shape_id
        self.route_id = route_id
        self.timestamp = timestamp
        self.gps_points = []
        self.gps_distance_to_route = []
        self.gps_distance_on_route = []
        self.gps_distance_on_route_dict = dict()

        self.ignored_gps_pulses = 0
        self.ignored_segments_because_time_between_gps_pulses = 0

    def add_gps_point(self, gps_pulse: GPS):
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

    def calculate_speed(self, segment_criteria: SegmentCriteria,
                        local_timezone: datetime.tzinfo = pytz.timezone('America/Santiago')):
        speed_data = []
        if len(self.gps_points) < 2:
            raise ValueError(f"{self} has {len(self.gps_points)} gps points.")
        for index, gps_pulse in enumerate(self.gps_points[1:], start=1):
            previous_gps_pulse = self.gps_points[index - 1]
            previous_distance = self.gps_distance_on_route[index - 1]
            current_distance = self.gps_distance_on_route[index]

            # calculate distance and time difference
            delta_time = (gps_pulse.timestamp - previous_gps_pulse.timestamp).total_seconds()
            delta_distance = current_distance - previous_distance

            if delta_time >= self.MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES:
                print(
                    f"time window between {previous_gps_pulse.timestamp} and {gps_pulse.timestamp} is greater than {self.MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES} seconds")
                self.ignored_segments_because_time_between_gps_pulses += 1
                continue

            current_temporal_segment_obj = segment_criteria.get_temporal_segment(gps_pulse.timestamp)
            previous_temporal_segment_obj = segment_criteria.get_temporal_segment(previous_gps_pulse.timestamp)

            current_spatial_segment_obj = segment_criteria.get_spatial_segment(self.shape_id, current_distance)
            previous_spatial_segment_obj = segment_criteria.get_spatial_segment(self.shape_id, previous_distance)

            if current_temporal_segment_obj == previous_temporal_segment_obj and \
                    current_spatial_segment_obj == previous_spatial_segment_obj:
                current_day_type_id = segment_criteria.get_day_type(gps_pulse.timestamp)
                date_obj = gps_pulse.timestamp.date()

                speed_row = self.__format_speed_data_row(date_obj, current_day_type_id,
                                                         current_temporal_segment_obj,
                                                         current_spatial_segment_obj, delta_time, delta_distance,
                                                         local_timezone, segment_criteria)
                speed_data.append(speed_row)
            else:
                # Calculate speed difference for interpolation between periods
                delta_speed = delta_distance / delta_time
                range_of_temporal_segments = segment_criteria.get_range_of_temporal_segments(
                    previous_gps_pulse.timestamp, gps_pulse.timestamp)

                aux_start_distance = previous_distance
                for temporal_segment_obj in range_of_temporal_segments:
                    aux_day_type_id = segment_criteria.get_day_type(temporal_segment_obj.start_time)
                    aux_date_obj = temporal_segment_obj.start_time.date()

                    ts_obj = temporal_segment_obj
                    if isinstance(temporal_segment_obj, PartialTemporalSegment):
                        ts_obj = temporal_segment_obj.complete_temporal_segment

                    # Calculate interpolated time and distance
                    i_delta_time = (temporal_segment_obj.end_time - temporal_segment_obj.start_time).total_seconds()
                    i_delta_dist = delta_speed * i_delta_time
                    range_of_spatial_segments = segment_criteria.get_range_of_spatial_segments(
                        self.shape_id, aux_start_distance, aux_start_distance + i_delta_dist)
                    for spatial_segment_obj in range_of_spatial_segments:
                        # calculate interpolated time and distance
                        ss_obj = spatial_segment_obj
                        if isinstance(spatial_segment_obj, PartialSpatialSegment):
                            ss_obj = spatial_segment_obj.complete_spatial_segment

                        aux_delta_dist = spatial_segment_obj.end_distance - spatial_segment_obj.start_distance
                        if delta_speed != 0:
                            aux_delta_time = aux_delta_dist / delta_speed
                        else:
                            aux_delta_time = i_delta_time

                        speed_row = self.__format_speed_data_row(
                            aux_date_obj, aux_day_type_id, ts_obj,
                            ss_obj, aux_delta_time, aux_delta_dist, local_timezone,
                            segment_criteria)
                        speed_data.append(speed_row)
                    aux_start_distance += i_delta_dist
        return speed_data

    def __format_speed_data_row(self, date_obj: datetime, day_type_id: str,
                                temporal_segment_obj: TemporalSegment, spatial_segment_obj: SpatialSegment,
                                delta_time: int, delta_distance: int, local_timezone: datetime.tzinfo,
                                segment_criteria: SegmentCriteria) -> dict:
        # get local info
        local_temporal_segment_obj = segment_criteria.get_temporal_segment(
            temporal_segment_obj.start_time, local_timezone)
        local_ts_index = local_temporal_segment_obj.index
        local_ts_name = local_temporal_segment_obj.get_name()
        local_date = local_temporal_segment_obj.get_date()
        local_day_type = segment_criteria.get_day_type(temporal_segment_obj.start_time, local_timezone)

        row = dict(route_id=self.route_id, shape_id=self.shape_id, pattern_id='pattern',
                   spatial_segment_index=spatial_segment_obj.index, spatial_segment_name=spatial_segment_obj.get_name(),
                   utc_date=date_obj.strftime('%Y-%m-%d'), utc_day_type=day_type_id,
                   utc_temporal_segment_index=temporal_segment_obj.index,
                   utc_temporal_segment_name=temporal_segment_obj.get_name(),
                   local_date=local_date.strftime('%Y-%m-%d'), local_day_type=local_day_type,
                   local_temporal_segment_index=local_ts_index, local_temporal_segment_name=local_ts_name,
                   distance_mts=delta_distance, time_secs=delta_time)

        return row
