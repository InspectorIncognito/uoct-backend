import gzip
import io
import json
import os
import threading
from datetime import datetime

from django.core.management import call_command
from django.db.models import ExpressionWrapper, F, FloatField
from django.db.models.functions import Round
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from geojson import Feature, FeatureCollection, Point
from gtfs_rt.processors.speed import calculate_speed
from gtfs_rt.utils import get_last_temporal_range, get_previous_month
from processors.models.shapes import shapes_to_geojson
from rest_api.models import (Alert, AlertThreshold, Axles, Camera, GTFSShape,
                             HistoricSpeed, Segment, Services, Shape, Speed,
                             Stop, TrafficSignal)
from rest_api.serializers import (AlertSerializer, AlertThresholdSerializer,
                                  AxlesSerializer, CameraSerializer,
                                  GTFSShapeSerializer, HistoricSpeedSerializer,
                                  ProcessAxisSerializer, SegmentSerializer,
                                  ServicesSerializer, ShapeSerializer,
                                  SpeedSerializer, StopSerializer,
                                  TrafficSignalSerializer)
from rest_framework import generics, mixins, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import AllowAny
from velocity.grid import GridManager
from velocity.gtfs import GTFSManager


class TestView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = None  # View returns custom JSON response

    def get(self, request, *args, **kwargs):
        gm = GridManager()
        filtered_gps = gm.filter_gps()
        response = dict(
            count=len(filtered_gps), data=json.loads(filtered_gps.to_json())
        )

        # gm = GTFSManager()
        # shapes_reader = gm.shapes_reader
        # df = shapes_reader.load_csv_file_as_df()
        # processed_df = shapes_reader.process_df(df)
        # response = json.loads(processed_df.to_json())

        return JsonResponse(data=response, safe=False)


class GeoJSONViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = None  # View returns GeoJSON response

    def get(self, request):
        # Returns a GeoJSON with the latest data.
        # This includes the 500-meter-segmented-path with its corresponding velocities
        shapes_json = shapes_to_geojson()

        return JsonResponse(shapes_json, safe=False)


class GTFSStopsViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = None  # View returns GeoJSON response

    def get(self, request):
        gtfs_manager = GTFSManager()
        stops = gtfs_manager.stops_reader.load_csv_file_as_df()
        stopsFeatureCollection = []
        for idx, stop in stops.iterrows():
            stop_lat = stop["stop_lat"]
            stop_lon = stop["stop_lon"]
            stopsFeatureCollection.append(
                Feature(geometry=Point(coordinates=[stop_lon, stop_lat]))
            )
        stopsFeatureCollection = FeatureCollection(stopsFeatureCollection)
        return JsonResponse(stopsFeatureCollection, safe=False)


class ShapeViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = Shape.objects.all()
    serializer_class = ShapeSerializer


class SegmentViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = SegmentSerializer

    def get_queryset(self):
        # Handle schema generation when shape_pk is not available
        if getattr(self, "swagger_fake_view", False):
            return Segment.objects.none()
        return Segment.objects.filter(shape__id=self.kwargs["shape_pk"]).order_by(
            "sequence"
        )


class ServicesViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = ServicesSerializer
    queryset = Services.objects.all()


class GenericSpeedViewSet(viewsets.ModelViewSet, mixins.ListModelMixin):
    class Meta:
        abstract = True

    permission_classes = [AllowAny]
    serializer_class = None
    queryset = None

    filter_backends = [OrderingFilter]  # Add to existing backends if you have any
    ordering_fields = [
        "segment__shape",
        "segment__sequence",
        "temporal_segment",
        "day_type",
        "distance",
        "time_secs",
        "timestamp",
    ]
    ordering = ["segment", "temporal_segment"]  # Default ordering

    def get_queryset(self):
        queryset = self.queryset
        start_time = self.request.query_params.get("startTime")
        end_time = self.request.query_params.get("endTime")
        month = self.request.query_params.get("month")
        day_type = self.request.query_params.get("dayType")
        temporal_segment = self.request.query_params.get("temporalSegment")

        if month is not None:
            month = int(month)
            year = timezone.now().year
            queryset = queryset.filter(timestamp__year=year, timestamp__month=month)
        if start_time is not None and end_time is not None:
            start_time = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
            start_time = timezone.make_aware(start_time, timezone.utc)
            end_time = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ")
            end_time = timezone.make_aware(end_time, timezone.utc)
            queryset = queryset.filter(
                timestamp__gte=start_time, timestamp__lte=end_time
            )

        if day_type is not None:
            queryset = queryset.filter(day_type=day_type)
        if temporal_segment is not None:
            queryset = queryset.filter(temporal_segment=temporal_segment)
        if not self.request.query_params.get("ordering"):
            queryset = queryset.order_by("segment", "temporal_segment")
        return queryset

    @staticmethod
    def _build_where_clause(query_params, alias):
        """Translate DRF query params into a parameterized SQL WHERE clause.

        Returns (where_sql, params_list). Does NOT include a default filter —
        callers must inject one when query_params is empty.
        ``alias`` is the SQL table alias used for the speed/historic-speed table
        (e.g. 'sp' for Speed, 'hs' for HistoricSpeed).
        """
        clauses = []
        params = []

        month = query_params.get("month")
        start_time = query_params.get("startTime")
        end_time = query_params.get("endTime")
        day_type = query_params.get("dayType")
        temporal_segment = query_params.get("temporalSegment")

        if month is not None:
            year = timezone.now().year
            clauses.append(f"EXTRACT(YEAR  FROM {alias}.timestamp) = %s")
            clauses.append(f"EXTRACT(MONTH FROM {alias}.timestamp) = %s")
            params.extend([year, int(month)])
        if start_time is not None and end_time is not None:
            start_dt = timezone.make_aware(
                datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ"), timezone.utc
            )
            end_dt = timezone.make_aware(
                datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ"), timezone.utc
            )
            clauses.append(f"{alias}.timestamp >= %s AND {alias}.timestamp <= %s")
            params.extend([start_dt, end_dt])
        if day_type is not None:
            clauses.append(f"{alias}.day_type = %s")
            params.append(day_type)
        if temporal_segment is not None:
            clauses.append(f"{alias}.temporal_segment = %s")
            params.append(int(temporal_segment))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    @staticmethod
    def _copy_stream(copy_sql, params, compress=False):
        """Generator that streams PostgreSQL COPY TO STDOUT output.

        ``copy_sql`` is a string with ``%s`` placeholders (psycopg2 format).
        ``params`` is a list/tuple of values to bind.
        When ``compress=True`` the output is gzip-compressed on-the-fly in 64 KB
        chunks using a background thread + os.pipe so that ``copy_expert``'s
        blocking writes never stall the HTTP response generator.
        """
        error_holder = [None]
        read_fd, write_fd = os.pipe()

        def _worker():
            from django.db import \
                connection as _conn  # thread-local connection

            try:
                with os.fdopen(write_fd, "wb") as pipe_w:
                    with _conn.cursor() as cursor:
                        final_sql = cursor.mogrify(copy_sql, params)
                        cursor.copy_expert(final_sql, pipe_w)
            except Exception as exc:
                error_holder[0] = exc
                # Ensure write-end is closed so the reader unblocks
                try:
                    os.close(write_fd)
                except OSError:
                    pass
            finally:
                _conn.close()  # Release thread-local connection

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        if compress:
            gz_buf = io.BytesIO()
            gz = gzip.GzipFile(fileobj=gz_buf, mode="wb")
            with os.fdopen(read_fd, "rb") as pipe_r:
                while True:
                    chunk = pipe_r.read(65536)
                    if not chunk:
                        break
                    gz.write(chunk)
                    gz.flush()  # flushes zlib buffer to gz_buf
                    gz_buf.seek(0)
                    data = gz_buf.read()
                    if data:
                        yield data
                    gz_buf.seek(0)
                    gz_buf.truncate(0)
            gz.close()
            gz_buf.seek(0)
            tail = gz_buf.read()
            if tail:
                yield tail
        else:
            with os.fdopen(read_fd, "rb") as pipe_r:
                while True:
                    chunk = pipe_r.read(65536)
                    if not chunk:
                        break
                    yield chunk

        thread.join()
        if error_holder[0] is not None:
            raise error_holder[0]


class SpeedViewSet(GenericSpeedViewSet):
    serializer_class = SpeedSerializer
    queryset = Speed.objects.all().order_by("-temporal_segment")

    filter_backends = [OrderingFilter]  # Add to existing backends if you have any
    ordering_fields = [
        "segment__shape",
        "segment__sequence",
        "temporal_segment",
        "day_type",
        "distance",
        "time_secs",
        "timestamp",
    ]
    ordering = ["-timestamp"]  # Default ordering

    def to_csv(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="sp")

        if len(request.query_params) == 0:
            start_time, end_time = get_last_temporal_range()
            if where_sql:
                where_sql += " AND sp.timestamp >= %s AND sp.timestamp <= %s"
            else:
                where_sql = "WHERE sp.timestamp >= %s AND sp.timestamp <= %s"
            params.extend([start_time, end_time])

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    sp.temporal_segment,
                    sp.day_type,
                    sp.distance,
                    sp.time_secs,
                    sp.timestamp,
                    array_to_string(sp.services, ';') AS active_services
                FROM rest_api_speed sp
                INNER JOIN rest_api_segment sg
                    ON sp.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, sp.temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=False),
            content_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="segment_speeds.csv"',
            },
        )

    def to_csv_gz(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="sp")

        if len(request.query_params) == 0:
            start_time, end_time = get_last_temporal_range()
            if where_sql:
                where_sql += " AND sp.timestamp >= %s AND sp.timestamp <= %s"
            else:
                where_sql = "WHERE sp.timestamp >= %s AND sp.timestamp <= %s"
            params.extend([start_time, end_time])

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    sp.temporal_segment,
                    sp.day_type,
                    sp.distance,
                    sp.time_secs,
                    sp.timestamp,
                    array_to_string(sp.services, ';') AS active_services
                FROM rest_api_speed sp
                INNER JOIN rest_api_segment sg
                    ON sp.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, sp.temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=True),
            content_type="application/gzip",
            headers={
                "Content-Disposition": 'attachment; filename="segment_speeds.csv.gz"',
            },
        )

    def to_csv_local(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="sp")

        if len(request.query_params) == 0:
            start_time, end_time = get_last_temporal_range()
            if where_sql:
                where_sql += " AND sp.timestamp >= %s AND sp.timestamp <= %s"
            else:
                where_sql = "WHERE sp.timestamp >= %s AND sp.timestamp <= %s"
            params.extend([start_time, end_time])

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    FLOOR(
                        (
                            EXTRACT(HOUR FROM (sp.timestamp AT TIME ZONE 'America/Santiago')) * 60
                            + EXTRACT(MINUTE FROM (sp.timestamp AT TIME ZONE 'America/Santiago'))
                        ) / 15
                    )::int AS temporal_segment,
                    CASE
                        WHEN EXTRACT(ISODOW FROM (sp.timestamp AT TIME ZONE 'America/Santiago')) BETWEEN 1 AND 5 THEN 'L'
                        WHEN EXTRACT(ISODOW FROM (sp.timestamp AT TIME ZONE 'America/Santiago')) = 6 THEN 'S'
                        ELSE 'D'
                    END AS day_type,
                    sp.distance,
                    sp.time_secs,
                    (sp.timestamp AT TIME ZONE 'America/Santiago') AS timestamp,
                    array_to_string(sp.services, ';') AS active_services
                FROM rest_api_speed sp
                INNER JOIN rest_api_segment sg
                    ON sp.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=False),
            content_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="segment_speeds_local.csv"',
            },
        )

    def to_csv_local_gz(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="sp")

        if len(request.query_params) == 0:
            start_time, end_time = get_last_temporal_range()
            if where_sql:
                where_sql += " AND sp.timestamp >= %s AND sp.timestamp <= %s"
            else:
                where_sql = "WHERE sp.timestamp >= %s AND sp.timestamp <= %s"
            params.extend([start_time, end_time])

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    FLOOR(
                        (
                            EXTRACT(HOUR FROM (sp.timestamp AT TIME ZONE 'America/Santiago')) * 60
                            + EXTRACT(MINUTE FROM (sp.timestamp AT TIME ZONE 'America/Santiago'))
                        ) / 15
                    )::int AS temporal_segment,
                    CASE
                        WHEN EXTRACT(ISODOW FROM (sp.timestamp AT TIME ZONE 'America/Santiago')) BETWEEN 1 AND 5 THEN 'L'
                        WHEN EXTRACT(ISODOW FROM (sp.timestamp AT TIME ZONE 'America/Santiago')) = 6 THEN 'S'
                        ELSE 'D'
                    END AS day_type,
                    sp.distance,
                    sp.time_secs,
                    (sp.timestamp AT TIME ZONE 'America/Santiago') AS timestamp,
                    array_to_string(sp.services, ';') AS active_services
                FROM rest_api_speed sp
                INNER JOIN rest_api_segment sg
                    ON sp.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=True),
            content_type="application/gzip",
            headers={
                "Content-Disposition": 'attachment; filename="segment_speeds_local.csv.gz"',
            },
        )


class HistoricSpeedViewSet(GenericSpeedViewSet):
    serializer_class = HistoricSpeedSerializer
    queryset = HistoricSpeed.objects.all().order_by("segment")

    def to_csv(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="hs")

        if len(request.query_params) == 0:
            previous_month = get_previous_month()
            if where_sql:
                where_sql += " AND EXTRACT(MONTH FROM hs.timestamp) = %s"
            else:
                where_sql = "WHERE EXTRACT(MONTH FROM hs.timestamp) = %s"
            params.append(previous_month)

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    hs.temporal_segment,
                    hs.day_type,
                    hs.speed
                FROM rest_api_historicspeed hs
                INNER JOIN rest_api_segment sg
                    ON hs.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, hs.temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=False),
            content_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="historic_speeds.csv"',
            },
        )

    def to_csv_gz(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="hs")

        if len(request.query_params) == 0:
            previous_month = get_previous_month()
            if where_sql:
                where_sql += " AND EXTRACT(MONTH FROM hs.timestamp) = %s"
            else:
                where_sql = "WHERE EXTRACT(MONTH FROM hs.timestamp) = %s"
            params.append(previous_month)

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    hs.temporal_segment,
                    hs.day_type,
                    hs.speed
                FROM rest_api_historicspeed hs
                INNER JOIN rest_api_segment sg
                    ON hs.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, hs.temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=True),
            content_type="application/gzip",
            headers={
                "Content-Disposition": 'attachment; filename="historic_speeds.csv.gz"',
            },
        )

    def to_csv_local(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="hs")

        if len(request.query_params) == 0:
            previous_month = get_previous_month()
            if where_sql:
                where_sql += " AND EXTRACT(MONTH FROM hs.timestamp) = %s"
            else:
                where_sql = "WHERE EXTRACT(MONTH FROM hs.timestamp) = %s"
            params.append(previous_month)

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    FLOOR(
                        (
                            EXTRACT(HOUR FROM (hs.timestamp AT TIME ZONE 'America/Santiago')) * 60
                            + EXTRACT(MINUTE FROM (hs.timestamp AT TIME ZONE 'America/Santiago'))
                        ) / 15
                    )::int AS temporal_segment,
                    CASE
                        WHEN EXTRACT(ISODOW FROM (hs.timestamp AT TIME ZONE 'America/Santiago')) BETWEEN 1 AND 5 THEN 'L'
                        WHEN EXTRACT(ISODOW FROM (hs.timestamp AT TIME ZONE 'America/Santiago')) = 6 THEN 'S'
                        ELSE 'D'
                    END AS day_type,
                    hs.speed,
                    (hs.timestamp AT TIME ZONE 'America/Santiago') AS timestamp
                FROM rest_api_historicspeed hs
                INNER JOIN rest_api_segment sg
                    ON hs.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=False),
            content_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="historic_speeds_local.csv"',
            },
        )

    def to_csv_local_gz(self, request, *args, **kwargs):
        where_sql, params = self._build_where_clause(request.query_params, alias="hs")

        if len(request.query_params) == 0:
            previous_month = get_previous_month()
            if where_sql:
                where_sql += " AND EXTRACT(MONTH FROM hs.timestamp) = %s"
            else:
                where_sql = "WHERE EXTRACT(MONTH FROM hs.timestamp) = %s"
            params.append(previous_month)

        copy_sql = f"""
            COPY (
                SELECT
                    sg.shape_id AS shape,
                    sg.sequence AS sequence,
                    FLOOR(
                        (
                            EXTRACT(HOUR FROM (hs.timestamp AT TIME ZONE 'America/Santiago')) * 60
                            + EXTRACT(MINUTE FROM (hs.timestamp AT TIME ZONE 'America/Santiago'))
                        ) / 15
                    )::int AS temporal_segment,
                    CASE
                        WHEN EXTRACT(ISODOW FROM (hs.timestamp AT TIME ZONE 'America/Santiago')) BETWEEN 1 AND 5 THEN 'L'
                        WHEN EXTRACT(ISODOW FROM (hs.timestamp AT TIME ZONE 'America/Santiago')) = 6 THEN 'S'
                        ELSE 'D'
                    END AS day_type,
                    hs.speed,
                    (hs.timestamp AT TIME ZONE 'America/Santiago') AS timestamp
                FROM rest_api_historicspeed hs
                INNER JOIN rest_api_segment sg
                    ON hs.segment_id = sg.segment_id
                {where_sql}
                ORDER BY sg.shape_id, sg.sequence, temporal_segment
            ) TO STDOUT WITH CSV HEADER
        """
        return StreamingHttpResponse(
            self._copy_stream(copy_sql, params, compress=True),
            content_type="application/gzip",
            headers={
                "Content-Disposition": 'attachment; filename="historic_speeds_local.csv.gz"',
            },
        )


class AlertViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = AlertSerializer
    queryset = Alert.objects.all()

    def active(self, request, *args, **kwargs):
        queryset = (
            self.get_queryset()
            .annotate(
                shape=F("segment__shape"),
                sequence=F("segment__sequence"),
                speed=ExpressionWrapper(
                    Round(
                        F("detected_speed__distance") / F("detected_speed__time_secs"),
                        2,
                    ),
                    output_field=FloatField(),
                ),
                date=F("timestamp__date"),
            )
            .values(
                "shape",
                "sequence",
                "speed",
                "temporal_segment",
                "useful",
                "useless",
                "date",
            )
        )
        if len(self.request.query_params) == 0:
            start_time, end_time = get_last_temporal_range()
            queryset = queryset.filter(
                timestamp__gte=start_time,
                timestamp__lte=end_time,
            )
        response = dict(count=queryset.count(), results=list(queryset))
        return JsonResponse(response, safe=False)


class StopViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = StopSerializer
    queryset = Stop.objects.all()

    def to_geojson(self, request, *args, **kwargs):
        stops = self.get_queryset()
        stops_feature_collection = []
        for stop in stops:
            stops_feature_collection.append(
                Feature(
                    geometry=Point(coordinates=[stop.longitude, stop.latitude]),
                    properties={
                        "shape_pk": stop.segment.shape.pk,
                        "segment_pk": stop.segment.sequence,
                    },
                )
            )
        stops_feature_collection = FeatureCollection(stops_feature_collection)
        return JsonResponse(stops_feature_collection, safe=False)


class GTFSShapeViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = GTFSShapeSerializer
    queryset = GTFSShape.objects.all().order_by("shape_id")

    def get_queryset(self, *args, **kwargs):
        queryset = GTFSShape.objects.all().order_by("shape_id")
        query_params = self.request.query_params
        direction = query_params.get("direction")
        if direction is not None:
            queryset = queryset.filter(direction=direction)
        return queryset

    def geojson(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        features_list = []
        for shape in queryset:
            features_list.append(shape.to_geojson())
        geojson = FeatureCollection(features=features_list)
        return JsonResponse(geojson)


class GridViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = None  # View returns custom JSON response

    def get(self, request):
        speed_records = calculate_speed()
        return JsonResponse({"speeds": speed_records})


class AlertThresholdViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
):
    permission_classes = [
        AllowAny,
    ]
    queryset = AlertThreshold.objects.all()
    serializer_class = AlertThresholdSerializer


class AxlesViewSet(viewsets.ModelViewSet):
    queryset = Axles.objects.all().order_by("id")
    serializer_class = AxlesSerializer
    permission_classes = [AllowAny]

    def destroy(self, request, *args, **kwargs):
        """
        Override destroy to also delete associated shapes, segments, speeds, etc.
        This ensures that deleting an Axle also cleans up all related data.
        """
        instance = self.get_object()
        axis_name = instance.name

        # Delete all related shapes and their data
        deleted_info = self._delete_axis_shapes(axis_name)

        # Delete the Axle itself
        self.perform_destroy(instance)

        return JsonResponse(
            {
                "status": "success",
                "message": f"Eje '{axis_name}' eliminado exitosamente",
                "deleted": deleted_info,
            }
        )

    def _delete_axis_shapes(self, axis_name: str) -> dict:
        """
        Delete all shapes associated with an axis name, including:
        - Speed records
        - HistoricSpeed records
        - Alert records
        - Services records
        - Stop records
        - Camera records
        - TrafficSignal records
        - Segments
        - Shapes
        """
        from rest_api.models import (Alert, Camera, HistoricSpeed, Segment,
                                     Services, Shape, Speed, Stop,
                                     TrafficSignal)

        # Find all shapes for this axis (e.g., "Eje Alameda_0", "Eje Alameda_1")
        shapes = Shape.objects.filter(name__startswith=f"{axis_name}_")
        shape_ids = list(shapes.values_list("id", flat=True))

        if not shape_ids:
            return {
                "shapes": 0,
                "segments": 0,
                "speeds": 0,
                "historic_speeds": 0,
                "alerts": 0,
                "services": 0,
                "stops": 0,
                "cameras": 0,
                "traffic_signals": 0,
            }

        # Get all segments for these shapes
        segments = Segment.objects.filter(shape_id__in=shape_ids)

        # Delete in order (due to foreign key constraints)
        # 1. Delete Speed records
        speeds_deleted, _ = Speed.objects.filter(segment__in=segments).delete()

        # 2. Delete HistoricSpeed records
        historic_deleted, _ = HistoricSpeed.objects.filter(
            segment__in=segments
        ).delete()

        # 3. Delete Alert records
        alerts_deleted, _ = Alert.objects.filter(segment__in=segments).delete()

        # 4. Delete Services records
        services_deleted, _ = Services.objects.filter(segment__in=segments).delete()

        # 5. Delete Stop records
        stops_deleted, _ = Stop.objects.filter(segment__in=segments).delete()

        # 6. Delete Camera records (note: field is segment_id, not segment)
        cameras_deleted, _ = Camera.objects.filter(segment_id__in=segments).delete()

        # 7. Collect related TrafficSignal ids before deleting segments.
        # Signals are linked from Segment via start_signal/end_signal.
        signal_ids = set(
            segments.exclude(start_signal__isnull=True).values_list(
                "start_signal_id", flat=True
            )
        )
        signal_ids.update(
            segments.exclude(end_signal__isnull=True).values_list(
                "end_signal_id", flat=True
            )
        )

        # 8. Delete Segments
        segments_deleted, _ = segments.delete()

        # 9. Delete orphan TrafficSignal records that belonged to removed segments.
        signals_deleted = 0
        if signal_ids:
            signals_deleted, _ = TrafficSignal.objects.filter(id__in=signal_ids).filter(
                segments_starting_here__isnull=True,
                segments_ending_here__isnull=True,
            ).delete()

        # 10. Delete Shapes
        shapes_deleted, _ = shapes.delete()

        return {
            "shapes": shapes_deleted,
            "segments": segments_deleted,
            "speeds": speeds_deleted,
            "historic_speeds": historic_deleted,
            "alerts": alerts_deleted,
            "services": services_deleted,
            "stops": stops_deleted,
            "cameras": cameras_deleted,
            "traffic_signals": signals_deleted,
        }


class TrafficSignalViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = TrafficSignalSerializer
    queryset = TrafficSignal.objects.all()

    def to_geojson(self, request, *args, **kwargs):
        """Return traffic signals used for segmentation as a GeoJSON FeatureCollection.

        Only includes signals that are referenced as start_signal or end_signal
        in at least one Segment.
        """
        from django.db.models import Q

        # Filter only signals used for segmentation
        signals = TrafficSignal.objects.filter(
            Q(segments_starting_here__isnull=False)
            | Q(segments_ending_here__isnull=False)
        ).distinct()

        features = []
        for signal in signals:
            features.append(
                Feature(
                    geometry=Point(coordinates=[signal.longitude, signal.latitude]),
                    properties={
                        "id": signal.id,
                        "osm_id": signal.osm_id,
                        "intersecting_ways": signal.intersecting_ways,
                    },
                )
            )
        return JsonResponse(FeatureCollection(features), safe=False)


class CameraViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    pagination_class = None
    serializer_class = CameraSerializer
    queryset = Camera.objects.all()


class ProcessAxisView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProcessAxisSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return JsonResponse({"error": serializer.errors}, status=400)

        axis_name = serializer.validated_data["axis_name"]
        distance_threshold = serializer.validated_data.get("distance_threshold", 500.0)

        try:
            call_command(
                "add_single_axis",
                axis_name,
                distance_threshold=distance_threshold,
            )
            return JsonResponse(
                {
                    "status": "success",
                    "message": f'Axis "{axis_name}" processed successfully',
                },
                status=200,
            )
        except Exception as e:
            return JsonResponse(
                {"error": str(e)},
                status=400,
            )
