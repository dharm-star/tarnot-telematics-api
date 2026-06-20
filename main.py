import os
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
import pandas as pd

app = FastAPI(
    title="Tractor Telematics Analytics API",
    description="Production-grade pipeline to calculate vehicle utilization metrics from messy IoT data.",
    version="1.0.0"
)

# Global in-memory lookup cache for O(1) API response times
VEHICLE_METRICS_CACHE: Dict[str, Dict[str, Any]] = {}


class TelemetryEngine:
    """
    Handles the ingestion, sanitization, and aggregation of messy telematics data.
    Decoupled from the delivery framework (FastAPI) to ensure testability.
    """
    SANITY_THRESHOLD_KM = 100.0  # Max credible distance a tractor can travel between consecutive pings

    @classmethod
    def process_data(cls, pings_path: str, vehicles_path: str) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(pings_path) or not os.path.exists(vehicles_path):
            raise FileNotFoundError("Missing source CSV datasets. Verify file paths.")

        # 1. Load Datasets
        pings_df = pd.read_csv(pings_path)
        vehicles_df = pd.read_csv(vehicles_path)

        # 2. Preprocess Timestamps & Sort sequentially per device
        pings_df['ts'] = pd.to_datetime(pings_df['ts'], dayfirst=True, format='mixed', errors='coerce')
        pings_df = pings_df.sort_values(by=['device_id', 'ts']).reset_index(drop=True)

        # 3. Calculate Sequential Odometer Deltas
        pings_df['prev_odometer'] = pings_df.groupby('device_id')['odometer_km'].shift(1)
        pings_df['distance_delta'] = pings_df['odometer_km'] - pings_df['prev_odometer']
        pings_df['distance_delta'] = pings_df['distance_delta'].fillna(0.0)

        # 4. Clean Messy Data Anomalies
        # Case A: Odometer Drops / Hardware Resets (delta < 0) -> Force to 0
        pings_df.loc[pings_df['distance_delta'] < 0, 'distance_delta'] = 0.0

        # Case B: Sensor Upward Spikes / '999999' Out-of-bounds Glitches -> Force to 0
        pings_df.loc[pings_df['distance_delta'] > cls.SANITY_THRESHOLD_KM, 'distance_delta'] = 0.0

        # 5. Define Time Windows for Activity Status Evaluation
        end_of_period = pings_df['ts'].max()
        seven_days_cutoff = end_of_period - pd.Timedelta(days=7)

        pings_df['date'] = pings_df['ts'].dt.date
        pings_df['has_moved'] = pings_df['distance_delta'] > 0.0

        processed_cache = {}

        # 6. Aggregate Metrics against the Vehicle Master
        for _, vehicle in vehicles_df.iterrows():
            dev_id = str(vehicle['device_id'])
            v_pings = pings_df[pings_df['device_id'] == dev_id]

            # Edge Case: Vehicle Master exists but no telemetry pings are found
            if v_pings.empty:
                processed_cache[dev_id] = {
                    "total_distance_km": 0.0,
                    "active_days": 0,
                    "status": "no_data"
                }
                continue

            # Compute absolute distance traveled
            total_dist = round(float(v_pings['distance_delta'].sum()), 2)

            # Compute active days (Unique calendar dates where movement occurred)
            active_days_count = int(v_pings[v_pings['has_moved']]['date'].nunique())

            # Evaluate status condition: Must have moved inside the last 7 days of the period
            moved_in_last_7_days = v_pings[
                (v_pings['ts'] >= seven_days_cutoff) & (v_pings['has_moved'] == True)
            ]
            status = "active" if not moved_in_last_7_days.empty else "inactive"

            processed_cache[dev_id] = {
                "total_distance_km": total_dist,
                "active_days": active_days_count,
                "status": status
            }

        return processed_cache


@app.on_event("startup")
def startup_event():
    """ Runs automatically when the server boots. Warms up the in-memory cache. """
    global VEHICLE_METRICS_CACHE
    try:
        VEHICLE_METRICS_CACHE = TelemetryEngine.process_data(
            pings_path="pings.csv",
            vehicles_path="vehicles.csv"
        )
        print(f" Successfully loaded metrics for {len(VEHICLE_METRICS_CACHE)} vehicles into memory.")
    except Exception as e:
        print(f"🛑 Error loading datasets on startup: {str(e)}")


@app.get("/vehicles/{device_id}/usage")
def get_vehicle_usage(device_id: str):
    """ Serves precomputed analytics instantly with O(1) lookup complexity. """
    if device_id not in VEHICLE_METRICS_CACHE:
        raise HTTPException(
            status_code=404,
            detail=f"Vehicle with device_id '{device_id}' not found in asset registry."
        )
    return VEHICLE_METRICS_CACHE[device_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
