from datetime import datetime

from django.utils import timezone
from rest_framework import viewsets, mixins
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from rest_framework import generics
from rest_framework.permissions import AllowAny
from processors.models.shapes import shapes_to_geojson
from rest_api.models import Shape, Segment, GTFSShape, Services, Speed, HistoricSpeed, Stop, AlertThreshold, Alert
from rest_api.serializers import ShapeSerializer, SegmentSerializer, GTFSShapeSerializer, ServicesSerializer, \
    SpeedSerializer, HistoricSpeedSerializer, StopSerializer, AlertThresholdSerializer, AlertSerializer
from gtfs_rt.processors.speed import calculate_speed
import csv
from geojson import FeatureCollection, Feature, Point

from velocity.gtfs import GTFSManager
from rest_framework.response import Response


# Create your views here.
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
            stop_lat = stop['stop_lat']
            stop_lon = stop['stop_lon']
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
        return Segment.objects.filter(shape__id=self.kwargs['shape_pk']).order_by('sequence')


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

    def get_queryset(self):
        queryset = self.queryset
        start_time = self.request.query_params.get('startTime')
        end_time = self.request.query_params.get('endTime')
        month = self.request.query_params.get("month")
        day_type = self.request.query_params.get("dayType")
        temporal_segment = self.request.query_params.get("temporalSegment")

        if month is not None:
            month = int(month)
            year = timezone.localtime().year
            queryset = queryset.filter(timestamp__year=year, timestamp__month=month)
        if start_time is not None and end_time is not None:
            start_time = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
            start_time = timezone.make_aware(start_time, timezone.get_current_timezone())
            end_time = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ")
            end_time = timezone.make_aware(end_time, timezone.get_current_timezone())
            queryset = queryset.filter(timestamp__gte=start_time, timestamp__lte=end_time)

        if day_type is not None:
            queryset = queryset.filter(day_type=day_type)
        if temporal_segment is not None:
            queryset = queryset.filter(temporal_segment=temporal_segment)
        queryset = queryset.order_by("segment", "temporal_segment")
        return queryset

    @staticmethod
    def csv_generator(queryset, fieldnames_dict):
        yield ','.join(list(fieldnames_dict.values())) + '\n'
        for obj in queryset:
            fieldnames = list(fieldnames_dict.keys())
            row = [str(obj[field]) for field in fieldnames]
            yield ','.join(row) + '\n'


class SpeedViewSet(GenericSpeedViewSet):
    serializer_class = SpeedSerializer
    queryset = Speed.objects.all().order_by('-temporal_segment')

    def to_csv(self, request, *args, **kwargs):
        queryset = self.get_queryset().values(
            'segment__shape',
            'segment__sequence',
            'temporal_segment',
            'day_type',
            'distance',
            'time_secs'
        )
        start_date = request.query_params.get('start_date', None)
        if start_date is not None:
            start_date = datetime.strptime(start_date, '%Y-%d-%mT%H:%M:%S')
            start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
            queryset = queryset.filter(timestamp__gte=start_date)

        fieldnames_dict = dict(
            segment__shape='shape',
            segment__sequence='sequence',
            temporal_segment='temporal_segment',
            day_type='day_type',
            distance='distance',
            time_secs='time_secs'
        )
        response = StreamingHttpResponse(self.csv_generator(queryset, fieldnames_dict), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="segment_speeds.csv"'

        return response


class HistoricSpeedViewSet(GenericSpeedViewSet):
    serializer_class = HistoricSpeedSerializer
    queryset = HistoricSpeed.objects.all().order_by("segment")

    def to_csv(self, request, *args, **kwargs):
        queryset = self.get_queryset().values(
            'segment__shape',
            'segment__sequence',
            'temporal_segment',
            'day_type',
            'speed'
        )
        fieldnames_dict = dict(
            segment__shape='shape',
            segment__sequence='sequence',
            temporal_segment='temporal_segment',
            day_type='day_type',
            speed='speed'
        )
        response = StreamingHttpResponse(self.csv_generator(queryset, fieldnames_dict), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="segment_speeds.csv"'
        return response


class AlertViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = AlertSerializer
    queryset = Alert.objects.all()


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
                        "segment_pk": stop.segment.sequence
                    }
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
        direction = query_params.get('direction')
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


class AlertThresholdViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.UpdateModelMixin,
                            mixins.CreateModelMixin, mixins.RetrieveModelMixin):
    permission_classes = [AllowAny, ]
    queryset = AlertThreshold.objects.all()
    serializer_class = AlertThresholdSerializer
