from __future__ import annotations

import datetime
import logging
import math
from bisect import bisect_right
from collections import defaultdict
from typing import TYPE_CHECKING, List

import pytz
from django.utils.timezone import get_current_timezone
from processors.geometry.point import Point
from velocity.constants import SEGMENT_DISTANCE_METERS, TEMPORAL_SEGMENT_MINUTES
from rest_api.util.shape import ShapeManager

if TYPE_CHECKING:
    from velocity.grid import GridManager

logger = logging.getLogger(__name__)


class SpatialSegment:

    def __init__(
        self, index: int, start_distance: int, end_distance: int, is_last: bool = False
    ):
        self.index = index
        self.start_distance = start_distance
        self.end_distance = end_distance
        self.is_last = is_last

    def is_part_of(self, start_distance: int, end_distance: int) -> bool:
        if self.is_last:
            is_part_of = (
                self.start_distance <= start_distance <= self.end_distance
                or self.start_distance <= end_distance <= self.end_distance
            )
        else:
            is_part_of = (
                self.start_distance <= start_distance < self.end_distance
                or self.start_distance <= end_distance < self.end_distance
            )
        return is_part_of

    def get_name(self):
        return f"{self.start_distance}-{self.end_distance}"

    def __eq__(self, other):
        return (
            self.index == other.index
            and self.start_distance == other.start_distance
            and self.end_distance == other.end_distance
            and self.is_last == other.is_last
        )

    def __hash__(self):
        return hash((self.index, self.start_distance, self.end_distance))

    def __str__(self):
        return f"SpatialSegment {self.index} -> [{self.start_distance}-{self.end_distance})"


class PartialSpatialSegment(SpatialSegment):

    def __init__(
        self, start_distance: int, end_distance: int, spatial_segment: SpatialSegment
    ):
        super().__init__(
            spatial_segment.index, start_distance, end_distance, spatial_segment.is_last
        )
        value_error_message = f"partial segment {start_distance}-{end_distance} is not part of {spatial_segment}"
        if not (
            spatial_segment.start_distance
            <= start_distance
            <= spatial_segment.end_distance
            and spatial_segment.start_distance
            <= end_distance
            <= spatial_segment.end_distance
            and start_distance <= end_distance
        ):
            raise ValueError(value_error_message)
        self.complete_spatial_segment = spatial_segment

    def __eq__(self, other):
        return (
            super().__eq__(other)
            and self.complete_spatial_segment == other.complete_spatial_segment
        )

    def __str__(self):
        return f"PartialSpatialSegment {self.index} -> [{self.start_distance}-{self.end_distance})"


class TemporalSegment:

    def __init__(
        self, index: int, start_time: datetime.datetime, end_time: datetime.datetime
    ):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time

    def get_name(self):
        return f"[{self.start_time}-{self.end_time})"

    def get_date(self):
        return self.start_time.date()

    def __eq__(self, other):
        condition = (
            self.index == other.index
            and self.start_time == other.start_time
            and self.end_time == other.end_time
        )
        return condition

    def __hash__(self):
        return hash((self.index, self.start_time, self.end_time))

    def __str__(self):
        return f"TemporalSegment {self.index} -> [{self.start_time}-{self.end_time})"


class PartialTemporalSegment(TemporalSegment):

    def __init__(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        temporal_segment: TemporalSegment,
    ):
        super().__init__(temporal_segment.index, start_time, end_time)
        value_error_message = (
            f"partial segment {start_time}-{end_time} is not part of {temporal_segment}"
        )
        if not (
            temporal_segment.start_time <= start_time <= temporal_segment.end_time
            and temporal_segment.start_time <= end_time <= temporal_segment.end_time
            and start_time <= end_time
        ):
            raise ValueError(value_error_message)
        self.complete_temporal_segment = temporal_segment

    def __eq__(self, other):
        return (
            super().__eq__(other)
            and self.complete_temporal_segment == other.complete_temporal_segment
        )

    def __str__(self):
        return f"PartialTemporalSegment {self.index} -> [{self.start_time}-{self.end_time})"


class SegmentCriteria:

    def __init__(self, grid_manager: GridManager):
        self.grid_manager = grid_manager
        self.temporal_segment_duration = TEMPORAL_SEGMENT_MINUTES  # in minutes
        self.shape_manager = ShapeManager()

    def get_spatial_segment(self, *args, **kwargs):
        raise NotImplementedError("You must create a subclass of")

    def get_temporal_segment(
        self, dt: datetime.datetime, timezone: datetime.tzinfo = get_current_timezone()
    ):
        if dt.tzinfo is None:
            raise ValueError("datetime instance must have a tzinfo")
        converted_timestamp = dt.astimezone(timezone)
        day_seconds = (
            converted_timestamp.hour * 3600
            + converted_timestamp.minute * 60
            + converted_timestamp.second
        )
        index = int(day_seconds // (self.temporal_segment_duration * 60))

        start_time = converted_timestamp.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_time = start_time + datetime.timedelta(
            minutes=index * self.temporal_segment_duration
        )
        end_time = start_time + datetime.timedelta(
            minutes=self.temporal_segment_duration
        )

        ts_obj = TemporalSegment(index, start_time, end_time)
        return ts_obj

    def get_day_type(
        self, dt: datetime.datetime, timezone: datetime.tzinfo = get_current_timezone()
    ):
        if dt.tzinfo is None:
            raise ValueError("datetime instance must have a tzinfo")
        converted_timestamp = dt.astimezone(timezone)
        weekday = converted_timestamp.weekday()
        day_type = "L" if weekday < 5 else "S" if weekday == 5 else "D"

        return day_type

    def get_range_of_spatial_segments(self, *args, **kwargs):
        raise NotImplementedError("You must create a subclass of")

    def get_range_of_temporal_segments(
        self, dt1: datetime.datetime, dt2: datetime.datetime
    ) -> list[datetime]:
        """
        Obtains a list of temporal intervals between two datetime.

        :param dt1: Start datetime
        :type dt1: datetime.datetime

        :param dt2: End datetime
        :type dt2: datetime.datetime

        :return: List of 30-minute intervals
        :rtype: list[datetime.datetime]

        """
        number_of_periods = 60 * 24 / self.temporal_segment_duration
        periods = []
        first_temp_segment = self.get_temporal_segment(dt1)
        if first_temp_segment.start_time < dt1:
            new_first_temp_segment = PartialTemporalSegment(
                dt1, first_temp_segment.end_time, first_temp_segment
            )
            periods.append(new_first_temp_segment)
        else:
            periods.append(first_temp_segment)

        while True:
            if periods[-1].end_time >= dt2:
                break
            new_end_time = periods[-1].end_time + datetime.timedelta(
                minutes=self.temporal_segment_duration
            )

            next_index = int((periods[-1].index + 1) % number_of_periods)
            periods.append(
                TemporalSegment(next_index, periods[-1].end_time, new_end_time)
            )

        if periods[-1].end_time > dt2:
            if isinstance(periods[-1], PartialTemporalSegment):
                segment_parent = periods[-1].complete_temporal_segment
            else:
                segment_parent = periods[-1]
            periods[-1] = PartialTemporalSegment(
                periods[-1].start_time, dt2, segment_parent
            )

        return periods


class FiveHundredMeterSegmentCriteria(SegmentCriteria):

    def __init__(self, grid_manager):
        super().__init__(grid_manager)
        self.spatial_segment_distance = SEGMENT_DISTANCE_METERS  # in meters
        (
            self.spatial_segments_by_shape_id,
            self.spatial_segment_init_list_by_shape_id,
        ) = self.__calculate_spatial_segments()
        self.shape_id_distance_dict = {
            shape_id: segments[-1].end_distance
            for shape_id, segments in self.spatial_segments_by_shape_id.items()
        }

    def __calculate_spatial_segments(self):
        """Build the spatial segments from the Segment rows stored in the DB.

        The boundaries are the cumulative lengths of the stored segments, so the
        segment index always matches Segment.sequence (the merge of a short last
        segment was already done when the axis was segmented). Re-cutting the total
        length every SEGMENT_DISTANCE_METERS drifts, because stored segments are not
        exactly that long after simplification.
        """
        segment_init_list = defaultdict(list)
        data = dict()
        for shape_pk, db_segments in self.shape_manager.get_segments().items():
            shape_id = str(shape_pk)
            segment_list = []
            start_distance = 0.0
            for index, db_segment in enumerate(db_segments):
                end_distance = start_distance + db_segment.get_distance()
                segment_list.append(
                    SpatialSegment(
                        index,
                        start_distance,
                        end_distance,
                        is_last=index == len(db_segments) - 1,
                    )
                )
                segment_init_list[shape_id].append(start_distance)
                start_distance = end_distance

            if not segment_list or segment_list[-1].end_distance == 0:
                logger.error(f"Shape ID {shape_id} with a distance of 0 meters.")
                segment_init_list.pop(shape_id, None)
                continue

            data[shape_id] = segment_list

        return data, segment_init_list

    def get_spatial_segment(self, shape_id: str, distance: int) -> SpatialSegment:
        segment_list = self.spatial_segments_by_shape_id[shape_id]
        index = bisect_right(
            self.spatial_segment_init_list_by_shape_id[shape_id], distance
        )

        if distance < 0 or distance > segment_list[-1].end_distance:
            raise ValueError(f"distance {distance} is not part of the shape {shape_id}")

        if index == len(self.spatial_segment_init_list_by_shape_id[shape_id]):
            return segment_list[-1]
        else:
            return segment_list[index - 1]

    def get_range_of_spatial_segments(
        self, shape_id: str, start_distance: int, end_distance: int
    ) -> List[SpatialSegment or PartialSpatialSegment]:
        """
        Parameters:
        - `shape_id`: A string representing the shape identifier.
        - `start_distance`: An integer representing the starting distance.
        - `end_distance`: An integer representing the ending distance.

        Returns:
        - A list of `SpatialSegment` or PartialSpatialSegment objects that fall within the specified range of distances.
        """
        segment_list = self.spatial_segments_by_shape_id[shape_id]
        result_segment = []
        aux_start_distance = start_distance
        for segment_obj in segment_list:
            if segment_obj.is_part_of(aux_start_distance, end_distance):
                result_segment.append(segment_obj)
                aux_start_distance = min(end_distance, segment_obj.end_distance)

        if start_distance > result_segment[0].start_distance:
            result_segment[0] = PartialSpatialSegment(
                start_distance, result_segment[0].end_distance, result_segment[0]
            )
        if end_distance < result_segment[-1].end_distance:
            if isinstance(result_segment[-1], PartialSpatialSegment):
                segment_parent = result_segment[-1].complete_spatial_segment
            else:
                segment_parent = result_segment[-1]
            result_segment[-1] = PartialSpatialSegment(
                result_segment[-1].start_distance, end_distance, segment_parent
            )

        return result_segment
