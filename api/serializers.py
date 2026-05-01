"""Serializers for route API request and response."""

from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    """Validate route lookup request body."""

    start = serializers.CharField(max_length=255)
    end = serializers.CharField(max_length=255)


class FuelStopSerializer(serializers.Serializer):
    """Shape of one fuel stop in response."""

    location = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    price_per_gallon = serializers.FloatField()
    gallons_filled = serializers.FloatField()
    cost = serializers.FloatField()


class RouteResponseSerializer(serializers.Serializer):
    """Output contract for route response."""

    distance_miles = serializers.FloatField()
    estimated_time = serializers.FloatField()
    fuel_efficiency = serializers.FloatField()
    route = serializers.JSONField()
    fuel_stops = FuelStopSerializer(many=True)
    total_cost = serializers.FloatField()
    total_gallons_used = serializers.FloatField()
    cache_used = serializers.BooleanField()
