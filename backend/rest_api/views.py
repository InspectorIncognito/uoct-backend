import json
from datetime import datetime

from django.db.models import ExpressionWrapper, F, FloatField
from django.db.models.functions import Round
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from geojson import Feature, FeatureCollection, Point
from gtfs_rt.processors.speed import (
    calculate_speed,
    calculate_speed_parallel,
    calculate_speed_serial,
)
from gtfs_rt.utils import get_last_temporal_range, get_previous_month
from processors.models.shapes import shapes_to_geojson
from rest_framework import generics, mixins, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import AllowAny
from velocity.grid import GridManager
from velocity.gtfs import GTFSManager

from rest_api.models import (
    Alert,
    AlertThreshold,
    Axles,
    Camera,
    GTFSShape,
    HistoricSpeed,
    Segment,
    Services,
    Shape,
    Speed,
    Stop,
    TrafficSignal,
)
from rest_api.serializers import (
    AlertSerializer,
    AlertThresholdSerializer,
    AxlesSerializer,
    CameraSerializer,
    GTFSShapeSerializer,
    HistoricSpeedSerializer,
    SegmentSerializer,
    ServicesSerializer,
    ShapeSerializer,
    SpeedSerializer,
    StopSerializer,
    TrafficSignalSerializer,
)


class TestView(generics.GenericAPIView):
    permission_classes = [AllowAny]

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

    def get(self, request):
        # Returns a GeoJSON with the latest data.
        # This includes the 500-meter-segmented-path with its corresponding velocities
        shapes_json = shapes_to_geojson()

        return JsonResponse(shapes_json, safe=False)


class GTFSStopsViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]

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
    def csv_generator(queryset, fieldnames_dict):
        yield ",".join(list(fieldnames_dict.values())) + "\n"
        for obj in queryset:
            fieldnames = list(fieldnames_dict.keys())
            row = []
            for field in fieldnames:
                row.append(str(obj[field]))
            yield ",".join(row) + "\n"


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
        query_params = request.query_params
        queryset = self.get_queryset().values(
            "segment__shape",
            "segment__sequence",
            "temporal_segment",
            "day_type",
            "distance",
            "time_secs",
            "timestamp",
        )
        if len(query_params) == 0:
            start_time, end_time = get_last_temporal_range()
            queryset = queryset.filter(
                timestamp__gte=start_time,
                timestamp__lte=end_time,
            )
        fieldnames_dict = dict(
            segment__shape="shape",
            segment__sequence="sequence",
            temporal_segment="temporal_segment",
            day_type="day_type",
            distance="distance",
            time_secs="time_secs",
            timestamp="timestamp",
        )
        response = StreamingHttpResponse(
            self.csv_generator(queryset, fieldnames_dict), content_type="text/csv"
        )
        response["Content-Disposition"] = 'attachment; filename="segment_speeds.csv"'

        return response


class HistoricSpeedViewSet(GenericSpeedViewSet):
    serializer_class = HistoricSpeedSerializer
    queryset = HistoricSpeed.objects.all().order_by("segment")

    def to_csv(self, request, *args, **kwargs):
        queryset = self.get_queryset().values(
            "segment__shape",
            "segment__sequence",
            "temporal_segment",
            "day_type",
            "speed",
        )
        if len(request.query_params) == 0:
            previous_month = get_previous_month()
            queryset = queryset.filter(timestamp__month=previous_month)
        fieldnames_dict = dict(
            segment__shape="shape",
            segment__sequence="sequence",
            temporal_segment="temporal_segment",
            day_type="day_type",
            speed="speed",
        )
        response = StreamingHttpResponse(
            self.csv_generator(queryset, fieldnames_dict), content_type="text/csv"
        )
        response["Content-Disposition"] = 'attachment; filename="segment_speeds.csv"'
        return response


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

    def get(self, request):
        speed_records = calculate_speed()
        return JsonResponse({"speeds": speed_records})


class ParallelSpeedViewSet(generics.GenericAPIView):
    """
    Endpoint for speed calculation using parallel HMM map matching.
    Useful for performance testing and comparison.

    Query params:
        - workers: Number of workers (default: 8)
        - include_speeds: If 'true', include speed records sample (default: false)
        - sample_size: Number of speed records to include if include_speeds=true (default: 10)
    """

    permission_classes = [AllowAny]

    def get(self, request):
        workers = int(request.GET.get("workers", 8))
        include_speeds = request.GET.get("include_speeds", "false").lower() == "true"
        sample_size = int(request.GET.get("sample_size", 10))

        speed_records, timing_metrics = calculate_speed_parallel(workers=workers)

        response_data = {"timing": timing_metrics, "record_count": len(speed_records)}

        if include_speeds:
            # Return only a sample to avoid huge responses
            response_data["speeds_sample"] = speed_records[:sample_size]

        return JsonResponse(response_data)


class SerialSpeedViewSet(generics.GenericAPIView):
    """
    Endpoint for speed calculation using serial (non-parallel) HMM map matching.
    Useful for performance testing and comparison.

    Query params:
        - include_speeds: If 'true', include speed records sample (default: false)
        - sample_size: Number of speed records to include if include_speeds=true (default: 10)
    """

    permission_classes = [AllowAny]

    def get(self, request):
        include_speeds = request.GET.get("include_speeds", "false").lower() == "true"
        sample_size = int(request.GET.get("sample_size", 10))

        speed_records, timing_metrics = calculate_speed_serial()

        response_data = {"timing": timing_metrics, "record_count": len(speed_records)}

        if include_speeds:
            # Return only a sample to avoid huge responses
            response_data["speeds_sample"] = speed_records[:sample_size]

        return JsonResponse(response_data)


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


class TrafficSignalViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = TrafficSignalSerializer
    queryset = TrafficSignal.objects.all()


class CameraViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    pagination_class = None
    serializer_class = CameraSerializer
    queryset = Camera.objects.all()
