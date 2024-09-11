from django.core.management import BaseCommand
from rest_api.models import HistoricSpeed, Segment


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Calling create_dummy_historic_speed command...")
        temporal_segments = int(1440 / 15)
        day_types = ['L', 'S', 'D']
        speed = 16
        segments = Segment.objects.all()
        for segment in segments:
            for day_type in day_types:
                for temporal_segment in range(temporal_segments):
                    historic_speed_data = dict(
                        segment=segment,
                        speed=speed,
                        temporal_segment=temporal_segment,
                        day_type=day_type
                    )
                    HistoricSpeed.objects.create(**historic_speed_data)
        print("Command finished successfully")

