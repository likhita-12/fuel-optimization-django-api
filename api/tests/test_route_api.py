"""API tests for route endpoint."""

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient


class RouteApiTests(TestCase):
    """Validate response/error behavior for POST /api/route/."""

    def setUp(self):
        """Set up API test client."""
        self.client = APIClient()

    @patch("api.views.compute_fuel_plan")
    @patch("api.views.MapboxRoutingService.get_route")
    def test_route_success(self, mock_get_route, mock_compute_fuel_plan):
        """Return route and computed fuel stops when inputs are valid."""
        mock_get_route.return_value = type(
            "RouteData",
            (),
            {
                "distance_miles": 2800.0,
                "duration_minutes": 2500.0,
                "cache_used": False,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-74.0, 40.7], [-118.2, 34.0]],
                },
            },
        )()
        mock_compute_fuel_plan.return_value = ([], 420.50, 120.0)

        response = self.client.post(
            "/api/route/",
            {"start": "New York, NY", "end": "Los Angeles, CA"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("distance_miles", response.data)
        self.assertIn("route", response.data)
        self.assertIn("fuel_stops", response.data)
        self.assertIn("fuel_efficiency", response.data)
        self.assertIn("total_gallons_used", response.data)
        self.assertEqual(response.data["total_cost"], 420.5)

    def test_invalid_request(self):
        """Return 400 when request body misses required fields."""
        response = self.client.post("/api/route/", {"start": "New York, NY"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("end", response.data)

    @patch("api.views.MapboxRoutingService.get_route")
    def test_invalid_location_error(self, mock_get_route):
        """Return 400 when location input cannot be geocoded."""
        from api.services.routing_service import InvalidLocationError

        mock_get_route.side_effect = InvalidLocationError("Could not geocode location")
        response = self.client.post(
            "/api/route/",
            {"start": "Invalid Place", "end": "Los Angeles, CA"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_location")

    @patch("api.views.MapboxRoutingService.get_route")
    def test_routing_provider_error(self, mock_get_route):
        """Return 502 when routing service fails."""
        from api.services.routing_service import RoutingServiceError

        mock_get_route.side_effect = RoutingServiceError("Routing provider unavailable")
        response = self.client.post(
            "/api/route/",
            {"start": "New York, NY", "end": "Los Angeles, CA"},
            format="json",
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "routing_provider_error")
