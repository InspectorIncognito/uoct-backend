from django.urls import include, path
from rest_framework import routers
from gps import views

router = routers.DefaultRouter()
router.register(r'create', views.GPSViewSet, basename='gps-create')

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('', include(router.urls)),
]
