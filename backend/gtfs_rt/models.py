from django.db import models
from django.utils import timezone


class GPSPulse(models.Model):
    route_id = models.CharField(max_length=64)
    direction_id = models.IntegerField()
    license_plate = models.CharField(max_length=24, default="NN")
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField(default=timezone.localtime)

    def __str__(self):
        return f"({self.latitude}, {self.longitude})"
