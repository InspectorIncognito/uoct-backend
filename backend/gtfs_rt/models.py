from django.db import models


class GPSPulse(models.Model):
    route_id = models.CharField(max_length=64)
    direction_id = models.IntegerField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField()
