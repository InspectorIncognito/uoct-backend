from django.contrib.postgres.fields import ArrayField
from django.db import models
from shapely.geometry import LineString as shp_LineString
from geojson.geometry import LineString
from geojson.feature import Feature
from typing import Dict, List
from velocity.constants import DEG_PI, DEG_PI_HALF


class Shape(models.Model):
    name = models.CharField(max_length=128)
    grid_min_lat = models.FloatField(default=DEG_PI_HALF)
    grid_max_lat = models.FloatField(default=-DEG_PI_HALF)
    grid_min_lon = models.FloatField(default=DEG_PI)
    grid_max_lon = models.FloatField(default=-DEG_PI)

    def get_segments(self):
        return Segment.objects.filter(shape=self)

    def add_segment(self, sequence: int, geometry: shp_LineString) -> None:
        points = list(geometry.coords)
        shape_data = {
            "shape": self,
            "sequence": sequence,
            "geometry": points
        }
        for point in points:
            self.grid_min_lat = min(self.grid_min_lat, point[0])
            self.grid_max_lat = max(self.grid_max_lat, point[0])
            self.grid_min_lon = min(self.grid_min_lon, point[1])
            self.grid_max_lon = max(self.grid_max_lon, point[1])

        Segment.objects.create(**shape_data)
        self.save()

    def get_bbox(self):
        return [self.grid_min_lon, self.grid_min_lat, self.grid_max_lon, self.grid_max_lat]

    def to_geojson(self):
        segments = Segment.objects.filter(shape=self).all()
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
