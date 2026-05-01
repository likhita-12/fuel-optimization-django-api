# Fuel Optimization API

## Overview
Django REST API that:
- Computes route between two US locations
- Optimizes fuel stops based on cost
- Calculates total fuel expense

## Endpoint
POST /api/route/

### Request
{
  "start": "New York, NY",
  "end": "Los Angeles, CA"
}

### Response
- distance_miles
- fuel_stops
- total_cost

## Tech Used
- Django
- Django REST Framework
- OpenRouteService API

## Setup
pip install -r requirements.txt
export ORS_API_KEY=your_key
python manage.py runserver
