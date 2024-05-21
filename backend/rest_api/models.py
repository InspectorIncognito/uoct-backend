from django.contrib.postgres.fields import ArrayField
from django.db import models
from shapely.geometry import LineString as shp_LineString
from geojson.geometry import LineString
from geojson.feature import Feature
from typing import Dict, List
from velocity.constants import DEG_PI, DEG_PI_HALF
from processors.geometry.point import Point


class Shape(models.Model):
    name = models.CharField(max_length=128)
    grid_min_lat = models.FloatField(default=DEG_PI_HALF)
    grid_max_lat = models.FloatField(default=-DEG_PI_HALF)
    grid_min_lon = models.FloatField(default=DEG_PI)
    grid_max_lon = models.FloatField(default=-DEG_PI)

    def get_segments(self):
        return Segment.objects.filter(shape=self).order_by('sequence')

    def add_segment(self, sequence: int, geometry: shp_LineString) -> None:
        points = list(geometry.coords)
        shape_data = {
            "shape": self,
            "sequence": sequence,
            "geometry": points
        }
        for point in points:
            self.grid_min_lat = min(self.grid_min_lat, point[1])
            self.grid_max_lat = max(self.grid_max_lat, point[1])
            self.grid_min_lon = min(self.grid_min_lon, point[0])
            self.grid_max_lon = max(self.grid_max_lon, point[0])

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

    def get_distance(self):
        total_distance = 0
        segments = self.get_segments()
        for segment in segments:
            coords = segment.geometry
            previous_point = None
            for coord in coords:
                current_point = Point(coord[0], coord[1])
                if previous_point is None:
                    previous_point = Point(coord[0], coord[1])
                    continue
                total_distance += previous_point.distance(current_point, algorithm='haversine')
        return int(total_distance)

    def __str__(self):
        return f"'{self.name}'"


class Segment(models.Model):
    shape = models.ForeignKey(Shape, on_delete=models.CASCADE)
    sequence = models.IntegerField(blank=False, null=False)
    geometry = ArrayField(ArrayField(models.FloatField()), blank=False, null=False)

    def __str__(self):
        return f"Segment {self.sequence} of Shape {self.shape}"

    def to_geojson(self):
        properties = {
            "shape_id": self.shape.pk,
            "sequence": self.sequence,
        }
        speed = Speed.objects.filter(segment=self).order_by('timestamp').first()
        if speed is not None:
            properties["speed"] = speed.speed
        services = Services.objects.filter(segment=self).first()
        if services is not None:
            properties["services"] = services.services
        feature = Feature(
            geometry=LineString(coordinates=self.geometry),
            properties=properties
        )
        return feature


class Speed(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    speed = models.FloatField(blank=False, null=False)
    timestamp = models.DateTimeField(auto_now_add=True)


class Services(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    services = ArrayField(models.CharField(max_length=124), blank=False, null=False)


class GTFSShape(models.Model):
    shape_id = models.CharField(max_length=124)
    geometry = ArrayField(ArrayField(models.FloatField()), blank=False, null=False)
    direction = models.IntegerField(blank=False, null=False)

    def to_geojson(self):
        return Feature(
            geometry=LineString(coordinates=self.geometry),
            properties={
                'shape_id': str(self.shape_id),
                'direction': str(self.direction)
            }
        )
