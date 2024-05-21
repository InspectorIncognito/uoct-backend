import os
import logging
import datetime
from django.core.management import BaseCommand, CommandError
from gtfs_rt.models import GPSPulse
from gtfs_rt.config import SANTIAGO_TIMEZONE
from velocity.utils import generate_grid
from velocity.vehicle import VehicleManager
from velocity.segment import FiveHundredMeterSegmentCriteria


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
        # TODO: filter by start_date and end_date arguments
        # By default, calculates the commercial speed mean from the last 15 minutes of every segment.
        end_date_hardcode = datetime.datetime(year=2024, month=5, day=15, hour=20, minute=0, second=0)
        end_date = SANTIAGO_TIMEZONE.localize(end_date_hardcode)
        start_date = SANTIAGO_TIMEZONE.localize((end_date_hardcode - datetime.timedelta(minutes=5)))
        queryset = GPSPulse.objects.filter(timestamp__gte=start_date, timestamp__lte=end_date)

        print("Creating Grid Object")
        grid_obj = generate_grid()
        print("Creating Vehicle Manager")
        vm = VehicleManager(grid_obj)

        print(f"Start date: {start_date}")
        print(f"End date: {end_date}")

        print(f"Got {len(queryset)} GPS pulses.")

        for gps in queryset:
            vm.add_data(gps)

        fhmsc = FiveHundredMeterSegmentCriteria(grid_obj)
        speed_records = vm.calculate_speed(fhmsc)
        print(speed_records)
