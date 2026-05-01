"""Fuel stop simulation and greedy optimization service."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from math import cos, radians
from pathlib import Path
from typing import Any

from django.conf import settings

from api.utils.geo import cumulative_route_miles, haversine_miles, sample_route_points

logger = logging.getLogger(__name__)

MAX_RANGE_MILES = 500.0
MILES_PER_GALLON = 10.0
TANK_CAPACITY_GALLONS = 50.0
ROUTE_SAMPLE_MILES = 50.0
LOOKAHEAD_MILES = 125.0
SEARCH_RADIUS_MILES = 20.0
_STATION_CACHE: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class FuelStop:
    """Represents one fuel stop output row."""

    location: str
    latitude: float
    longitude: float
    price_per_gallon: float
    gallons_filled: float
    cost: float


def load_fuel_stations() -> list[dict[str, Any]]:
    """Load the CSV fuel station dataset once and cache in memory."""
    global _STATION_CACHE  # pylint: disable=global-statement
    if _STATION_CACHE is not None:
        return _STATION_CACHE

    dataset_path = Path(settings.FUEL_DATASET_PATH)
    stations: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stations.append(
                {
                    "location": row.get("location", "Unknown"),
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "price_per_gallon": float(row["price_per_gallon"]),
                }
            )
    logger.info("Loaded %s fuel stations from %s", len(stations), dataset_path)
    _STATION_CACHE = stations
    return stations


def compute_fuel_plan(route_geometry: dict[str, Any], distance_miles: float) -> tuple[list[FuelStop], float, float]:
    """Return optimized fuel stops, total cost, and total gallons used."""
    if distance_miles < MAX_RANGE_MILES:
        return [], 0.0, 0.0

    coordinates = route_geometry.get("coordinates", [])
    if not coordinates:
        return [], 0.0, 0.0

    route_points = [(float(lat), float(lon)) for lon, lat in coordinates]
    sampled_points = sample_route_points(route_points, sample_every_miles=ROUTE_SAMPLE_MILES)
    stations = load_fuel_stations()
    fuel_stops = optimize_fuel_stops(sampled_points, stations, route_points, distance_miles)
    total_cost = round(sum(stop.cost for stop in fuel_stops), 2)
    total_gallons = round(sum(stop.gallons_filled for stop in fuel_stops), 2)
    return fuel_stops, total_cost, total_gallons


def find_stations_near_route(
    route_points: list[tuple[float, float]],
    stations: list[dict[str, Any]],
    radius_miles: float = 20.0,
) -> list[dict[str, Any]]:
    """Find stations within a route corridor using bounding-box then Haversine filter."""
    if not route_points:
        return []
    lats = [point[0] for point in route_points]
    lons = [point[1] for point in route_points]
    lat_pad = radius_miles / 69.0
    mid_lat = sum(lats) / len(lats)
    lon_pad = radius_miles / max(1.0, 69.0 * abs(cos(radians(mid_lat))))

    min_lat, max_lat = min(lats) - lat_pad, max(lats) + lat_pad
    min_lon, max_lon = min(lons) - lon_pad, max(lons) + lon_pad

    prefiltered = [
        station
        for station in stations
        if min_lat <= station["latitude"] <= max_lat and min_lon <= station["longitude"] <= max_lon
    ]
    if not prefiltered:
        return []

    nearby: list[dict[str, Any]] = []
    for station in prefiltered:
        for lat, lon in route_points:
            if haversine_miles(lat, lon, station["latitude"], station["longitude"]) <= radius_miles:
                nearby.append(station)
                break
    return nearby


def optimize_fuel_stops(
    route_points: list[tuple[float, float]],
    fuel_stations: list[dict[str, Any]],
    full_route_points: list[tuple[float, float]],
    distance_miles: float,
) -> list[FuelStop]:
    """Greedy optimization with lookahead to delay buying when cheaper fuel is ahead.

    The strategy is intentionally greedy and local:
    - At each checkpoint, inspect candidate stations near the current point.
    - Look ahead ~125 miles; if cheaper fuel exists ahead, only buy enough to reach that point.
    - Otherwise buy enough for the longest feasible leg (up to tank/range).
    """
    if distance_miles < MAX_RANGE_MILES:
        return []

    cumulative = cumulative_route_miles(route_points)
    checkpoints = _checkpoint_miles(distance_miles)
    fuel_stops: list[FuelStop] = []
    # Checkpoints are created at max-range boundaries, so fuel is effectively near empty there.
    remaining_fuel = 0.0
    search_radius_miles = max(float(getattr(settings, "FUEL_SEARCH_RADIUS_MILES", SEARCH_RADIUS_MILES)), SEARCH_RADIUS_MILES)
    route_corridor_stations = find_stations_near_route(
        full_route_points, fuel_stations, radius_miles=search_radius_miles
    )
    if not route_corridor_stations:
        route_corridor_stations = fuel_stations

    for checkpoint_mile in checkpoints:
        point_index = _first_index_at_or_after(cumulative, checkpoint_mile)
        current_point = route_points[point_index]
        current_station = _pick_station_for_point(
            current_point, route_corridor_stations, search_radius_miles
        )

        ahead_limit = min(distance_miles, checkpoint_mile + LOOKAHEAD_MILES)
        ahead_stations = _stations_in_mile_window(
            route_points,
            cumulative,
            route_corridor_stations,
            checkpoint_mile,
            ahead_limit,
            search_radius_miles,
        )
        cheaper_ahead_exists = any(
            station["price_per_gallon"] < current_station["price_per_gallon"] for station in ahead_stations
        )

        # Keep a small reserve so slight geometry variation does not strand the vehicle.
        reserve_gallons = 2.0
        if cheaper_ahead_exists:
            target_miles = ahead_limit - checkpoint_mile
            logger.info(
                "Fuel decision: delaying refill at mile %.1f, cheaper station ahead", checkpoint_mile
            )
        else:
            target_miles = min(MAX_RANGE_MILES, distance_miles - checkpoint_mile)
            logger.info(
                "Fuel decision: filling more at mile %.1f, current station best in lookahead",
                checkpoint_mile,
            )

        required_gallons = min(
            TANK_CAPACITY_GALLONS,
            max(0.0, (target_miles / MILES_PER_GALLON) + reserve_gallons),
        )
        gallons_to_add = max(0.0, required_gallons - remaining_fuel)
        if gallons_to_add > 0.01:
            cost = gallons_to_add * current_station["price_per_gallon"]
            fuel_stops.append(
                FuelStop(
                    location=current_station["location"],
                    latitude=current_station["latitude"],
                    longitude=current_station["longitude"],
                    price_per_gallon=round(current_station["price_per_gallon"], 3),
                    gallons_filled=round(gallons_to_add, 2),
                    cost=round(cost, 2),
                )
            )

        next_checkpoint = min(distance_miles, checkpoint_mile + MAX_RANGE_MILES)
        gallons_spent = (next_checkpoint - checkpoint_mile) / MILES_PER_GALLON
        remaining_fuel = max(0.0, min(TANK_CAPACITY_GALLONS, remaining_fuel + gallons_to_add - gallons_spent))
    return fuel_stops


def _checkpoint_miles(distance_miles: float) -> list[float]:
    """Return checkpoint mile markers where refuel decisions are made."""
    marker = MAX_RANGE_MILES
    checkpoints: list[float] = []
    while marker < distance_miles:
        checkpoints.append(marker)
        marker += MAX_RANGE_MILES
    return checkpoints


def _first_index_at_or_after(cumulative: list[float], target_mile: float) -> int:
    """Find first route index whose cumulative distance is >= target mile."""
    for index, value in enumerate(cumulative):
        if value >= target_mile:
            return index
    return len(cumulative) - 1


def _stations_in_mile_window(
    route_points: list[tuple[float, float]],
    cumulative: list[float],
    stations: list[dict[str, Any]],
    window_start: float,
    window_end: float,
    radius_miles: float,
) -> list[dict[str, Any]]:
    """Collect stations near route points between two mile markers."""
    candidates: list[dict[str, Any]] = []
    for index, mile in enumerate(cumulative):
        if mile < window_start or mile > window_end:
            continue
        lat, lon = route_points[index]
        for station in stations:
            if haversine_miles(lat, lon, station["latitude"], station["longitude"]) <= radius_miles:
                candidates.append(station)
    return candidates

def _pick_station_for_point(
    point: tuple[float, float], stations: list[dict[str, Any]], search_radius_miles: float
) -> dict[str, Any]:
    """Pick cheapest station in radius; fallback to nearest if radius has no stations."""
    lat, lon = point
    in_radius: list[tuple[dict[str, Any], float]] = []
    nearest_station = None
    nearest_distance = float("inf")

    for station in stations:
        distance = haversine_miles(lat, lon, station["latitude"], station["longitude"])
        if distance <= search_radius_miles:
            in_radius.append((station, distance))
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_station = station

    if in_radius:
        return min(in_radius, key=lambda item: item[0]["price_per_gallon"])[0]
    logger.warning("No stations within %.2f miles, using nearest fallback", search_radius_miles)
    if nearest_station is None:
        raise ValueError("Fuel station dataset is empty")
    return nearest_station
