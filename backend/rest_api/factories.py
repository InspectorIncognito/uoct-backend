import datetime
import uuid

import factory
from rest_api.models import Speed, Shape, Segment, HistoricSpeed, Stop, Alert
from random import randint
from django.utils import timezone


class ShapeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Shape


class SegmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Segment

    shape = factory.SubFactory(ShapeFactory)
    segment_id = uuid.uuid4()
    sequence = 0
    geometry = [[0.0, 0.0], [0.0, 0.1], [1.0, 1.0]]


class StopFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Stop

    segment = factory.SubFactory(SegmentFactory)
    latitude = factory.Faker('latitude')
    longitude = factory.Faker('longitude')
    stop_id = 'STOP_ID'


class SpeedFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Speed

    segment = factory.SubFactory(SegmentFactory)
    distance = 100
    time_secs = 5
    day_type = "L"


class HistoricSpeedFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HistoricSpeed

    segment = factory.SubFactory(SegmentFactory)
    speed = 16.0
    day_type = "L"


class AlertFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Alert

    segment = factory.SubFactory(SegmentFactory)
    detected_speed = factory.SubFactory(SpeedFactory)


def create_speed_dataset(segment_n: int = 5, speed_n: int = 10):
    shape = ShapeFactory()
    dataset = {
        "shape_id": shape.pk,
        "segments": {}
    }
    this_year = datetime.datetime.now().year
    for idx in range(segment_n):
        segment = SegmentFactory(shape=shape, sequence=idx)
        for month in range(1, 13):
            speed_timestamp = datetime.datetime(this_year, month, 1)
            speed_timestamp = timezone.make_aware(speed_timestamp, timezone.get_current_timezone())
            distances = []
            times = []
            for _ in range(speed_n):
                distance = randint(100, 1000)
                time_secs = randint(10, 50)
                distances.append(distance)
                times.append(time_secs)
                SpeedFactory(distance=distance, time_secs=time_secs, segment=segment, timestamp=speed_timestamp)
            distances_sum = sum(distances)
            times_sum = sum(times)
            speed_mean = round(3.6 * distances_sum / times_sum, 2)
            data = dataset["segments"].get(segment.pk) or []
            data.append({
                "date": month,
                "expected_speed": speed_mean
            })
            dataset["segments"][segment.pk] = data
    return dataset
