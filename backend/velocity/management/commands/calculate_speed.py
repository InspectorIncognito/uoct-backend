import os
import logging
import datetime
from django.core.management import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Calculate speed for all segments of each shape in a range of time.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start_time',
            help="Start time of the GPS pulses.",
            type=datetime.datetime
        )
        parser.add_argument(
            '--end_time',
            help="End time of the GPS pulses.",
            type=datetime.datetime
        )

    def handle(self, *args, **options):
        pass
