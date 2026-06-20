# Tractor Telematics Analytics API

A production-grade FastAPI pipeline that ingests messy IoT telematics data from tractors, sanitizes it, and serves vehicle utilization metrics via a REST API with O(1) lookup performance.

---

## Quickstart (2 commands)

```bash
pip install pipenv
pipenv shell
pipenv install
pipenv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Then visit: http://localhost:8000/docs

---

## Project Structure

```
tractor-telematics/
├── main.py          # FastAPI app + TelemetryEngine
├── pings.csv        # IoT telemetry pings (device_id, ts, odometer_km)
├── vehicles.csv     # Vehicle master registry (device_id, model, registration)
├── Pipfile          # Pipenv dependency declaration
├── Pipfile.lock     # Pinned dependency lockfile
└── README.md
```

---

## API Endpoints

### `GET /vehicles/{device_id}/usage`

Returns precomputed utilization metrics for a vehicle.

**Example:**
```
GET /vehicles/DEV001/usage
```

**Response:**
```json
{
  "total_distance_km": 60.2,
  "active_days": 4,
  "status": "active"
}
```

| Field | Description |
|---|---|
| `total_distance_km` | Total sanitized distance traveled across all pings |
| `active_days` | Count of unique calendar days with any movement |
| `status` | `active` if moved in last 7 days of dataset period, `inactive` otherwise, `no_data` if no pings |

---

## Data Sanitization Logic

The `TelemetryEngine` handles the following anomalies automatically:

| Anomaly | Detection | Fix |
|---|---|---|
| Odometer reset / hardware reboot | `distance_delta < 0` | Set delta to `0` |
| Sensor spike / `999999` glitch | `distance_delta > 100 km` | Set delta to `0` |
| Missing telemetry for registered vehicle | Empty pings for `device_id` | Returns `status: no_data` |
| Malformed timestamps | `pd.to_datetime(..., errors='coerce')` | Row excluded via NaT |

---

## CSV Format

**pings.csv** — one row per IoT ping:
```
device_id,ts,odometer_km
DEV001,01/06/2025 08:00,100.0
```

**vehicles.csv** — vehicle master registry:
```
device_id,model,registration
DEV001,John Deere 5075E,MH-12-AB-1234
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `pandas` | Data ingestion & aggregation |

All managed via **Pipenv** — no manual `pip install` needed.
