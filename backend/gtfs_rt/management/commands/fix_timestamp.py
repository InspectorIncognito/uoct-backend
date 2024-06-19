from django.core.management.base import BaseCommand
import datetime

from gtfs_rt.config import TIMEZONE
from gtfs_rt.models import GPSPulse


class Command(BaseCommand):
    help = "Download GTFS RT proto files every 1 minute."

    def handle(self, *args, **options):
        print("COMMAND RUNNING")
        gps_pulses = GPSPulse.objects.all()
        for gps_pulse in gps_pulses:
            timezone = TIMEZONE
            timestamp = gps_pulse.timestamp
            timestamp_data = {
                "year": timestamp.year,
                "month": timestamp.month,
                "day": timestamp.day,
                "hour": timestamp.hour,
                "minute": timestamp.minute,
                "second": timestamp.second,
                "microsecond": timestamp.microsecond
            }
            new_timestamp = datetime.datetime(**timestamp_data)
            new_timestamp = timezone.localize(new_timestamp)
            gps_pulse.timestamp = new_timestamp
            gps_pulse.save()
        print("DONE")
