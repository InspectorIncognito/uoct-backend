from django.core.management.base import BaseCommand
from processors.osm.query import EJES_PRINCIPALES
from rest_api.models import Axles


class Command(BaseCommand):
    help = "Create Axles database entries from predefined axle data"

    def handle(self, *args, **options):
        self.stdout.write("Creating Axles database entries...")

        for name, axle in EJES_PRINCIPALES.items():
            streets = axle.get("streets", [])
            city = axle.get("city", "Provincia de Santiago")

            if not name or not streets:
                self.stdout.write(
                    self.style.WARNING(f"Skipping invalid axle data: {axle}")
                )
                continue

            axles_entry, created = Axles.objects.get_or_create(
                name=name, defaults={"streets": streets, "city": city}
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created Axles entry: {name}"))
            else:
                self.stdout.write(
                    self.style.WARNING(f"Axles entry already exists: {name}")
                )

        self.stdout.write(self.style.SUCCESS("Finished creating Axles entries."))
