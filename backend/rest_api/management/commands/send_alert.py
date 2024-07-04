from django.core.management import BaseCommand

from rest_api.util.alert import send_alerts


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("calling send_alert...")
        send_alerts()
