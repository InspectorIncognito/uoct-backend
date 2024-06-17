from django.core.management.base import BaseCommand, CommandError
from gtfs_rt.processors.manager import GTFSRTManager
import datetime
import pytz


class Command(BaseCommand):
    help = "Download GTFS RT proto data from Sonda"

    def handle(self, *args, **options):
        gtfs_rt_manager = GTFSRTManager()
        gtfs_rt_manager.run_process_cron()
