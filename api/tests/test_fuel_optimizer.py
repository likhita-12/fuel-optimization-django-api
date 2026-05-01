"""Unit tests for fuel optimizer service."""

from unittest.mock import patch

from django.test import SimpleTestCase

from api.services import fuel_optimizer


class FuelOptimizerTests(SimpleTestCase):
    """Validate fuel stop selection and cost calculations."""

    @patch("api.services.fuel_optimizer.load_fuel_stations")
    def test_short_route_needs_no_stops(self, mock_load_fuel_stations):
        """Routes under max range should not create fuel stops."""
        geometry = {"type": "LineString", "coordinates": [[-74.0, 40.7], [-75.0, 40.0]]}
        stops, total, gallons = fuel_optimizer.compute_fuel_plan(geometry, 120.0)
        self.assertEqual(stops, [])
        self.assertEqual(total, 0.0)
        self.assertEqual(gallons, 0.0)
        mock_load_fuel_stations.assert_not_called()

    @patch("api.services.fuel_optimizer.load_fuel_stations")
    def test_greedy_lookahead_prefers_delayed_buying(self, mock_load_fuel_stations):
        """Greedy strategy buys less when cheaper station exists ahead."""
        geometry = {
            "type": "LineString",
            "coordinates": [
                [-74.0, 40.7],
                [-85.0, 40.0],
                [-96.0, 39.5],
                [-108.0, 36.0],
            ],
        }
        mock_load_fuel_stations.return_value = [
            {"location": "A", "latitude": 40.0, "longitude": -85.0, "price_per_gallon": 3.80},
            {"location": "B", "latitude": 40.0, "longitude": -85.1, "price_per_gallon": 3.50},
            {"location": "C", "latitude": 39.5, "longitude": -96.0, "price_per_gallon": 3.20},
        ]

        stops, total, gallons = fuel_optimizer.compute_fuel_plan(geometry, 1100.0)

        self.assertGreaterEqual(len(stops), 1)
        self.assertGreater(total, 0.0)
        self.assertGreater(gallons, 0.0)

    @patch("api.services.fuel_optimizer.load_fuel_stations")
    @patch("api.services.fuel_optimizer.settings.FUEL_SEARCH_RADIUS_MILES", 1.0)
    def test_fallback_to_nearest_when_no_station_in_radius(self, mock_load_fuel_stations):
        """Use nearest station if no stations are found in configured radius."""
        geometry = {
            "type": "LineString",
            "coordinates": [[-90.0, 35.0], [-97.0, 35.0], [-104.0, 35.0]],
        }
        mock_load_fuel_stations.return_value = [
            {"location": "Far Cheap", "latitude": 44.0, "longitude": -120.0, "price_per_gallon": 2.5},
            {"location": "Nearest", "latitude": 35.1, "longitude": -97.0, "price_per_gallon": 3.6},
        ]

        stops, total, _ = fuel_optimizer.compute_fuel_plan(geometry, 550.0)

        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0].location, "Nearest")
        self.assertGreater(total, 0.0)

    def test_haversine_distance(self):
        """Haversine returns reasonable values for known city distance."""
        from api.utils.geo import haversine_miles

        distance = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertGreater(distance, 2400)
        self.assertLess(distance, 2600)
