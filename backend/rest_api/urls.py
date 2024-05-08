from django.urls import include, path
from rest_api.views import GeoJSONViewSet, ShapeViewSet, SegmentViewSet, GridViewSet

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('mapData/', GeoJSONViewSet.as_view(), name='mapData'),
    path('shape/', ShapeViewSet.as_view({"get": 'list'}), name="shape"),
    path('shape/<int:shape_pk>/segments/', SegmentViewSet.as_view({"get": 'list'}), name="segments" ),
    path('debug/grid/', GridViewSet.as_view(), name="segments"),
]
