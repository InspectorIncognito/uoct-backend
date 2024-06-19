import factory
from gtfs_rt.models import GPSPulse


class GPSPulseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GPSPulse
