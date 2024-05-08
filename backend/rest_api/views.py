from rest_framework import viewsets
from django.http import JsonResponse
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from processors.models.shapes import shapes_to_geojson
from rest_api.models import Shape, Segment
from rest_api.serializers import ShapeSerializer, SegmentSerializer
from velocity.grid import GridManager
from velocity.gtfs import GTFSReader, GTFSManager


# Create your views here.
class GeoJSONViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Returns a GeoJSON with the latest data.
        # This includes the 500-meter-segmented-path with its corresponding velocities
        # TODO: Change placeholder with real information
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


class GridViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        grid_manager = GridManager()
        grid_manager.process()
        grid = grid_manager.get_grid()
        gtfs_manager = GTFSManager()
        print('GTFS LOADED')
        shapes_geojson = gtfs_manager.get_shape_geojson()
        print('GOT SHAPES')
        gtfs_manager.get_services_for_each_segment(shapes_geojson)
        return JsonResponse({'status': 'ok'})
