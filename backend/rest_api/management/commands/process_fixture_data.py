from django.core.management import BaseCommand, CommandError
from processors.osm.process import process_fixture_data


class Command(BaseCommand):
    help = 'Process fixture data and save to database'

    def handle(self, *args, **options):
        print("Calling process_fixture_data command...")
        process_fixture_data()
