from django.core.management import BaseCommand

from rest_api.models import AlertThreshold


class Command(BaseCommand):
    help = 'Creates an instance of AlertThreshold with its default value'

    def handle(self, *args, **options):
        print("Calling set_alert_threshold command...")
        AlertThreshold.objects.create(**{"threshold": 2})
