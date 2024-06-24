from django.core.management.base import BaseCommand
from processors.speed.avg_speed import get_last_month_avg_speed


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Calling get_last_month_avg_speed...")
        get_last_month_avg_speed()
