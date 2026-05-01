"""Fuel stop optimization service."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

from django.conf import settings

MILES_PER_GALLON = 10.0
MAX_RANGE_MILES = 500.0
TANK_CAPACITY_GALLONS = 50.0
SEGMENT_MILES = 450.0
SAMPLE_EVERY_MILES = 50.0
SEARCH_RADIUS_MILES = 20.0
LOOKAHEAD_MILES = 150.0
MIN_STOP_SEPARATION_MILES = 10.0
DESTINATION_BUFFER_MILES = 50.0

_STATIONS_CACHE: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class FuelStop:
    """Structured fuel stop record returned to API clients."""

    lat: float
    lng: float
    price: float
    gallons: float
    cost: float


def optimize_fuel_for_route(
    route_geometry: dict[str, Any],
    distance_miles: float,
) -> tuple[list[FuelStop], float]:
    """Compute optimized fuel stops and total fuel cost for a route."""
    # For routes under full-tank range, no stop is required.
    if distance_miles < MAX_RANGE_MILES:
        return [], 0.0

    coordinates = route_geometry.get("coordinates", [])
    if not coordinates:
        return [], 0.0

    route_points = [(float(lat), float(lon)) for lon, lat in coordinates]
    stations = load_fuel_dataset()
    sampled_points = _sample_points(route_points, SAMPLE_EVERY_MILES)
    cumulative = _cumulative_distances(sampled_points)
    decision_miles = _segment_markers(distance_miles, SEGMENT_MILES)

    # Assume the vehicle starts full and fuel is consumed until each decision point.
    remaining_fuel = max(0.0, TANK_CAPACITY_GALLONS - (SEGMENT_MILES / MILES_PER_GALLON))
    stops: list[FuelStop] = []

    for current_mile in decision_miles:
        # Avoid adding stop decisions effectively at destination.
        if distance_miles - current_mile <= DESTINATION_BUFFER_MILES:
            continue

        idx = _index_at_or_after(cumulative, current_mile)
        point = sampled_points[idx]
        current_station = _pick_cheapest_station_near_point(point, stations, SEARCH_RADIUS_MILES)

        lookahead_end = min(distance_miles, current_mile + LOOKAHEAD_MILES)
        cheaper_ahead = _has_cheaper_station_ahead(
            sampled_points, cumulative, stations, current_mile, lookahead_end, current_station["price_per_gallon"]
        )

        next_decision_mile = min(distance_miles, current_mile + SEGMENT_MILES)
        miles_to_next = max(0.0, next_decision_mile - current_mile)
        # Keep a small safety reserve but avoid oversized top-ups.
        reserve_gallons = 1.0
        minimum_needed = min(TANK_CAPACITY_GALLONS, (miles_to_next / MILES_PER_GALLON) + reserve_gallons)

        # If cheaper fuel exists ahead and we already have enough, delay refuel.
        if cheaper_ahead and remaining_fuel >= minimum_needed:
            gallons_to_buy = 0.0
        else:
            if cheaper_ahead:
                target_miles = max(0.0, lookahead_end - current_mile)
                required_gallons = min(TANK_CAPACITY_GALLONS, target_miles / MILES_PER_GALLON)
            else:
                required_gallons = minimum_needed
            gallons_to_buy = max(0.0, required_gallons - remaining_fuel)

        if gallons_to_buy > 0:
            stop_cost = gallons_to_buy * current_station["price_per_gallon"]
            _append_or_merge_stop(
                stops=stops,
                station=current_station,
                gallons_to_buy=gallons_to_buy,
                stop_cost=stop_cost,
            )
            remaining_fuel = min(TANK_CAPACITY_GALLONS, remaining_fuel + gallons_to_buy)

        miles_until_next_decision = min(SEGMENT_MILES, max(0.0, distance_miles - current_mile))
        remaining_fuel = max(0.0, remaining_fuel - (miles_until_next_decision / MILES_PER_GALLON))

    total_cost = round(sum(stop.cost for stop in stops), 2)
    return stops, total_cost


def _append_or_merge_stop(
    stops: list[FuelStop],
    station: dict[str, Any],
    gallons_to_buy: float,
    stop_cost: float,
) -> None:
    """Append a new stop or merge with previous one if station is effectively the same."""
    new_lat = round(station["latitude"], 6)
    new_lng = round(station["longitude"], 6)
    new_price = round(station["price_per_gallon"], 3)
    new_gallons = round(gallons_to_buy, 2)
    new_cost = round(stop_cost, 2)

    if stops:
        last = stops[-1]
        is_same_coord = last.lat == new_lat and last.lng == new_lng
        is_close = _haversine_miles(last.lat, last.lng, new_lat, new_lng) <= MIN_STOP_SEPARATION_MILES
        if is_same_coord or is_close:
            merged_gallons = round(last.gallons + new_gallons, 2)
            merged_cost = round(last.cost + new_cost, 2)
            merged_price = round((merged_cost / merged_gallons), 3) if merged_gallons > 0 else new_price
            stops[-1] = FuelStop(
                lat=last.lat,
                lng=last.lng,
                price=merged_price,
                gallons=merged_gallons,
                cost=merged_cost,
            )
            return

    stops.append(
        FuelStop(
            lat=new_lat,
            lng=new_lng,
            price=new_price,
            gallons=new_gallons,
            cost=new_cost,
        )
    )


def load_fuel_dataset() -> list[dict[str, Any]]:
    """Load and cache station data from CSV for real-price lookups."""
    global _STATIONS_CACHE  # pylint: disable=global-statement
    if _STATIONS_CACHE is not None:
        return _STATIONS_CACHE

    dataset_path = Path(settings.FUEL_DATASET_PATH)
    stations: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            stations.append(
                {
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "price_per_gallon": float(row["price_per_gallon"]),
                }
            )
    _STATIONS_CACHE = stations
    return stations


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in miles between coordinates."""
    earth_radius = 3958.8
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return earth_radius * (2 * asin(sqrt(a)))


def _sample_points(points: list[tuple[float, float]], every_miles: float) -> list[tuple[float, float]]:
    """Sample route points approximately every N miles."""
    if len(points) < 2:
        return points
    sampled = [points[0]]
    distance_since_sample = 0.0
    for i in range(1, len(points)):
        prev_lat, prev_lng = points[i - 1]
        lat, lng = points[i]
        leg = _haversine_miles(prev_lat, prev_lng, lat, lng)
        distance_since_sample += leg
        if distance_since_sample >= every_miles:
            sampled.append((lat, lng))
            distance_since_sample = 0.0
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def _cumulative_distances(points: list[tuple[float, float]]) -> list[float]:
    """Compute cumulative route miles for sampled points."""
    if not points:
        return []
    cumulative = [0.0]
    for i in range(1, len(points)):
        prev_lat, prev_lng = points[i - 1]
        lat, lng = points[i]
        cumulative.append(cumulative[-1] + _haversine_miles(prev_lat, prev_lng, lat, lng))
    return cumulative


def _segment_markers(distance_miles: float, segment: float) -> list[float]:
    """Return decision points along route."""
    markers: list[float] = []
    marker = segment
    while marker < distance_miles:
        markers.append(marker)
        marker += segment
    return markers


def _index_at_or_after(cumulative: list[float], target_mile: float) -> int:
    """Find first sampled point index at or after target distance."""
    for i, dist in enumerate(cumulative):
        if dist >= target_mile:
            return i
    return len(cumulative) - 1


def _pick_cheapest_station_near_point(
    point: tuple[float, float],
    stations: list[dict[str, Any]],
    radius_miles: float,
) -> dict[str, Any]:
    """Pick cheapest station within radius; otherwise nearest station."""
    lat, lng = point
    nearby: list[dict[str, Any]] = []
    nearest = None
    nearest_dist = float("inf")

    for station in stations:
        dist = _haversine_miles(lat, lng, station["latitude"], station["longitude"])
        if dist <= radius_miles:
            nearby.append(station)
        if dist < nearest_dist:
            nearest = station
            nearest_dist = dist

    if nearby:
        return min(nearby, key=lambda s: s["price_per_gallon"])
    if nearest is None:
        raise ValueError("No stations available")
    return nearest


def _has_cheaper_station_ahead(
    sampled_points: list[tuple[float, float]],
    cumulative: list[float],
    stations: list[dict[str, Any]],
    current_mile: float,
    lookahead_end: float,
    current_price: float,
) -> bool:
    """Check if a cheaper station exists ahead within lookahead window."""
    for i, mile in enumerate(cumulative):
        if mile < current_mile or mile > lookahead_end:
            continue
        candidate = _pick_cheapest_station_near_point(sampled_points[i], stations, SEARCH_RADIUS_MILES)
        if candidate["price_per_gallon"] < current_price:
            return True
    return False
