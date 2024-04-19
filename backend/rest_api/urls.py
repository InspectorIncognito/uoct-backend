from django.urls import include, path
from rest_api.views import GeoJSONViewSet, ShapeViewSet

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('mapData/', GeoJSONViewSet.as_view(), name='mapData'),
    path('shapes/', ShapeViewSet.as_view({"get": 'list'}), name="shape")
]
