"""Geospatial utility helpers."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def decode_polyline6(polyline: str) -> list[tuple[float, float]]:
    """Decode a polyline6 string into a list of ``(lat, lon)`` coordinates."""
    coordinates: list[tuple[float, float]] = []
    index = lat = lon = 0
    length = len(polyline)

    while index < length:
        shift = result = 0
        while True:
            value = ord(polyline[index]) - 63
            index += 1
            result |= (value & 0x1F) << shift
            shift += 5
            if value < 0x20:
                break
        delta_lat = ~(result >> 1) if result & 1 else result >> 1
        lat += delta_lat

        shift = result = 0
        while True:
            value = ord(polyline[index]) - 63
            index += 1
            result |= (value & 0x1F) << shift
            shift += 5
            if value < 0x20:
                break
        delta_lon = ~(result >> 1) if result & 1 else result >> 1
        lon += delta_lon
        coordinates.append((lat / 1_000_000.0, lon / 1_000_000.0))

    return coordinates


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in miles between two lat/lon points."""
    earth_radius_miles = 3958.8
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    a = (
        sin(delta_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    )
    c = 2 * asin(sqrt(a))
    return earth_radius_miles * c


def cumulative_route_miles(route_points: list[tuple[float, float]]) -> list[float]:
    """Return cumulative miles from the start for every route point."""
    if not route_points:
        return []
    cumulative = [0.0]
    for index in range(1, len(route_points)):
        prev_lat, prev_lon = route_points[index - 1]
        lat, lon = route_points[index]
        cumulative.append(cumulative[-1] + haversine_miles(prev_lat, prev_lon, lat, lon))
    return cumulative


def sample_route_points(
    route_points: list[tuple[float, float]], sample_every_miles: float = 50.0
) -> list[tuple[float, float]]:
    """Sample route points approximately every ``sample_every_miles``."""
    if len(route_points) <= 1:
        return route_points[:]

    cumulative = cumulative_route_miles(route_points)
    sampled = [route_points[0]]
    next_target = sample_every_miles

    for index in range(1, len(route_points)):
        while cumulative[index] >= next_target:
            sampled.append(route_points[index])
            next_target += sample_every_miles
    if sampled[-1] != route_points[-1]:
        sampled.append(route_points[-1])
    return sampled
