"""Unit tests for routing service behavior and caching."""

from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from api.services.routing_service import MapboxRoutingService


@override_settings(MAPBOX_API_KEY="fake-token", ROUTING_CACHE_TTL_SECONDS=3600)
class RoutingServiceTests(SimpleTestCase):
    """Validate one-call routing path and cache reuse."""

    def setUp(self):
        """Reset cache between tests."""
        cache.clear()
        self.service = MapboxRoutingService()

    @patch("api.services.routing_service.requests.get")
    @patch("api.services.routing_service.requests.post")
    def test_route_cached_after_first_lookup(self, mock_post, mock_get):
        """Second lookup for same inputs should skip external requests."""
        geocode_response = Mock()
        geocode_response.raise_for_status = Mock()
        geocode_response.json.return_value = [
            {"features": [{"geometry": {"coordinates": [-74.0060, 40.7128]}}]},
            {"features": [{"geometry": {"coordinates": [-118.2437, 34.0522]}}]},
        ]
        mock_post.return_value = geocode_response

        directions_response = Mock()
        directions_response.raise_for_status = Mock()
        directions_response.json.return_value = {
            "routes": [
                {
                    "distance": 4506150,
                    "geometry": {"type": "LineString", "coordinates": [[-74.0060, 40.7128], [-118.2437, 34.0522]]},
                }
            ]
        }
        mock_get.return_value = directions_response

        self.service.get_route("New York, NY", "Los Angeles, CA")
        self.service.get_route("New York, NY", "Los Angeles, CA")

        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_get.call_count, 1)
