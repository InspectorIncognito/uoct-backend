from django.urls import include, path
from rest_api.views import GeoJSONViewSet, ShapeViewSet, SegmentViewSet, GridViewSet, GTFSShapeViewSet, ServicesViewSet, \
    SpeedViewSet

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('mapData/', GeoJSONViewSet.as_view(), name='mapData'),
    path('shape/', ShapeViewSet.as_view({"get": 'list'}), name="shape"),
    path('services/', ServicesViewSet.as_view({"get": 'list'}), name="services"),
    path('speeds/', SpeedViewSet.as_view({"get": 'list'}), name="speeds"),
    path('gtfs_shape/', GTFSShapeViewSet.as_view({"get": 'list'}), name="gtfs_shape"),
    path('gtfs_shape/custom/', GTFSShapeViewSet.as_view({"get": 'geojson'}), name="segments_geojson"),
    path('shape/<int:shape_pk>/segments/', SegmentViewSet.as_view({"get": 'list'}), name="segments"),
    path('debug/speed/', GridViewSet.as_view(), name="segments"),
]
