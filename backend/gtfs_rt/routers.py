from django.urls import include, path
from gtfs_rt.views import GTFSRTViewSet
from rest_framework import routers

router = routers.SimpleRouter()
router.register(r"pulses", GTFSRTViewSet, basename="pulses")

urlpatterns = [
    path("", include(router.urls)),
]
