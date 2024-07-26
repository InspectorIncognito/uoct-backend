from django.core.management import BaseCommand, CommandError
from gtfs_rt.processors.speed import calculate_speed
from rest_api.models import Shape, Segment
from django.utils import timezone


class Command(BaseCommand):
    help = 'Calculate speed for all segments of each shape in a range of time.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start_time',
            help="Start time of the GPS pulses. Format: yyyy-mm-dd HH:MM:SS",
            type=str
        )
        parser.add_argument(
            '--end_time',
            help="End time of the GPS pulses. Format: yyyy-mm-dd HH:MM:SS",
            type=str
        )

    def handle(self, *args, **options):
        if Shape.objects.count() == 0:
            raise CommandError("No shapes found")
        elif Segment.objects.count() == 0:
            raise Exception("No segments found")
        now = timezone.localtime()
        calculate_speed(now)
