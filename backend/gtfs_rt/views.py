from datetime import datetime, timedelta

from django.db.models import Max
from django.http import JsonResponse
from django.utils import timezone
from geojson import Feature, FeatureCollection, Point
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema

from gtfs_rt.models import GPSPulse
from gtfs_rt.serializers import GTFSRTSerializer
from gtfs_rt.utils import (
    get_allowed_service_routes,
    get_temporal_range,
    get_temporal_segment,
)


class GTFSRTViewSet(viewsets.ModelViewSet):
    permission_classes = [
        AllowAny,
    ]
    queryset = GPSPulse.objects.all().order_by("timestamp")
    serializer_class = GTFSRTSerializer

    @staticmethod
    def _is_truthy(value):
        return str(value).lower() in {"1", "true", "yes", "on"}

    def _get_last_minute_bounds(self):
        max_timestamp = GPSPulse.objects.aggregate(
            max_timestamp=Max("timestamp")
        )["max_timestamp"]
        if not max_timestamp:
            return None, None
        return max_timestamp - timedelta(minutes=1), max_timestamp

    def _get_allowed_service_routes(self):
        return get_allowed_service_routes()

    def get_queryset(self):
        # By default, returns the last 15 minutes of GPS data.
        delta_time = timedelta(minutes=15)
        queryset = self.queryset
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        last_minute = self._is_truthy(self.request.query_params.get("last_minute"))
        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            queryset = queryset.filter(
                timestamp__gte=start_date, timestamp__lte=end_date
            )
        elif last_minute:
            start_date, end_date = self._get_last_minute_bounds()
            if not start_date or not end_date:
                return GPSPulse.objects.none()
            queryset = queryset.filter(
                timestamp__gte=start_date, timestamp__lte=end_date
            )
        else:
            now = timezone.now()
            previous_15_minutes = now - delta_time
            previous_temporal_segment = get_temporal_segment(now)
            start_date, end_date = get_temporal_range(previous_temporal_segment)
            queryset = queryset.filter(
                timestamp__gte=start_date, timestamp__lte=end_date
            )
        allowed_service_routes = self._get_allowed_service_routes()
        queryset = queryset.filter(route_id__in=allowed_service_routes)
        return queryset.order_by("-timestamp")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="last_minute",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Si es true, devuelve solo los pulsos GPS del ultimo minuto "
                    "registrado en la base de datos."
                ),
            )
        ]
    )
    @action(detail=False, methods=["get"])
    def to_geojson(self, request):
        queryset = self.get_queryset().values(
            "longitude",
            "latitude",
            "route_id",
            "direction",
            "license_plate",
            "timestamp",
        )
        geojson_data = [
            Feature(
                geometry=Point(coordinates=[gps["longitude"], gps["latitude"]]),
                properties={
                    "service": gps["route_id"],
                    "direction": gps["direction"],
                    "license_plate": gps["license_plate"],
                    "timestamp": gps["timestamp"].isoformat(),
                },
            )
            for gps in queryset
        ]
        return JsonResponse(FeatureCollection(features=geojson_data), safe=False)
