import factory
from rest_api.models import Speed, Shape, Segment


class ShapeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Shape


class SegmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Segment

    shape = factory.SubFactory(ShapeFactory)


class SpeedFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Speed

    segment = factory.SubFactory(SegmentFactory)
