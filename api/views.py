"""API views for fuel-optimized route endpoint."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import RouteRequestSerializer
from api.services.fuel_service import optimize_fuel_for_route
from api.services.routing_service import (
    InvalidLocationError,
    MapboxRoutingService,
    RoutingServiceError,
)

logger = logging.getLogger(__name__)


class RouteAPIView(APIView):
    """Handle route calculation and fuel optimization."""

    routing_service = MapboxRoutingService()

    def get(self, request, *args, **kwargs):
        """Simple health-style response for browser GET checks."""
        return Response({"message": "API working via browser"}, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        """Compute route and optimized fuel stops for the given origin and destination."""
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start = serializer.validated_data["start"]
        end = serializer.validated_data["end"]

        try:
            route_data = self.routing_service.get_route(start=start, end=end)
            fuel_stops, total_cost = optimize_fuel_for_route(
                route_geometry=route_data.geometry,
                distance_miles=route_data.distance_miles,
            )
        except InvalidLocationError as exc:
            logger.warning("Invalid route input: %s", exc)
            return Response(
                {"detail": str(exc), "code": "invalid_location"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RoutingServiceError as exc:
            logger.exception("Routing request failed")
            return Response(
                {"detail": str(exc), "code": "routing_provider_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except (ValueError, KeyError) as exc:
            logger.exception("Fuel optimization failed")
            return Response(
                {"detail": f"Fuel optimization failed: {exc}", "code": "fuel_optimization_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        route_coordinates = [
            [round(float(lat), 6), round(float(lng), 6)]
            for lng, lat in route_data.geometry.get("coordinates", [])
        ]
        payload = {
            "distance_miles": round(route_data.distance_miles, 2),
            "route_summary": {
                "start": start,
                "end": end,
            },
            "route_coordinates": route_coordinates,
            "fuel_stops": [
                {
                    "lat": stop.lat,
                    "lng": stop.lng,
                    "price": stop.price,
                    "gallons": stop.gallons,
                    "cost": stop.cost,
                }
                for stop in fuel_stops
            ],
            "total_cost": total_cost,
        }
        return Response(payload, status=status.HTTP_200_OK)


# Backward-compatible alias for older imports.
RouteView = RouteAPIView
