# Rides API – Django REST Framework

A RESTful API for managing ride information, built with Django REST Framework.

## Table of Contents

- [Setup](#setup)
- [Running the Server](#running-the-server)
- [Running Tests](#running-tests)
- [API Endpoints](#api-endpoints)
- [Design Decisions](#design-decisions)
- [Bonus SQL Query](#bonus-sql-query)

---

## Setup

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd rides_project

# Create and activate a virtual environment
python -m venv .venv

# On macOS/Linux:
source .venv/bin/activate
# On Windows PowerShell:
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# (Optional) Create a superuser for the admin panel
python manage.py createsuperuser
```

---

## Running the Server

```bash
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/api/`.

---

## Running Tests

```bash
python manage.py test rides
```

---

## API Endpoints

### Ride List / CRUD

| Method | URL             | Description        |
|--------|-----------------|--------------------|
| GET    | `/api/rides/`   | List all rides     |
| POST   | `/api/rides/`   | Create a new ride  |
| GET    | `/api/rides/{id}/` | Retrieve a ride |
| PUT    | `/api/rides/{id}/` | Update a ride   |
| DELETE | `/api/rides/{id}/` | Delete a ride   |

### Authentication

All endpoints require **Token Authentication**. Only users with `role = 'admin'` are authorized to access the API.

Include the token in the `Authorization` header:

```
Authorization: Token <your-token>
```

### Query Parameters (GET `/api/rides/`)

| Parameter        | Description                                          | Example                          |
|------------------|------------------------------------------------------|----------------------------------|
| `status`         | Filter rides by status                               | `?status=en-route`               |
| `rider__email`   | Filter rides by rider's email                        | `?rider__email=john@example.com` |
| `ordering`       | Sort results (`pickup_time` or `distance`)           | `?ordering=pickup_time`          |
| `lat` / `lng`    | GPS position for distance sorting (required with `ordering=distance`) | `?ordering=distance&lat=40.7&lng=-74.0` |
| `page`           | Page number for pagination                           | `?page=2`                        |

### Response Format

Each ride in the response includes nested `rider`, `driver`, and `todays_ride_events` (events from the last 24 hours only):

```json
{
    "count": 50,
    "next": "http://127.0.0.1:8000/api/rides/?page=2",
    "previous": null,
    "results": [
        {
            "id_ride": 1,
            "status": "en-route",
            "rider": {
                "id_user": 2,
                "username": "john",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "role": "user",
                "phone_number": "555-1234"
            },
            "driver": {
                "id_user": 3,
                "username": "jane",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane@example.com",
                "role": "user",
                "phone_number": "555-5678"
            },
            "pickup_latitude": 40.7128,
            "pickup_longitude": -74.006,
            "dropoff_latitude": 40.758,
            "dropoff_longitude": -73.9855,
            "pickup_time": "2026-02-12T10:30:00Z",
            "todays_ride_events": [
                {
                    "id_ride_event": 1,
                    "description": "Status changed to pickup",
                    "created_at": "2026-02-12T10:30:00Z"
                }
            ]
        }
    ]
}
```

---

## Design Decisions

### 1. Query Optimization (3 queries total)

The ride list endpoint is optimized to execute at most **3 SQL queries**, regardless of the number of rides returned:

1. **COUNT** – Required by the paginator to compute total pages.
2. **SELECT rides** with `select_related('rider', 'driver')` – Fetches rides and joins the User table for both rider and driver in a single query.
3. **SELECT ride events** via `prefetch_related` with a `Prefetch` object – Fetches only events from the last 24 hours for all rides on the current page in one query, using the `to_attr='todays_ride_events'` pattern to attach them directly to each ride instance.

### 2. `todays_ride_events` – Efficient Filtering of Large Tables

Since the RideEvent table is expected to be very large, we never fetch the full list of events for a ride. The `Prefetch` object applies a `created_at__gte=threshold` filter at the database level, so only recent events are transferred. The `to_attr` pattern avoids additional queries in the serializer.

### 3. Distance Sorting

Distance sorting uses a database-level annotation with an approximate **squared Euclidean distance** formula: `(lat - lat0)² + (lng - lng0)²`. This avoids expensive trigonometric functions (Haversine) while preserving correct ordering for ranking purposes. Since it's computed as a DB annotation, it supports pagination correctly — the database handles the `ORDER BY` and `LIMIT`/`OFFSET`.

Requesting `?ordering=distance` without providing `lat` and `lng` returns a `400 Bad Request` with a descriptive error message.

### 4. Authentication

A custom `IsAdminRole` permission class checks that the authenticated user has `role == 'admin'`. This is applied at the ViewSet level so all CRUD operations are protected.

### 5. Model Design

- `User` extends Django's `AbstractUser` to add `role` and `phone_number` while retaining all built-in auth functionality.
- `RideEvent.created_at` uses `auto_now_add=True` for consistency — it is always set by the database at insert time.

---

## Bonus SQL Query

The following raw SQL returns the count of trips that took more than 1 hour from pickup to dropoff, grouped by month and driver. It calculates trip duration by finding the time difference between `'Status changed to pickup'` and `'Status changed to dropoff'` events for each ride.

```sql
SELECT
    strftime('%Y-%m', re_pickup.created_at)          AS month,
    u.first_name || ' ' || u.last_name               AS driver,
    COUNT(*)                                          AS "count_of_trips_gt_1hr"
FROM ride r
JOIN "user" u
    ON u.id_user = r.id_driver
JOIN ride_event re_pickup
    ON re_pickup.id_ride = r.id_ride
    AND re_pickup.description = 'Status changed to pickup'
JOIN ride_event re_dropoff
    ON re_dropoff.id_ride = r.id_ride
    AND re_dropoff.description = 'Status changed to dropoff'
WHERE
    -- Duration from pickup to dropoff exceeds 1 hour (3600 seconds)
    (julianday(re_dropoff.created_at) - julianday(re_pickup.created_at)) * 86400 > 3600
GROUP BY
    strftime('%Y-%m', re_pickup.created_at),
    u.id_user
ORDER BY
    month ASC,
    driver ASC;
```

> **Note:** The above query uses SQLite functions (`strftime`, `julianday`). For **PostgreSQL**, replace with:

```sql
SELECT
    TO_CHAR(re_pickup.created_at, 'YYYY-MM')         AS month,
    u.first_name || ' ' || u.last_name               AS driver,
    COUNT(*)                                          AS "count_of_trips_gt_1hr"
FROM ride r
JOIN "user" u
    ON u.id_user = r.id_driver
JOIN ride_event re_pickup
    ON re_pickup.id_ride = r.id_ride
    AND re_pickup.description = 'Status changed to pickup'
JOIN ride_event re_dropoff
    ON re_dropoff.id_ride = r.id_ride
    AND re_dropoff.description = 'Status changed to dropoff'
WHERE
    EXTRACT(EPOCH FROM (re_dropoff.created_at - re_pickup.created_at)) > 3600
GROUP BY
    TO_CHAR(re_pickup.created_at, 'YYYY-MM'),
    u.id_user,
    u.first_name,
    u.last_name
ORDER BY
    month ASC,
    driver ASC;
```

### Sample Output

| Month   | Driver   | Count of Trips > 1hr |
|---------|----------|----------------------|
| 2024-01 | Chris H  | 4                    |
| 2024-01 | Howard Y | 5                    |
| 2024-01 | Randy W  | 2                    |
| 2024-02 | Chris H  | 7                    |
| 2024-02 | Howard Y | 5                    |
| ...     | ...      | ...                  |