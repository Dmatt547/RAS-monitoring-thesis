"""
RAS Live Telemetry Exporter — RQ2 (Physical Drone)

Connects to a physical DJI Tello drone via the djitellopy SDK and exposes its
raw telemetry as Prometheus metrics on port 8001.

This differs from the RQ1 exporter (ras_exporter.py, port 8000), which replays
a pre-labelled CSV dataset and publishes a ready-made ras_health_status value.
This exporter publishes ONLY raw sensor readings — no health/fault label is
computed here. Per the RQ2 design, fault detection is performed entirely by
Prometheus alerting rules evaluated against these raw metrics
(see ras_alerts.rules.yml), so the system determines faults itself instead of
being told about them by the data source.

Run:   python ras_exporter_live.py
Check: http://localhost:8001/metrics
"""

import time

from djitellopy import Tello
from prometheus_client import Gauge, start_http_server

SCRAPE_PORT = 8001
POLL_INTERVAL_SEC = 1.0

# --- Raw metric definitions (mirrors the fields logged by telemetry_logger.py) ---
battery = Gauge("ras_battery_percent", "Battery level (%)")
temp_low = Gauge("ras_temperature_low_c", "Lower bound of onboard temperature range (C)")
temp_high = Gauge("ras_temperature_high_c", "Upper bound of onboard temperature range (C)")
height_cm = Gauge("ras_height_cm", "Height above ground (cm), from time-of-flight sensor")
barometer_cm = Gauge("ras_barometer_cm", "Barometric height estimate (cm)")
pitch_deg = Gauge("ras_pitch_deg", "Pitch angle (degrees)")
roll_deg = Gauge("ras_roll_deg", "Roll angle (degrees)")
yaw_deg = Gauge("ras_yaw_deg", "Yaw angle (degrees)")
vel_x = Gauge("ras_velocity_x_cm_s", "Velocity, X axis (cm/s)")
vel_y = Gauge("ras_velocity_y_cm_s", "Velocity, Y axis (cm/s)")
vel_z = Gauge("ras_velocity_z_cm_s", "Velocity, Z axis (cm/s)")
motor_time_s = Gauge("ras_motor_on_seconds", "Cumulative motor-on time reported by the drone (s)")
accel_x = Gauge("ras_accel_x", "Acceleration, X axis (0.001g)")
accel_y = Gauge("ras_accel_y", "Acceleration, Y axis (0.001g)")
accel_z = Gauge("ras_accel_z", "Acceleration, Z axis (0.001g)")
poll_success = Gauge("ras_last_poll_success", "1 if the last poll of the drone succeeded, 0 otherwise")

# Maps djitellopy's get_current_state() field names to the Gauges above.
STATE_TO_METRIC = {
    "bat": battery,
    "templ": temp_low,
    "temph": temp_high,
    "h": height_cm,
    "baro": barometer_cm,
    "pitch": pitch_deg,
    "roll": roll_deg,
    "yaw": yaw_deg,
    "vgx": vel_x,
    "vgy": vel_y,
    "vgz": vel_z,
    "time": motor_time_s,
    "agx": accel_x,
    "agy": accel_y,
    "agz": accel_z,
}


def publish_state(state: dict) -> None:
    """Push one drone state reading into the matching Prometheus gauges.

    Kept separate from main() so it can be unit tested with a fake state
    dict, without needing a physical drone connected.
    """
    for field, gauge in STATE_TO_METRIC.items():
        value = state.get(field)
        if value is not None:
            gauge.set(float(value))


def main():
    tello = Tello()
    tello.connect()
    print(f"Connected. Battery: {tello.get_battery()}%")
    print(f"Exporting live telemetry on http://localhost:{SCRAPE_PORT}/metrics")
    print("Press Ctrl+C to stop.\n")

    start_http_server(SCRAPE_PORT)

    try:
        while True:
            try:
                state = tello.get_current_state()
                publish_state(state)
                poll_success.set(1)
            except Exception as exc:  # noqa: BLE001 - log and keep exporting
                print(f"Poll failed: {exc}")
                poll_success.set(0)
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
