from datetime import datetime

from django.core.management import BaseCommand, CommandError
from gtfs_rt.config import TIMEZONE
from gtfs_rt.processors.speed import calculate_speed
from rest_api.models import Segment, Shape


class Command(BaseCommand):
    help = "Calculate speed for all segments of each shape in a range of time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start_time",
            help="Start time of the GPS pulses. Format: yyyy-mm-ddTHH:MM:SSZ",
            type=str,
        )
        parser.add_argument(
            "--end_time",
            help="End time of the GPS pulses. Format: yyyy-mm-ddTHH:MM:SSZ",
            type=str,
        )
        parser.add_argument(
            "--use-hmm",
            action="store_true",
            help="Use HMM map matching (active mode - replaces grid-based matching)",
        )
        parser.add_argument(
            "--hmm-shadow",
            action="store_true",
            help="Run HMM in shadow mode (logs results but doesn't affect speed calculations)",
        )
        parser.add_argument(
            "--hmm-max-distance",
            type=float,
            default=100.0,
            help="HMM maximum distance for candidate segments in meters (default: 100.0)",
        )
        parser.add_argument(
            "--hmm-sigma",
            type=float,
            default=25.0,
            help="HMM emission probability sigma (default: 25.0)",
        )
        parser.add_argument(
            "--hmm-beta",
            type=float,
            default=30.0,
            help="HMM transition probability beta (default: 30.0)",
        )

    def handle(self, *args, **options):
        start_time = None
        end_time = None
        if options["start_time"] and options["end_time"]:
            start_time = datetime.strptime(
                options["start_time"], "%Y-%m-%dT%H:%M:%SZ"
            ).astimezone(TIMEZONE)
            end_time = datetime.strptime(
                options["end_time"], "%Y-%m-%dT%H:%M:%SZ"
            ).astimezone(TIMEZONE)
        if Shape.objects.count() == 0:
            raise CommandError("No shapes found")
        elif Segment.objects.count() == 0:
            raise Exception("No segments found")

        # Extract HMM parameters
        use_hmm = options.get("use_hmm", False)
        hmm_shadow_mode = options.get("hmm_shadow", False)
        hmm_max_distance = options.get("hmm_max_distance", 100.0)
        hmm_sigma = options.get("hmm_sigma", 25.0)
        hmm_beta = options.get("hmm_beta", 30.0)

        calculate_speed(
            start_time,
            end_time,
            use_hmm=use_hmm,
            hmm_shadow_mode=hmm_shadow_mode,
            hmm_max_distance=hmm_max_distance,
            hmm_sigma=hmm_sigma,
            hmm_beta=hmm_beta,
        )
