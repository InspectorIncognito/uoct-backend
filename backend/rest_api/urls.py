from django.urls import include, path
from rest_api.views import GeoJSONViewSet, ShapeViewSet, SegmentViewSet, GridViewSet, GTFSShapeViewSet

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('mapData/', GeoJSONViewSet.as_view(), name='mapData'),
    path('shape/', ShapeViewSet.as_view({"get": 'list'}), name="shape"),
    path('gtfs_shape/', GTFSShapeViewSet.as_view({"get": 'list'}), name="shape"),
    path('gtfs_shape/custom/', GTFSShapeViewSet.as_view({"get": 'geojson'}), name="segments"),
    path('shape/<int:shape_pk>/segments/', SegmentViewSet.as_view({"get": 'list'}), name="segments"),
    path('debug/grid/', GridViewSet.as_view(), name="segments"),
]
