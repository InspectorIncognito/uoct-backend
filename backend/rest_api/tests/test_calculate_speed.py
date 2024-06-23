from rest_api.factories import ShapeFactory
from rest_api.tests.tests_views_base import BaseTestCase
from django.core.management import call_command, CommandError


class TestCalculateSpeed(BaseTestCase):
    def setUp(self):
        pass

    def test_no_shapes_found(self):
        with self.assertRaises(CommandError) as context:
            call_command('calculate_speed')
        self.assertEqual("No shapes found", str(context.exception))

    def test_no_segments_found(self):
        ShapeFactory()
        with self.assertRaises(Exception) as context:
            call_command('calculate_speed')
        self.assertEqual("No segments found", str(context.exception))
