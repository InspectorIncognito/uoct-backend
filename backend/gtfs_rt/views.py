from datetime import datetime, timedelta
import pytz
from rest_framework.response import Response
from rest_framework import viewsets, mixins
from gtfs_rt.models import GPSPulse
from gtfs_rt.serializers import GTFSRTSerializer
from rest_framework.permissions import AllowAny
from gtfs_rt.config import SANTIAGO_TIMEZONE
from rest_framework.views import APIView


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
            start_date = SANTIAGO_TIMEZONE.localize(datetime.strptime(start_date, '%Y-%m-%dT%H:%M:%SZ'))
            end_date = SANTIAGO_TIMEZONE.localize(datetime.strptime(end_date, '%Y-%m-%dT%H:%M:%SZ'))
            queryset = queryset.filter(timestamp__gte=start_date, timestamp__lte=end_date).order_by("route_id")
        else:
            end_datetime = datetime.now().astimezone(SANTIAGO_TIMEZONE)
            start_datetime = end_datetime - delta_time
            queryset = queryset.filter(timestamp__gte=start_datetime, timestamp__lte=end_datetime).order_by("route_id")
        return queryset
