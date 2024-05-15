from rest_framework import viewsets, mixins
from gtfs_rt.models import GPSPulse
from gtfs_rt.serializers import GTFSRTSerializer
from rest_framework.permissions import AllowAny


class GTFSRTViewSet(viewsets.ModelViewSet, mixins.ListModelMixin):
    permission_classes = [AllowAny,]
    queryset = GPSPulse.objects.all()
    serializer_class = GTFSRTSerializer
