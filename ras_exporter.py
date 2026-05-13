"""
RAS Telemetry Exporter — Real Dataset Replay
Replays drone_telemetry_dataset.csv (derived from real DJI flight records)
row by row, exposing metrics to Prometheus on port 8000.

Source dataset: tampering_research_dataset.csv
  - Real DJI flight log data (DJI_FLIGHTRECORD_BIN_DJI_LOG)
  - 190 rows across 6 anomaly phases
  - Phases: normal_operation, data_injection, altitude_anomaly,
            speed_anomaly, heading_anomaly, combined_fault

Run:   python ras_exporter.py
Check: http://localhost:8000/metrics
"""

import time
import csv
import os
from prometheus_client import start_http_server, Gauge, Counter

# --- Metric definitions ---
altitude        = Gauge('ras_altitude_m',           'Drone altitude in metres')
speed           = Gauge('ras_speed_ms',             'Drone speed in m/s')
heading         = Gauge('ras_heading_deg',          'Drone heading in degrees')
latitude        = Gauge('ras_latitude',             'GPS latitude')
longitude       = Gauge('ras_longitude',            'GPS longitude')
anomaly_label   = Gauge('ras_anomaly_label',        '0 = normal, 1 = anomaly detected in data')
health_status   = Gauge('ras_health_status',        '1 = healthy, 0 = fault/anomaly phase')
fault_events    = Counter('ras_fault_events_total', 'Total fault phase transitions detected')

# --- Load dataset ---
DATASET_PATH = os.path.join(os.path.dirname(__file__), "drone_telemetry_dataset.csv")

def load_dataset():
    with open(DATASET_PATH, newline="") as f:
        return list(csv.DictReader(f))

if __name__ == "__main__":
    rows = load_dataset()
    print(f"Loaded {len(rows)} rows from real DJI flight dataset")
    print("Starting RAS Telemetry Exporter on http://localhost:8000/metrics")
    print("-" * 70)
    print(f"{'Tick':>5}  {'Phase':<22} {'Alt(m)':>8} {'Spd':>6} {'Hdg':>8}  {'Health'}")
    print("-" * 70)

    start_http_server(8000)

    prev_health = 1
    prev_phase  = None

    for row in rows:
        tick    = int(row["timestamp_s"])
        phase   = row["phase"]
        alt     = float(row["altitude_m"])
        spd     = float(row["speed_ms"])
        hdg     = float(row["heading_deg"])
        lat     = float(row["latitude"])
        lon     = float(row["longitude"])
        label   = int(row["anomaly_label"])
        health  = int(row["health_status"])

        # Push to Prometheus
        altitude.set(alt)
        speed.set(spd)
        heading.set(hdg)
        latitude.set(lat)
        longitude.set(lon)
        anomaly_label.set(label)
        health_status.set(health)

        # Count fault transitions (healthy -> fault)
        if prev_health == 1 and health == 0:
            fault_events.inc()

        # Print phase changes
        if phase != prev_phase:
            print(f"\n>>> Phase: {phase.upper()}")

        # Print every 10 ticks
        if tick % 10 == 0:
            status = "OK" if health else "FAULT"
            print(f"{tick:>5}  {phase:<22} {alt:>8.2f}  {spd:>5.2f}  {hdg:>8.2f}  [{status}]")

        prev_health = health
        prev_phase  = phase

        time.sleep(1)

    print("\n--- Dataset replay complete ---")
    print("Keeping exporter alive for final scrape...")
    while True:
        time.sleep(5)
