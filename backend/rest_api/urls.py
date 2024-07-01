from django.urls import include, path
from rest_api.views import GeoJSONViewSet, ShapeViewSet, SegmentViewSet, GridViewSet, GTFSShapeViewSet, ServicesViewSet, \
    SpeedViewSet, HistoricSpeedViewSet, GTFSStopsViewSet, StopViewSet

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('mapData/', GeoJSONViewSet.as_view(), name='mapData'),
    path('shape/', ShapeViewSet.as_view({"get": 'list'}), name="shape"),
    path('services/', ServicesViewSet.as_view({"get": 'list'}), name="services"),
    path('speeds/', SpeedViewSet.as_view({"get": 'list'}), name="speeds"),
    path('historicSpeeds/', HistoricSpeedViewSet.as_view({"get": "list"}), name="historicSpeeds"),
    path('historicSpeeds/to_csv/', HistoricSpeedViewSet.as_view({"get": "to_csv"}), name="historicSpeeds-to_csv"),
    path('stops/', StopViewSet.as_view({"get": "list"}), name="stops"),
    path('stops/geojson/', StopViewSet.as_view({"get": "to_geojson"}), name="stops"),
    path('gtfs_stops/', GTFSStopsViewSet.as_view(), name="stopsGeoJson"),
    path('speeds/to_csv/', SpeedViewSet.as_view({"get": "to_csv"}), name="shape-to_csv"),
    path('gtfs_shape/', GTFSShapeViewSet.as_view({"get": 'list'}), name="gtfs_shape"),
    path('gtfs_shape/custom/', GTFSShapeViewSet.as_view({"get": 'geojson'}), name="segments_geojson"),
    path('shape/<int:shape_pk>/segments/', SegmentViewSet.as_view({"get": 'list'}), name="segments"),
    path('debug/speed/', GridViewSet.as_view(), name="segments"),
]
