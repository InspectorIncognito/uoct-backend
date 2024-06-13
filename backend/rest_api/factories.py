import factory
from rest_api.models import Speed, Shape, Segment
from random import randint
import numpy as np


class ShapeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Shape


class SegmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Segment

    shape = factory.SubFactory(ShapeFactory)
    geometry = [[0.0, 0.0], [0.0, 0.1], [1.0, 1.0]]


class SpeedFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Speed

    segment = factory.SubFactory(SegmentFactory)
    day_type = "L"


def create_speed_dataset(segment_n: int = 5, speed_n: int = 10):
    shape = ShapeFactory()
    dataset = {
        "shape_id": shape.pk,
        "segments": {}
    }
    for idx in range(segment_n):
        segment = SegmentFactory(shape=shape, sequence=idx)
        for month in range(1, 13):
            speeds = []
            for _ in range(speed_n):
                speed = randint(10, 30)
                SpeedFactory(speed=speed, segment=segment)
                speeds.append(speed)
            speed_mean = np.mean(speeds)
            data = dataset["segments"].get(segment.pk) or []
            data.append({
                "date": month,
                "expected_speed": speed_mean
            })
            dataset["segments"][segment.pk] = data
    return dataset
