from rest_api.util.shape import flush_shape_objects

from rest_api.tests.tests_views_base import BaseTestCase
from rest_api.models import Shape, Segment
from geojson.geometry import LineString, MultiLineString
from geojson.feature import Feature, FeatureCollection
from processors.models.shapes import shapes_to_geojson


class GeometryTestCase(BaseTestCase):
    def setUp(self):
        self.login_process()
        self.shape_data = {
            'name': 'Test Shape'
        }
        self.segment_data = [
            {
                'sequence': 0,
                'geometry': [(0, 0), (0, 1), (0, 2)]
            },
            {
                'sequence': 1,
                'geometry': [(0, 3), (0, 4), (0, 5)]
            }
        ]

    def create_shape(self, shape_data=None):
        shape_data = shape_data or self.shape_data
        return Shape.objects.create(**shape_data)

    def create_segments(self, segment_data=None):
        segment_data = segment_data or self.segment_data
        shape_obj = self.create_shape()
        for segment in segment_data:
            segment['shape_id'] = shape_obj
        segments = Segment.objects.bulk_create([Segment(**segment) for segment in segment_data])
        return shape_obj, segments


class ShapeTest(GeometryTestCase):
    def test_create(self):
        shape_obj = Shape.objects.create(**self.shape_data)
        expected_obj = Shape.objects.get(pk=shape_obj.pk)
        self.assertEqual(shape_obj, expected_obj)

    def test_to_geojson(self):
        shape, segments = self.create_segments()
        actual = shape.to_geojson()
        expected = [Feature(
            geometry=LineString(coordinates=segment.geometry),
            properties={
                "shape_id": shape.pk,
                "sequence": segment.sequence
            }
        ) for segment in segments]
        self.assertEqual(actual, expected)

    def test_to_geojson_with_no_segments(self):
        shape = self.create_shape()
        actual = shape.to_geojson()
        expected = {}
        self.assertDictEqual(actual, expected)

    def test_flush_shape_objects(self):
        _, _ = self.create_segments()
        self.assertTrue(len(Shape.objects.all()) == 1)
        self.assertTrue(len(Segment.objects.all()) == len(self.segment_data))
        flush_shape_objects()
        self.assertTrue(len(Shape.objects.all()) == 0)
        self.assertTrue(len(Segment.objects.all()) == 0)


class SegmentTest(GeometryTestCase):
    def test_create(self):
        segment_data = [
            {
                'sequence': 0,
                'geometry': [(0, 0), (0, 1), (0, 2)]
            },
            {
                'sequence': 1,
                'geometry': [(0, 3), (0, 4), (0, 5)]
            },
            {
                'sequence': 2,
                'geometry': [(0, 6), (0, 7), (0, 8)]
            }
        ]
        _, segments = self.create_segments(segment_data)
        self.assertEqual(len(segments), len(segment_data))

    def test_to_geojson(self):
        shape, segments = self.create_segments()
        expected = [Feature(
            geometry=LineString(coordinates=segment.geometry),
            properties={
                "shape_id": segment.shape_id.pk,
                "sequence": segment.sequence
            }
        ) for segment in segments]
        actual = [segment.to_geojson() for segment in segments]
        self.assertEqual(actual, expected)


class GeoJSONTest(GeometryTestCase):
    def test_shapes_to_geojson(self):
        _, _ = self.create_segments()
        actual = shapes_to_geojson()
        features = []
        shapes = Shape.objects.all()
        for shape in shapes:
            features.extend(shape.to_geojson())
        expected = FeatureCollection(
            features=features
        )

        self.assertEqual(actual, expected)

    def test_shapes_to_geojson_without_shapes(self):
        expected = FeatureCollection(features=[])
        actual = shapes_to_geojson()

        self.assertDictEqual(actual, expected)