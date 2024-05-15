from rest_framework import serializers
from gtfs_rt.models import GPSPulse


class GTFSRTSerializer(serializers.ModelSerializer):
    class Meta:
        model = GPSPulse
        fields = '__all__'
