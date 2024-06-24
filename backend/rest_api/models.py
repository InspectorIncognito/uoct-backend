from django.contrib.postgres.fields import ArrayField
from django.db import models
from shapely.geometry import LineString as shp_LineString
from geojson.geometry import LineString
from geojson.feature import Feature
from velocity.constants import DEG_PI, DEG_PI_HALF
from processors.geometry.point import Point
from django.utils import timezone
from rest_api.vars import SPEED_COLOR_RANGES


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
            distance = segment.get_distance()
            total_distance += distance
        return int(total_distance)

    def __str__(self):
        return f"'{self.name}'"


class Segment(models.Model):
    shape = models.ForeignKey(Shape, on_delete=models.CASCADE)
    sequence = models.IntegerField(blank=False, null=False)
    geometry = ArrayField(ArrayField(models.FloatField()), blank=False, null=False)

    def __str__(self):
        return f"Segment {self.sequence} of Shape {self.shape}"

    def get_distance(self):
        accum_distance = 0
        previous_point = Point(latitude=self.geometry[0][1], longitude=self.geometry[0][0])
        for point in self.geometry[1:]:
            current_point = Point(latitude=point[1], longitude=point[0])
            distance = current_point.distance(previous_point, algorithm='haversine')
            accum_distance += distance
            previous_point = current_point
        return accum_distance

    def to_geojson(self):
        properties = {
            "shape_id": self.shape.pk,
            "sequence": self.sequence,
        }
        speed: Speed = Speed.objects.filter(segment=self).order_by('-timestamp').first()
        if speed is not None:
            properties["speed"] = str(speed.speed)
            properties["color"] = speed.assign_color()
            try:
                historic_speed = HistoricSpeed.objects.get(segment=self, day_type=speed.day_type,
                                                           temporal_segment=speed.temporal_segment)
            except HistoricSpeed.DoesNotExist:
                properties["historic_speed"] = "Sin registro"
            else:
                properties["historic_speed"] = historic_speed.speed
        else:
            properties["speed"] = "Sin registro"
            properties["color"] = "#DDDDDD"
        services = Services.objects.filter(segment=self).first()
        if services is not None:
            properties["services"] = services.services
        line = shp_LineString(coordinates=self.geometry)
        line = line.simplify(tolerance=0.00001)
        feature = Feature(
            geometry=LineString(coordinates=list(line.coords)),
            properties=properties
        )
        return feature


class Stop(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    stop_id = models.CharField(max_length=128)
    latitude = models.FloatField()
    longitude = models.FloatField()


class Speed(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    speed = models.FloatField(blank=False, null=False)
    timestamp = models.DateTimeField(default=timezone.localtime)
    day_type = models.CharField(max_length=1, blank=False, null=False, default="L")
    temporal_segment = models.IntegerField(blank=False, null=False, default=0)

    def assign_color(self):
        for min_speed, max_speed, color in SPEED_COLOR_RANGES:
            if min_speed <= self.speed <= max_speed:
                return color
        return "#000000"


class HistoricSpeed(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    speed = models.FloatField(blank=False, null=False)
    day_type = models.CharField(max_length=1, blank=False, null=False, default="L")
    temporal_segment = models.IntegerField(blank=False, null=False, default=0)
    timestamp = models.DateTimeField(default=timezone.localtime)


# TODO: Create alert
class Alert(models.Model):
    timestamp = models.DateTimeField()
    voted_positive = models.IntegerField()
    voted_negative = models.IntegerField()
    detected_speed = models.ForeignKey(Speed, on_delete=models.CASCADE)
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)


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
