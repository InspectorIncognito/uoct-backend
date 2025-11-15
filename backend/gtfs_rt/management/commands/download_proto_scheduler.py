from django.core.management.base import BaseCommand, CommandError
from gtfs_rt.processors.manager import GTFSRTManager
import datetime
import pytz


class Command(BaseCommand):
    help = "Download GTFS RT proto data from Sonda"

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            help="Sets the time limit for downloading GTFS RT proto data (format: HH:MM:SS).",
            type=float
        )

    def handle(self, *args, **options):
        print("Running download_proto_scheduler")
        default_hours = None  # 1 hour default
        if options['hours']:
            default_hours = options['hours']
        gtfs_rt_manager = GTFSRTManager()
        gtfs_rt_manager.run_process_scheduler(default_hours)
