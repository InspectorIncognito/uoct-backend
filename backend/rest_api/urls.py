from django.urls import include, path
from rest_api.views import GeoJSONViewSet

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('mapData/', GeoJSONViewSet.as_view(), name='mapData'),
]
