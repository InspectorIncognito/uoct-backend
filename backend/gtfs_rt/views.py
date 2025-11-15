from datetime import datetime, timedelta

from django.db.models import Case, CharField, F, Value, When
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.utils import timezone
from geojson import Feature, FeatureCollection, Point
from gtfs_rt.config import TIMEZONE
from gtfs_rt.models import GPSPulse
from gtfs_rt.serializers import GTFSRTSerializer
from gtfs_rt.utils import get_temporal_range, get_temporal_segment
from rest_api.util.shape import ShapeManager
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny


class GTFSRTViewSet(viewsets.ModelViewSet):
    permission_classes = [
        AllowAny,
    ]
    queryset = GPSPulse.objects.all().order_by("timestamp")
    serializer_class = GTFSRTSerializer

    def get_queryset(self):
        # By default, returns the last 15 minutes of GPS data.
        delta_time = timedelta(minutes=15)
        queryset = self.queryset
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            queryset = queryset.filter(
                timestamp__gte=start_date, timestamp__lte=end_date
            ).order_by("route_id")
        else:
            now = timezone.now()
            previous_15_minutes = now - delta_time
            previous_temporal_segment = get_temporal_segment(previous_15_minutes)
            start_date, end_date = get_temporal_range(previous_temporal_segment)
            print("temporal_range:", start_date, end_date)
            queryset = queryset.filter(
                timestamp__gte=start_date, timestamp__lte=end_date
            ).order_by("route_id")
        print("initial gps points:", queryset.count())
        queryset = queryset.annotate(service_id=F("route_id"))
        shape_manager = ShapeManager()
        all_services = shape_manager.get_all_services()
        print("all_services:", len(all_services))
        print(all_services)
        queryset = queryset.filter(service_id__in=all_services)
        print("filtered gps points:", queryset.count())
        return queryset

    @action(detail=False, methods=["get"])
    def to_geojson(self, request):
        queryset = self.get_queryset()
        print(f"queryset count: {queryset.count()}")
        geojson_data = []
        for gps in queryset:
            gps_geojson = Feature(
                geometry=Point(coordinates=[gps.longitude, gps.latitude]),
                properties={"service": gps.service_id},
            )
            geojson_data.append(gps_geojson)
        return JsonResponse(FeatureCollection(features=geojson_data), safe=False)
