import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from shapely.geometry import LineString as shp_LineString
from geojson.geometry import LineString
from geojson.feature import Feature
from velocity.constants import DEG_PI, DEG_PI_HALF
from processors.geometry.point import Point
from django.utils import timezone
from rest_api.vars import SPEED_COLOR_RANGES
from gtfs_rt.utils import get_temporal_segment, get_day_type


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
    segment_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
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

    def to_geojson(self, use_temporal_segment=True):
        properties = {
            "shape_id": self.shape.pk,
            "sequence": self.sequence,
        }
        now = timezone.localtime()
        temporal_segment = get_temporal_segment(now) - 1
        day_type = get_day_type(now)
        speed_query = Speed.objects.filter(segment=self)
        if use_temporal_segment:
            speed = speed_query.filter(segment=self, temporal_segment=temporal_segment).first()
        else:
            speed: Speed = speed_query.order_by('-timestamp').first()
        if speed is not None:
            alert = Alert.objects.filter(segment=self, temporal_segment=speed.temporal_segment).first()
            if alert is not None:
                properties['alert_id'] = alert.pk
            speed_info = speed.check_value()
            properties.update(speed_info)
        else:
            historic_speed = (HistoricSpeed.objects.filter(segment=self, day_type=day_type,
                                                           temporal_segment=temporal_segment)
                              .order_by("-timestamp").first())
            if historic_speed is not None:
                properties["historic_speed"] = historic_speed.speed
            else:
                properties["historic_speed"] = "Sin registro"
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

    def get_stops(self):
        stops_query = Stop.objects.filter(segment=self)
        if stops_query.count() == 0:
            return []
        return [stop.stop_id for stop in stops_query]


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

    def check_value(self):
        geojson_data = dict()
        geojson_data["speed"] = self.speed
        geojson_data["color"] = self.assign_color()
        geojson_data["temporal_segment"] = self.temporal_segment
        historic_speed: HistoricSpeed = HistoricSpeed.objects.filter(
            segment=self.segment,
            day_type=self.day_type,
            temporal_segment=self.temporal_segment,
        ).order_by("-timestamp").first()
        if historic_speed is not None:
            geojson_data["historic_speed"] = str(historic_speed.speed)
        else:
            geojson_data["historic_speed"] = "Sin registro"
        return geojson_data


class HistoricSpeed(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    speed = models.FloatField(blank=False, null=False)
    day_type = models.CharField(max_length=1, blank=False, null=False, default="L")
    temporal_segment = models.IntegerField(blank=False, null=False, default=0)
    timestamp = models.DateTimeField(default=timezone.localtime)


# TODO: Create alert

class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Save object to the database. Removes all other entries if there
        are any.
        """
        self.__class__.objects.exclude(id=self.id).delete()
        self.pk = 1
        super(SingletonModel, self).save(*args, **kwargs)

    @classmethod
    def load(cls, *args, **kwargs):
        """
        Load object from the database. Failing that, create a new empty
        (default) instance of the object and return it (without saving it
        to the database).
        """

        try:
            return cls.objects.get(*args, **kwargs)
        except cls.DoesNotExist:
            return cls()


class AlertThreshold(SingletonModel):
    threshold = models.FloatField(blank=False, null=False, default=2)


class Alert(models.Model):
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE)
    detected_speed = models.ForeignKey(Speed, on_delete=models.CASCADE)
    temporal_segment = models.IntegerField(default=0)
    voted_positive = models.IntegerField(default=0)
    voted_negative = models.IntegerField(default=0)
    timestamp = models.DateTimeField(default=timezone.localtime)


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
