from django.core.management.base import BaseCommand, CommandError
from gtfs_rt.processors.manager import GTFSRTManager
import datetime
import pytz


class Command(BaseCommand):
    help = "Download GTFS RT proto files every 1 minute."

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            help="Sets the time limit for downloading GTFS RT proto data (format: HH:MM:SS).",
            type=int
        )


    def handle(self, *args, **options):
        default_hours = 1
        if options['hours']:
            default_hours = options['hours']
        gtfs_rt_manager = GTFSRTManager()
        gtfs_rt_manager.run_process_scheduler(hours=default_hours)
