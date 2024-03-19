from django.shortcuts import render
from gps.models import GPS
from rest_framework.viewsets import ViewSet
from rest_framework import permissions, viewsets, mixins
from gps.serializers import GPSSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import datetime
from django.http import JsonResponse


class GPSViewSet(viewsets.ModelViewSet, mixins.CreateModelMixin, mixins.ListModelMixin):
    serializer_class = GPSSerializer
    permission_classes = [permissions.AllowAny]
    queryset = GPS.objects.all()

    def filter_queryset(self, queryset):
        start = self.request.GET.get('start', None)
        end = self.request.GET.get('end', None)
        if start and end:
            start_date = datetime.strptime(start, '%d/%m/%Y %H:%M:%S')
            end_date = datetime.strptime(end, '%d/%m/%Y %H:%M:%S')
            queryset = queryset.filter(datetime__gte=start_date, datetime__lte=end_date)
            return super().filter_queryset(queryset)
        return super().filter_queryset(queryset)

    @action(methods=['GET'], detail=False)
    def to_geojson(self, *args, **kwargs):
        data = self.queryset.all()
        response = {
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [p.lon, p.lat]
                },
                'properties': {
                    'trip_id': p.trip_id
                }
            } for p in data]
        }
        return JsonResponse(response)
