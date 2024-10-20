from datetime import datetime, timedelta

from django.http import JsonResponse
from rest_framework import viewsets
from gtfs_rt.models import GPSPulse
from gtfs_rt.serializers import GTFSRTSerializer
from rest_framework.permissions import AllowAny
from gtfs_rt.config import TIMEZONE
from django.utils import timezone

from gtfs_rt.utils import get_temporal_segment, get_temporal_range
from geojson import FeatureCollection, Feature, Point

from rest_api.util.shape import ShapeManager
from django.db.models.functions import Concat
from django.db.models import F, Value, CharField, Case, When


class GTFSRTViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny, ]
    queryset = GPSPulse.objects.all().order_by('timestamp')
    serializer_class = GTFSRTSerializer

    def get_queryset(self):
        # By default, returns the last 15 minutes of GPS data.
        delta_time = timedelta(minutes=15)
        queryset = self.queryset
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%dT%H:%M:%SZ').astimezone(TIMEZONE)
            end_date = datetime.strptime(end_date, '%Y-%m-%dT%H:%M:%SZ').astimezone(TIMEZONE)
            queryset = queryset.filter(timestamp__gte=start_date, timestamp__lte=end_date).order_by("route_id")
        else:
            now = timezone.localtime()
            previous_15_minutes = now - delta_time
            previous_temporal_segment = get_temporal_segment(previous_15_minutes)
            start_date, end_date = get_temporal_range(previous_temporal_segment)
            print("temporal_range:", start_date, end_date)
            queryset = queryset.filter(timestamp__gte=start_date, timestamp__lte=end_date).order_by("route_id")
        print("initial gps points:", queryset.count())
        queryset = queryset.annotate(
            service_id=Concat(
                F('route_id'),
                Case(
                    When(direction_id=0, then=Value('I')),
                    When(direction_id=1, then=Value('R')),
                    output_field=CharField()
                ),
                output_field=CharField()
            ))
        shape_manager = ShapeManager()
        all_services = shape_manager.get_all_services()
        queryset = queryset.filter(service_id__in=all_services)
        return queryset

    def to_geojson(self, request):
        shape_manager = ShapeManager()
        all_services = list(shape_manager.get_all_services())

        #queryset = (self.get_queryset()
        #            .values('route_id', 'latitude', 'longitude')
        #            .annotate(service=Concat(F('route_id'), Value("I") if F('direction') else Value("R"),
        #                                     output_field=CharField()))
        #            .order_by('route_id')
        #            )
        #queryset = queryset.filter(service__in=all_services)
        queryset = self.get_queryset()
        print(queryset.count())
        geojson_data = []
        for gps in queryset:
            gps_geojson = Feature(geometry=Point(coordinates=[gps.longitude, gps.latitude]),
                                  properties={'service': gps.service_id})
            geojson_data.append(gps_geojson)
        return JsonResponse(FeatureCollection(features=geojson_data), safe=False)
