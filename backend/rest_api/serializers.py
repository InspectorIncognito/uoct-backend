from rest_framework import serializers
from rest_api.models import Shape, Segment, GTFSShape, Services, Speed, HistoricSpeed, Stop


class ShapeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shape
        fields = '__all__'


class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Segment
        fields = '__all__'


class SpeedSerializer(serializers.ModelSerializer):
    shape = serializers.IntegerField(source="segment.shape.id", read_only=True)
    sequence = serializers.IntegerField(source="segment.sequence", read_only=True)

    class Meta:
        model = Speed
        fields = ['shape', 'sequence', 'speed', 'timestamp', 'day_type', 'temporal_segment']


class HistoricSpeedSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricSpeed
        fields = '__all__'

class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = '__all__'


class ServicesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Services
        fields = '__all__'


class GTFSShapeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GTFSShape
        fields = ['shape_id', 'direction']
