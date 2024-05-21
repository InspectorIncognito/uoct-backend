from rest_framework import routers
from gtfs_rt.views import GTFSRTViewSet
from django.urls import path, include

router = routers.SimpleRouter()
router.register(r'pulses', GTFSRTViewSet)

urlpatterns = [
    path('', include((router.urls, 'gtfs_rt'), namespace='gtfs_rt'))
]
