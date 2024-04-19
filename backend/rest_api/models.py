from django.contrib.postgres.fields import ArrayField
from django.db import models
from geojson.geometry import LineString
from geojson.feature import Feature


class Shape(models.Model):
    name = models.CharField(max_length=128)

    def to_geojson(self):
        segments = Segment.objects.filter(shape=self).all()
        print(segments)
        if len(segments) == 0:
            return {}
        geojson = [segment.to_geojson() for segment in segments]
        return geojson

    def __str__(self):
        return f"'{self.name}'"


class Segment(models.Model):
    shape = models.ForeignKey(Shape, on_delete=models.CASCADE)
    sequence = models.IntegerField(blank=False, null=False)
    geometry = ArrayField(ArrayField(models.FloatField()), blank=False, null=False)

    def __str__(self):
        return f"Segment {self.sequence} of Shape {self.shape}"

    def to_geojson(self):
        feature = Feature(
            geometry=LineString(coordinates=self.geometry),
            properties={
                "shape_id": self.shape.pk,
                "sequence": self.sequence
            }
        )
        return feature
