from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from django.utils.timezone import get_current_timezone

from velocity.gps import GPSPulse as GPS
from velocity.segment import (
    PartialSpatialSegment,
    PartialTemporalSegment,
    SegmentCriteria,
    SpatialSegment,
    TemporalSegment,
)

if TYPE_CHECKING:
    from velocity.grid import GridManager


# TODO: Add vehicle license plate if necessary
class ExpeditionData:
    MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES = 60 * 10  # in seconds
    MAXIMUM_STATIONARY_TIME = 60 * 5  # 5 minutos (300 segundos)
    MINIMUM_MOVEMENT_THRESHOLD = 5  # metros mínimos para considerar movimiento

    def __init__(
        self,
        grid_manager: GridManager,
        route_id: str | None,
        timestamp: datetime,
        license_plate: str,
    ):
        self.id = uuid.uuid4()
        self.grid_manager = grid_manager

        self.license_plate = license_plate
        self.timestamp = timestamp
        self.route_id = route_id
        self.shape_id = None

        self.gps_points = []
        self.gps_distance_to_route = []
        self.gps_distance_on_route = []
        self.gps_distance_on_route_dict = dict()

        self.ignored_gps_pulses = 0
        self.ignored_segments_because_time_between_gps_pulses = 0
        self.ignored_segments_because_stationary = 0

    def add_gps_point(self, gps_pulse: GPS):
        if len(self.gps_points) == 0:
            self.gps_points.append(gps_pulse)
        elif gps_pulse.timestamp > self.gps_points[-1].timestamp:
            self.gps_points.append(gps_pulse)
        elif gps_pulse.timestamp == self.gps_points[-1].timestamp:
            # print(f'gps point {gps_pulse} is equal to previous gps point {gps_pulse}.')
            self.ignored_gps_pulses += 1
        elif gps_pulse.timestamp < self.gps_points[-1].timestamp:
            # print(f'gps point {gps_pulse} is older than latest gps point {gps_pulse}.')
            self.ignored_gps_pulses += 1

    def _get_stationary_indices(self) -> set[int]:
        """
        Identifies indexes of GPS points where the vehicle has been stationary (MINIMUM_MOVEMENT_THRESHOLD)
        for longer than MAXIMUM_STATIONARY_TIME based on gps_distance_on_route and also dont have a route_id
        (i.e. route_id=nan).

        Returns
        -------
        set[int]
            A set of indices corresponding to stationary GPS point.
        """
        n_points = len(self.gps_points)
        # Only filter stationary points for expeditions without a route_id
        # route_id can be None, "nan" (string from pandas category), or a valid route string
        has_valid_route = self.route_id is not None and self.route_id != "nan"
        if n_points < 2 or has_valid_route:
            return set()

        distances = self.gps_distance_on_route
        points = self.gps_points
        threshold = self.MINIMUM_MOVEMENT_THRESHOLD
        max_stationary = self.MAXIMUM_STATIONARY_TIME

        indices_to_exclude = set()
        stationary_start_idx = None
        stationary_start_time = None
        threshold_exceeded = False  # Flag para saber si ya se superó el umbral

        for i in range(1, n_points):
            prev_dist = distances[i - 1]
            curr_dist = distances[i]

            # Saltar puntos sin proyección válida
            # TODO: Revisar si es necesario reiniciar el período estacionario al encontrar puntos sin proyección, 
            # o si se pueden ignorar simplemente en la lógica de cálculo de velocidad. 
            # Por ahora, se reinicia el seguimiento para evitar falsos positivos de estacionariedad debido a gaps en la proyección.
            if prev_dist is None or curr_dist is None:
                # Reiniciar período estacionario si hay gaps
                stationary_start_idx = None
                threshold_exceeded = False
                continue

            delta_distance = abs(curr_dist - prev_dist)

            if delta_distance < threshold:
                # Inicio o continuación de período estacionario
                if stationary_start_idx is None:
                    stationary_start_idx = i - 1
                    stationary_start_time = points[i - 1].timestamp
                    threshold_exceeded = False

                # Verificar duración acumulada
                elapsed = (points[i].timestamp - stationary_start_time).total_seconds()

                if elapsed >= max_stationary:
                    if not threshold_exceeded:
                        # Primera vez que se supera el umbral - marcar este índice
                        threshold_exceeded = True
                    # Solo agregar índices a partir de que se superó el umbral
                    indices_to_exclude.add(i)
            else:
                # Movimiento detectado - reiniciar tracking
                stationary_start_idx = None
                stationary_start_time = None
                threshold_exceeded = False

        return indices_to_exclude

    def calculate_speed(
        self,
        segment_criteria: SegmentCriteria,
        local_timezone: ZoneInfo = get_current_timezone(),
    ):
        speed_data = []
        if len(self.gps_points) < 2:
            raise ValueError(f"{self} has {len(self.gps_points)} gps points.")

        # Validar que gps_distance_on_route esté inicializada y tenga valores
        if not self.gps_distance_on_route or len(self.gps_distance_on_route) != len(
            self.gps_points
        ):
            if self.shape_id is None:
                raise ValueError
            raise ValueError(
                f"{self} does not have distance_on_route calculated. "
                f"Expected {len(self.gps_points)} distances, got {len(self.gps_distance_on_route) if self.gps_distance_on_route else 0}."
            )

        # Contador de puntos descartados por falta de proyección HMM
        skipped_no_projection = 0

        # Obtener índices de períodos estacionarios (O(n) pre-cálculo)
        stationary_indices = self._get_stationary_indices()

        for index, gps_pulse in enumerate(self.gps_points[1:], start=1):
            # Saltar pulsos sin recorrido asignado y en períodos estacionarios >= 5 min
            if index in stationary_indices:
                self.ignored_segments_because_stationary += 1
                print(
                    f"{self}: Skipping stationary pulse at index {index} (>= 5 min stopped)."
                )
                continue
            previous_gps_pulse = self.gps_points[index - 1]
            previous_distance = self.gps_distance_on_route[index - 1]
            current_distance = self.gps_distance_on_route[index]

            # Descartar pulsos GPS que no fueron matcheados por el HMM
            # Estos tienen None en gps_distance_on_route
            if previous_distance is None or current_distance is None:
                skipped_no_projection += 1
                continue

            # calculate distance and time difference
            delta_time = (
                gps_pulse.timestamp - previous_gps_pulse.timestamp
            ).total_seconds()
            delta_distance = current_distance - previous_distance

            # Validar monotonía: descartar si hay retroceso significativo (> 50m)
            # TODO: Analizar bien la no monotonía con respecto a la distancia previa y actual. Ver los casos 
            # típicos de no monotonía (ej. GPS errático, cambio de ruta, etc.) y ajustar el umbral o la lógica según corresponda.
            # Ej de error: Expedition (519R,VPYD41,2): Skipping non-monotonic distance (prev=15406.0m, curr=9563.7m, next=9976.9m)
            if delta_distance < -50:
                next_gps_pulse = (
                    self.gps_points[index + 1]
                    if index + 1 < len(self.gps_points)
                    else None
                )
                next_distance = (
                    self.gps_distance_on_route[index + 1] if next_gps_pulse else None
                )
                if next_distance is not None and next_distance >= current_distance:
                    print(
                        f"{self}: Skipping non-monotonic distance "
                        f"(prev={previous_distance:.1f}m, curr={current_distance:.1f}m, next={next_distance:.1f}m)"
                    )
                skipped_no_projection += 1
                continue

            # Asegurar que delta_distance sea positivo (pequeños retrocesos de proyección)
            if delta_distance < 0:
                delta_distance = 0

            if delta_time >= self.MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES:
                print(
                    f"time window between {previous_gps_pulse.timestamp} and {gps_pulse.timestamp} is greater than {self.MAXIMUM_ACCEPTABLE_TIME_BETWEEN_GPS_PULSES} seconds"
                )
                self.ignored_segments_because_time_between_gps_pulses += 1
                continue

            current_temporal_segment_obj = segment_criteria.get_temporal_segment(
                gps_pulse.timestamp
            )
            previous_temporal_segment_obj = segment_criteria.get_temporal_segment(
                previous_gps_pulse.timestamp
            )

            current_spatial_segment_obj = segment_criteria.get_spatial_segment(
                self.shape_id, current_distance
            )
            previous_spatial_segment_obj = segment_criteria.get_spatial_segment(
                self.shape_id, previous_distance
            )

            if (
                current_temporal_segment_obj == previous_temporal_segment_obj
                and current_spatial_segment_obj == previous_spatial_segment_obj
            ):
                current_day_type_id = segment_criteria.get_day_type(gps_pulse.timestamp)
                date_obj = gps_pulse.timestamp.date()

                speed_row = self.__format_speed_data_row(
                    date_obj,
                    current_day_type_id,
                    current_temporal_segment_obj,
                    current_spatial_segment_obj,
                    delta_time,
                    delta_distance,
                    local_timezone,
                    segment_criteria,
                )
                speed_data.append(speed_row)
            else:
                # Calculate speed difference for interpolation between periods
                delta_speed = delta_distance / delta_time

                range_of_temporal_segments = (
                    segment_criteria.get_range_of_temporal_segments(
                        previous_gps_pulse.timestamp, gps_pulse.timestamp
                    )
                )

                aux_start_distance = previous_distance
                for temporal_segment_obj in range_of_temporal_segments:
                    aux_day_type_id = segment_criteria.get_day_type(
                        temporal_segment_obj.start_time
                    )
                    aux_date_obj = temporal_segment_obj.start_time.date()

                    ts_obj = temporal_segment_obj
                    if isinstance(temporal_segment_obj, PartialTemporalSegment):
                        ts_obj = temporal_segment_obj.complete_temporal_segment

                    # Calculate interpolated time and distance
                    i_delta_time = (
                        temporal_segment_obj.end_time - temporal_segment_obj.start_time
                    ).total_seconds()
                    i_delta_dist = delta_speed * i_delta_time
                    range_of_spatial_segments = (
                        segment_criteria.get_range_of_spatial_segments(
                            self.shape_id,
                            aux_start_distance,
                            aux_start_distance + i_delta_dist,
                        )
                    )
                    for spatial_segment_obj in range_of_spatial_segments:
                        # calculate interpolated time and distance
                        ss_obj = spatial_segment_obj
                        if isinstance(spatial_segment_obj, PartialSpatialSegment):
                            ss_obj = spatial_segment_obj.complete_spatial_segment

                        aux_delta_dist = (
                            spatial_segment_obj.end_distance
                            - spatial_segment_obj.start_distance
                        )
                        if delta_speed != 0:
                            aux_delta_time = aux_delta_dist / delta_speed
                        else:
                            aux_delta_time = i_delta_time

                        speed_row = self.__format_speed_data_row(
                            aux_date_obj,
                            aux_day_type_id,
                            ts_obj,
                            ss_obj,
                            aux_delta_time,
                            aux_delta_dist,
                            local_timezone,
                            segment_criteria,
                        )
                        speed_data.append(speed_row)
                    aux_start_distance += i_delta_dist

        return speed_data

    def __format_speed_data_row(
        self,
        date_obj: datetime,
        day_type_id: str,
        temporal_segment_obj: TemporalSegment,
        spatial_segment_obj: SpatialSegment,
        delta_time: int,
        delta_distance: int,
        local_timezone: datetime.tzinfo,
        segment_criteria: SegmentCriteria,
    ) -> dict:
        # get local info
        local_temporal_segment_obj = segment_criteria.get_temporal_segment(
            temporal_segment_obj.start_time, local_timezone
        )
        local_ts_index = local_temporal_segment_obj.index
        local_ts_name = local_temporal_segment_obj.get_name()
        local_date = local_temporal_segment_obj.get_date()
        local_day_type = segment_criteria.get_day_type(
            temporal_segment_obj.start_time, local_timezone
        )
        row = dict(
            route_id=self.route_id,
            shape_id=self.shape_id,
            pattern_id="pattern",
            spatial_segment_index=spatial_segment_obj.index,
            spatial_segment_name=spatial_segment_obj.get_name(),
            utc_date=date_obj.strftime("%Y-%m-%d"),
            utc_day_type=day_type_id,
            utc_temporal_segment_index=temporal_segment_obj.index,
            utc_temporal_segment_name=temporal_segment_obj.get_name(),
            local_date=local_date.strftime("%Y-%m-%d"),
            local_day_type=local_day_type,
            local_temporal_segment_index=local_ts_index,
            local_temporal_segment_name=local_ts_name,
            distance_mts=delta_distance,
            time_secs=delta_time,
        )

        return row

    def __eq__(self, other):
        return isinstance(other, ExpeditionData) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        route = self.route_id if self.route_id else "Unknown"
        shape = self.shape_id if self.shape_id else "NoShape"
        return f"Expedition ({route},{self.license_plate},{shape})"
