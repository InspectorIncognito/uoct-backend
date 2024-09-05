from django.core.management import BaseCommand

from rest_api.util.alert import TranSappSiteManager


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Calling delete_speed_anomaly_alerts command...")
        site_manager = TranSappSiteManager()
        site_manager.delete_all_alerts()
