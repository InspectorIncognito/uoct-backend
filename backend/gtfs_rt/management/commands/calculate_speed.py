from django.core.management import BaseCommand, CommandError
from gtfs_rt.processors.speed import calculate_speed
from rest_api.models import Shape, Segment
from datetime import datetime
from gtfs_rt.config import TIMEZONE


class Command(BaseCommand):
    help = 'Calculate speed for all segments of each shape in a range of time.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start_time',
            help="Start time of the GPS pulses. Format: yyyy-mm-ddTHH:MM:SSZ",
            type=str
        )
        parser.add_argument(
            '--end_time',
            help="End time of the GPS pulses. Format: yyyy-mm-ddTHH:MM:SSZ",
            type=str
        )

    def handle(self, *args, **options):
        start_time = None
        end_time = None
        if options['start_time'] and options['end_time']:
            start_time = datetime.strptime(options['start_time'], '%Y-%m-%dT%H:%M:%SZ').astimezone(TIMEZONE)
            end_time = datetime.strptime(options['end_time'], '%Y-%m-%dT%H:%M:%SZ').astimezone(TIMEZONE)
        if Shape.objects.count() == 0:
            raise CommandError("No shapes found")
        elif Segment.objects.count() == 0:
            raise Exception("No segments found")
        calculate_speed(start_time, end_time)
