from django.db import models


class GPS(models.Model):
    lat = models.FloatField(null=False, blank=False)
    lon = models.FloatField(null=False, blank=False)
    trip_id = models.CharField(max_length=24, null=False, blank=False)
    datetime = models.DateTimeField(null=False, blank=False)
