from rest_framework import serializers
from rest_api.models import Shape


class ShapeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shape
        fields = '__all__'
