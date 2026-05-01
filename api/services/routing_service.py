"""Service for route retrieval from OpenRouteService directions API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class RoutingServiceError(Exception):
    """Raised when route lookup fails."""


class InvalidLocationError(RoutingServiceError):
    """Raised when input locations cannot be geocoded."""


@dataclass(frozen=True)
class RouteData:
    """Container for route geometry and distance."""

    distance_miles: float
    duration_minutes: float
    geometry: dict[str, Any]
    cache_used: bool


class OpenRouteServiceRoutingService:
    """Fetch and cache route data using OpenRouteService directions."""

    nominatim_search_url = "https://nominatim.openstreetmap.org/search"
    directions_url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"

    def get_route(self, start: str, end: str) -> RouteData:
        """Return route for start/end, using cache before network."""
        cache_key = self._cache_key(start, end)
        cached = cache.get(cache_key)
        if cached:
            logger.info("Route cache hit for %s -> %s", start, end)
            return RouteData(
                distance_miles=cached["distance_miles"],
                duration_minutes=cached["duration_minutes"],
                geometry=cached["geometry"],
                cache_used=True,
            )

        logger.info("Route cache miss for %s -> %s", start, end)
        start_point, end_point = self._geocode_locations(start, end)
        logger.info("Calling ORS directions API once")
        route_data = self._fetch_directions(start_point, end_point)
        cache.set(
            cache_key,
            {
                "distance_miles": route_data.distance_miles,
                "duration_minutes": route_data.duration_minutes,
                "geometry": route_data.geometry,
            },
            timeout=settings.ROUTING_CACHE_TTL_SECONDS,
        )
        return RouteData(
            distance_miles=route_data.distance_miles,
            duration_minutes=route_data.duration_minutes,
            geometry=route_data.geometry,
            cache_used=False,
        )

    def _fetch_directions(
        self, start_point: tuple[float, float], end_point: tuple[float, float]
    ) -> RouteData:
        """Fetch route geometry and distance from ORS directions endpoint."""
        if not settings.ORS_API_KEY:
            raise RoutingServiceError("ORS_API_KEY is not configured")

        headers = {
            "Authorization": settings.ORS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "coordinates": [
                [start_point[0], start_point[1]],
                [end_point[0], end_point[1]],
            ],
            "instructions": False,
        }
        try:
            response = requests.post(
                self.directions_url,
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("ORS directions API request failed")
            raise RoutingServiceError("Routing provider unavailable") from exc

        features = data.get("features", [])
        if not features:
            raise RoutingServiceError("No route found for given locations")

        route = features[0]
        summary = route.get("properties", {}).get("summary", {})
        distance_miles = float(summary.get("distance", 0.0)) / 1609.344
        duration_minutes = float(summary.get("duration", 0.0)) / 60.0
        geometry = route.get("geometry")
        if not geometry or geometry.get("type") != "LineString" or not geometry.get("coordinates"):
            raise RoutingServiceError("Invalid geometry returned by routing provider")

        return RouteData(
            distance_miles=distance_miles,
            duration_minutes=duration_minutes,
            geometry=geometry,
            cache_used=False,
        )

    def _geocode_locations(
        self, start: str, end: str
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Resolve start/end text into longitude/latitude with Nominatim."""
        return self._geocode_text(start), self._geocode_text(end)

    def _geocode_text(self, location: str) -> tuple[float, float]:
        """Resolve free-text location to ``(lon, lat)`` for directions calls."""
        params = {"q": location, "format": "json", "limit": 1}
        headers = {"User-Agent": "fuel-routing-api/1.0"}
        try:
            response = requests.get(
                self.nominatim_search_url, params=params, headers=headers, timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Nominatim geocoding failed")
            raise RoutingServiceError("Failed to validate locations") from exc

        if not data:
            raise InvalidLocationError(f"Could not geocode location: {location}")

        if isinstance(data, list):
            item = data[0]
            if "lon" in item and "lat" in item:
                return float(item["lon"]), float(item["lat"])
            if "features" in item:
                coordinates = item.get("features", [{}])[0].get("geometry", {}).get("coordinates")
                if coordinates and len(coordinates) == 2:
                    return float(coordinates[0]), float(coordinates[1])
        if isinstance(data, dict):
            features = data.get("features", [])
            if features:
                coordinates = features[0].get("geometry", {}).get("coordinates")
                if coordinates and len(coordinates) == 2:
                    return float(coordinates[0]), float(coordinates[1])

        raise InvalidLocationError(f"Could not geocode location: {location}")

    @staticmethod
    def _cache_key(start: str, end: str) -> str:
        """Build deterministic key for route cache entries."""
        digest = sha256(f"{start.strip().lower()}::{end.strip().lower()}".encode()).hexdigest()
        return f"route:{digest}"


# Backward-compatible alias to avoid touching unrelated modules.
MapboxRoutingService = OpenRouteServiceRoutingService
