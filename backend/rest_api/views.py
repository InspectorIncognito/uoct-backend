from datetime import datetime

from django.utils import timezone
from geojson import FeatureCollection
from rest_framework import viewsets
from django.http import JsonResponse, HttpResponse
from rest_framework import generics
from rest_framework.permissions import AllowAny
from processors.models.shapes import shapes_to_geojson
from rest_api.models import Shape, Segment, GTFSShape, Services, Speed
from rest_api.serializers import ShapeSerializer, SegmentSerializer, GTFSShapeSerializer, ServicesSerializer, \
    SpeedSerializer
from gtfs_rt.processors.speed import calculate_speed
import csv
import pandas as pd

# Create your views here.
class GeoJSONViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Returns a GeoJSON with the latest data.
        # This includes the 500-meter-segmented-path with its corresponding velocities
        shapes_json = shapes_to_geojson()

        return JsonResponse(shapes_json, safe=False)


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


class SpeedViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = SpeedSerializer
    queryset = Speed.objects.all().order_by('-timestamp')

    def to_csv(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        start_date = request.query_params.get('start_date', None)
        if start_date is not None:
            start_date = datetime.strptime(start_date, '%Y-%d-%mT%H:%M:%S')
            start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
            queryset = queryset.filter(timestamp__gte=start_date)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="segment_speeds.csv"'
        serializer = self.get_serializer(queryset, many=True)
        fieldnames = ['shape', 'sequence', 'speed', 'timestamp', 'day_type']
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        for obj in serializer.data:
            writer.writerow(obj)

        return response


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
