from django.core.management import BaseCommand, CommandError
from processors.osm.process import process_shape_data


class Command(BaseCommand):
    help = 'Queries a custom OSM Overpass query, processes it and saves it to database'

    def add_arguments(self, parser):
        parser.add_argument(
            "--distance",
            help="Sets the distance threshold of segments in each shape queried",
            type=int or float
        )

    def handle(self, *args, **options):
        if options["distance"]:
            if options["distance"] <= 0.0:
                raise CommandError("Distance must be greater than 0")
            process_shape_data(options['distance'])
        else:
            process_shape_data()
