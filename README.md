# Fuel Optimization Route API

This project solves a practical problem:
**for a long road trip, where and when should a vehicle refuel to minimize total fuel cost?**

Instead of just returning a route, this API makes intelligent decisions about fuel stops based on distance, fuel prices, and vehicle constraints.

---

## 💡 What the API does

Given a start and end location (within the United States), the API:

* Generates a driving route using OpenRouteService
* Assumes a vehicle with a **maximum range of 500 miles**
* Identifies optimal fuel stops along the route
* Selects fuel stations based on **cost efficiency**, not just proximity
* Calculates total fuel consumption assuming **10 miles per gallon**
* Returns a structured response with route details, fuel stops, and total cost

---

## API Endpoint

**POST** `/api/route/`

### Request

```json
{
  "start": "New York, NY",
  "end": "Los Angeles, CA"
}
```

### Response (sample)

```json
{
  "distance_miles": 2789.5,
  "fuel_stops": [
    {
      "lat": 39.9612,
      "lng": -82.9988,
      "price": 3.62,
      "gallons": 10.0,
      "cost": 36.2
    }
  ],
  "total_cost": 612.7
}
```

---

## Approach & Logic

The system focuses on minimizing cost while keeping decisions realistic:

* The route is sampled at regular intervals (~50 miles)
* Refueling decisions are evaluated before the vehicle reaches its maximum range (~450 miles)
* Nearby fuel stations (within ~20 miles) are considered
* A cost-based selection strategy is applied:

  * Choose the **cheapest available station** within reach
  * Use a **lookahead mechanism (~150 miles)** to delay refueling if cheaper fuel is ahead
  * Fall back to the nearest viable station if necessary

This creates a balance between **cost optimization** and **practical feasibility**.

---

## Tech Stack

* Django (latest stable version)
* Django REST Framework
* OpenRouteService API (routing)
* Custom fuel optimization logic
* CSV dataset for fuel prices

---

## Running the project locally

```bash
pip install -r requirements.txt
export ORS_API_KEY=your_api_key
python manage.py runserver
```

---

## Design Considerations

* Uses **a single routing API call** to keep the system efficient
* Separates routing and fuel logic into modular services
* Designed to be easily extendable (e.g., real-time fuel prices, EV routing)

---

##  Demo

A short walkthrough of the API and code:
👉 (Add your Loom video link here)

---

##  Final Note

This project focuses not just on generating results, but on making **cost-aware decisions under constraints**, which reflects real-world system design scenarios.
