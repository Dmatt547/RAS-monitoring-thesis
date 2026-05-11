"""
RAS Telemetry Exporter — Thesis Simulation
Simulates health metrics for a Remote Autonomous System (drone)
and exposes them to Prometheus on port 8000.

Metrics simulated:
  - Battery level (%)
  - Signal strength / RSSI (dBm)
  - Uptime (seconds)
  - CPU temperature (celsius)
  - Packet loss (%)
  - System health status (1 = healthy, 0 = fault)

Run: python ras_exporter.py
Then open: http://localhost:8000/metrics
"""

import time
import random
import math
from prometheus_client import start_http_server, Gauge, Counter, Enum

# --- Metric definitions ---
battery_level      = Gauge('ras_battery_percent',     'Battery level of the RAS (%)')
signal_strength    = Gauge('ras_signal_rssi_dbm',     'WiFi signal strength in dBm (more negative = weaker)')
cpu_temperature    = Gauge('ras_cpu_temperature_c',   'CPU/onboard temperature in Celsius')
packet_loss        = Gauge('ras_packet_loss_percent', 'Network packet loss (%)')
uptime_seconds     = Counter('ras_uptime_seconds_total', 'Total uptime in seconds')
health_status      = Gauge('ras_health_status',       '1 = healthy, 0 = fault detected')
fault_events       = Counter('ras_fault_events_total', 'Total number of fault events detected')

# --- Simulation state ---
battery    = 100.0
rssi       = -45.0
temp       = 35.0
loss       = 0.0
tick       = 0

# Fault injection schedule (tick number -> fault type)
# These simulate realistic fault scenarios for the thesis
FAULT_SCHEDULE = {
    60:  "battery_drain",     # ~1 min in: rapid battery drain starts
    120: "signal_loss",       # ~2 min in: signal degrades
    180: "overheat",          # ~3 min in: temperature spike
    240: "recovery",          # ~4 min in: system recovers
}

active_fault = None

def simulate_tick():
    global battery, rssi, temp, loss, tick, active_fault

    tick += 1

    # Check fault schedule
    if tick in FAULT_SCHEDULE:
        active_fault = FAULT_SCHEDULE[tick]
        if active_fault != "recovery":
            fault_events.inc()
            print(f"[tick {tick}] FAULT INJECTED: {active_fault}")
        else:
            active_fault = None
            print(f"[tick {tick}] System recovered — faults cleared")

    # --- Battery simulation ---
    if active_fault == "battery_drain":
        battery -= random.uniform(0.8, 1.5)   # Rapid drain
    else:
        battery -= random.uniform(0.05, 0.15) # Normal drain
    battery = max(0.0, battery)

    # --- Signal strength simulation (dBm, typically -30 to -90) ---
    if active_fault == "signal_loss":
        rssi -= random.uniform(0.5, 2.0)      # Degrading signal
        loss = min(100.0, loss + random.uniform(1.0, 3.0))
    else:
        rssi += random.uniform(-1.0, 1.0)     # Normal fluctuation
        rssi = max(-90.0, min(-30.0, rssi))
        loss = max(0.0, loss - random.uniform(0.0, 0.5))

    # --- Temperature simulation ---
    if active_fault == "overheat":
        temp += random.uniform(0.5, 1.5)      # Rising temp
    else:
        # Natural fluctuation around baseline
        baseline = 35.0
        temp += (baseline - temp) * 0.05 + random.uniform(-0.3, 0.3)
    temp = min(95.0, max(20.0, temp))

    # --- Health status logic ---
    is_healthy = (
        battery > 15.0 and
        rssi > -80.0 and
        temp < 80.0 and
        loss < 20.0
    )
    health_status.set(1 if is_healthy else 0)

    # --- Push to Prometheus ---
    battery_level.set(round(battery, 2))
    signal_strength.set(round(rssi, 2))
    cpu_temperature.set(round(temp, 2))
    packet_loss.set(round(loss, 2))
    uptime_seconds.inc()

    # Console log every 10 ticks
    if tick % 10 == 0:
        status = "HEALTHY" if is_healthy else "** FAULT **"
        print(f"[tick {tick:4d}] Battery: {battery:5.1f}%  RSSI: {rssi:6.1f} dBm  Temp: {temp:4.1f}C  Loss: {loss:4.1f}%  [{status}]")

if __name__ == "__main__":
    print("Starting RAS Telemetry Exporter on http://localhost:8000/metrics")
    print("Fault injection schedule:")
    for t, f in FAULT_SCHEDULE.items():
        print(f"  tick {t:>4} (~{t}s): {f}")
    print("-" * 60)

    start_http_server(8000)

    while True:
        simulate_tick()
        time.sleep(1)
