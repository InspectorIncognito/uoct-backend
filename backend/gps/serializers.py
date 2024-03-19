from rest_framework import serializers
from gps.models import GPS


class GPSSerializer(serializers.ModelSerializer):
    class Meta:
        model = GPS
        fields = '__all__'
