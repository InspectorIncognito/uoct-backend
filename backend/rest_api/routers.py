from django.urls import path, include
from rest_framework import routers
from rest_api.views import AlertThresholdViewSet

router = routers.SimpleRouter()
router.register(r'', AlertThresholdViewSet)

urlpatterns = [
    path(r'alert-threshold/', include((router.urls, 'rest_api'), namespace='alert-threshold')),
]
