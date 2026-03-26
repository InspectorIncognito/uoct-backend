from django.urls import path
from rest_api.views import (
    AlertViewSet,
    AxlesViewSet,
    CameraViewSet,
    GeoJSONViewSet,
    GridViewSet,
    GTFSShapeViewSet,
    GTFSStopsViewSet,
    HistoricSpeedViewSet,
    ProcessAxisView,
    SegmentViewSet,
    ServicesViewSet,
    ShapeViewSet,
    SpeedViewSet,
    StopViewSet,
    TestView,
    TrafficSignalViewSet,
)
from rest_framework.routers import DefaultRouter

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
router = DefaultRouter()
router.register(r"axles", AxlesViewSet, basename="axles")
urlpatterns = [
    path("mapData/", GeoJSONViewSet.as_view(), name="mapData"),
    path("shape/", ShapeViewSet.as_view({"get": "list"}), name="shape"),
    path("services/", ServicesViewSet.as_view({"get": "list"}), name="services"),
    path("speeds/", SpeedViewSet.as_view({"get": "list"}), name="speeds"),
    path(
        "speeds/to_csv/", SpeedViewSet.as_view({"get": "to_csv"}), name="shape-to_csv"
    ),
    path(
        "speeds/to_csv_gz/",
        SpeedViewSet.as_view({"get": "to_csv_gz"}),
        name="shape-to_csv-gz",
    ),
    path(
        "speeds/to_csv_local/",
        SpeedViewSet.as_view({"get": "to_csv_local"}),
        name="shape-to_csv-local",
    ),
    path(
        "speeds/to_csv_local_gz/",
        SpeedViewSet.as_view({"get": "to_csv_local_gz"}),
        name="shape-to_csv-local-gz",
    ),
    path("alerts/", AlertViewSet.as_view({"get": "list"}), name="alerts"),
    path(
        "alerts/active/", AlertViewSet.as_view({"get": "active"}), name="active-alerts"
    ),
    path(
        "historicSpeeds/",
        HistoricSpeedViewSet.as_view({"get": "list"}),
        name="historicSpeeds",
    ),
    path(
        "historicSpeeds/to_csv/",
        HistoricSpeedViewSet.as_view({"get": "to_csv"}),
        name="historicSpeeds-to_csv",
    ),
    path(
        "historicSpeeds/to_csv_gz/",
        HistoricSpeedViewSet.as_view({"get": "to_csv_gz"}),
        name="historicSpeeds-to_csv-gz",
    ),
    path(
        "historicSpeeds/to_csv_local/",
        HistoricSpeedViewSet.as_view({"get": "to_csv_local"}),
        name="historicSpeeds-to_csv-local",
    ),
    path(
        "historicSpeeds/to_csv_local_gz/",
        HistoricSpeedViewSet.as_view({"get": "to_csv_local_gz"}),
        name="historicSpeeds-to_csv-local-gz",
    ),
    path("stops/", StopViewSet.as_view({"get": "list"}), name="stops"),
    path("stops/geojson/", StopViewSet.as_view({"get": "to_geojson"}), name="stops"),
    path("gtfs_stops/", GTFSStopsViewSet.as_view(), name="stopsGeoJson"),
    path("gtfs_shape/", GTFSShapeViewSet.as_view({"get": "list"}), name="gtfs_shape"),
    path(
        "gtfs_shape/custom/",
        GTFSShapeViewSet.as_view({"get": "geojson"}),
        name="segments_geojson",
    ),
    path(
        "shape/<int:shape_pk>/segments/",
        SegmentViewSet.as_view({"get": "list"}),
        name="segments",
    ),
    path("debug/speed/", GridViewSet.as_view(), name="segments"),
    path("debug/test/", TestView.as_view(), name="debug-test"),
    path(
        "traffic_signal/",
        TrafficSignalViewSet.as_view({"get": "list"}),
        name="traffic_signal",
    ),
    path(
        "traffic_signal/geojson/",
        TrafficSignalViewSet.as_view({"get": "to_geojson"}),
        name="traffic_signal_geojson",
    ),
    path("camera/", CameraViewSet.as_view({"get": "list"}), name="camera"),
    path("axles/process/", ProcessAxisView.as_view(), name="process-axis"),
] + router.urls
