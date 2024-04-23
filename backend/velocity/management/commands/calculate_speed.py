from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Calculate speed of every GridCell inside the GridManager and update it'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        pass
