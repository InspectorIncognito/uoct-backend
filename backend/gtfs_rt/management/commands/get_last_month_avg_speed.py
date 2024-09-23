from django.core.management.base import BaseCommand
from processors.speed.avg_speed import get_month_commercial_speed
from django.utils import timezone


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Calling get_last_month_avg_speed command...")
        today = timezone.localtime()
        this_year = today.year
        this_month = today.month
        get_month_commercial_speed(year=this_year, month=this_month)
