import json

from django.shortcuts import render
from rest_framework import viewsets
from django.http import JsonResponse
from rest_framework import generics
from rest_framework.permissions import AllowAny
from processors.models.shapes import shapes_to_geojson


# Create your views here.
class GeoJSONViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Returns a GeoJSON with the latest data.
        # This includes the 500-meter-segmented-path with its corresponding velocities
        # TODO: Change placeholder with real information
        shapes_json = shapes_to_geojson()

        return JsonResponse(shapes_json, safe=False)
