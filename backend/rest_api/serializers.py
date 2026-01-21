from rest_framework import serializers

from rest_api.models import (
    Alert,
    AlertThreshold,
    Axles,
    Camera,
    GTFSShape,
    HistoricSpeed,
    Segment,
    Services,
    Shape,
    Speed,
    Stop,
    TrafficSignal,
)


class ShapeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shape
        fields = "__all__"


class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Segment
        fields = "__all__"


class SpeedSerializer(serializers.ModelSerializer):
    shape = serializers.IntegerField(source="segment.shape.id", read_only=True)
    sequence = serializers.IntegerField(source="segment.sequence", read_only=True)
    active_services = serializers.ListField(source="services", read_only=True)

    class Meta:
        model = Speed
        fields = [
            "shape",
            "sequence",
            "temporal_segment",
            "day_type",
            "distance",
            "time_secs",
            "timestamp",
            "active_services",
        ]


class HistoricSpeedSerializer(serializers.ModelSerializer):
    shape = serializers.IntegerField(source="segment.shape.id", read_only=True)
    sequence = serializers.IntegerField(source="segment.sequence", read_only=True)

    class Meta:
        model = HistoricSpeed
        fields = ["shape", "sequence", "temporal_segment", "day_type", "speed"]


class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = "__all__"


class ServicesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Services
        fields = "__all__"


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = "__all__"


class GTFSShapeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GTFSShape
        fields = ["shape_id", "route_id", "direction"]


class AlertThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertThreshold
        fields = "__all__"


class AxlesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Axles
        fields = ["id", "name", "streets", "city"]

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre no puede estar vacío.")
        # verificar que no exista otro con el mismo nombre (ignorando mayúsculas/minúsculas)
        qs = Axles.objects.filter(name__iexact=value.strip())
        if qs.exists():
            raise serializers.ValidationError("Ya existe un eje con ese nombre.")
        return value.strip()

    def validate_streets(self, value):
        if not value or not isinstance(value, list):
            raise serializers.ValidationError("Debe incluir al menos una calle.")
        # Opcional: eliminar duplicados conservando orden
        clean = []
        for s in value:
            s_norm = s.strip()
            if s_norm and s_norm not in clean:
                clean.append(s_norm)
        if not clean:
            raise serializers.ValidationError("Debe ingresar calles válidas.")
        return clean


class TrafficSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrafficSignal
        fields = "__all__"


class CameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = "__all__"


class ProcessAxisSerializer(serializers.Serializer):
    axis_name = serializers.CharField(max_length=255, required=True)
    distance_threshold = serializers.FloatField(required=False, default=500.0)
