# RAS Health Monitoring — Thesis (T1–T2 2026)

Monitors the health of a Remote Autonomous System (drone) using Prometheus and Grafana. Built for the thesis: **"Monitoring the Health and Reliability of Remote Autonomous Systems"**.

This is the single source-controlled home for all thesis code, T1 and T2 alike — RQ1 work (Trimester 1) and RQ2 work (Trimester 2) both live here from now on.

**RQ1 (Trimester 1, complete):** validated a Prometheus-based monitoring pipeline using real drone telemetry replayed from the [Drone Telemetry Tampering Dataset v2](https://www.kaggle.com/datasets/rasikaekanayakadevlk/drone-telemetry-tampering-dataset-v2) (Kaggle). Fault detection relied on a pre-labelled health status already present in the dataset.

**RQ2 (Trimester 2, in progress):** replaces the pre-labelled dataset with a physical DJI Tello drone streaming live telemetry, and replaces the pre-labelled health status with Prometheus alerting rules that detect faults autonomously from raw metrics.

## What it does

- `ras_exporter.py` — RQ1. Replays drone telemetry from a CSV dataset row by row and exposes the metrics (including a pre-labelled `ras_health_status`) to Prometheus via HTTP on port 8000
- `ras_exporter_live.py` — RQ2. Connects to a physical Tello drone via the `djitellopy` SDK and exposes its raw, live telemetry to Prometheus on port 8001. Publishes no health/fault label — see `ras_alerts.rules.yml`
- `ras_alerts.rules.yml` — RQ2. Prometheus alerting rules that evaluate the raw live metrics against thresholds (battery, temperature, attitude, connection loss) to detect faults autonomously. Thresholds are placeholders pending Phase 1 baseline flight data
- `prometheus.yml` — Prometheus config. Scrapes both exporters (RQ1 sim on 8000, RQ2 live on 8001) and loads the alert rules
- `grafana-dashboard.json` — Pre-built Grafana dashboard showing all metrics in real time (RQ1; RQ2 panels to be added once live data is confirmed)

The dataset contains 190 rows across six labelled phases, replayed at 1 row/second (~190 seconds total):

| Phase | Description | Health Status |
|-------|-------------|---------------|
| `normal_operation` | Clean flight data, no anomalies | Healthy (1) |
| `data_injection` | Tampered or injected data values | Fault (0) |
| `altitude_anomaly` | Abnormal altitude readings | Fault (0) |
| `speed_anomaly` | Abnormal speed readings | Fault (0) |
| `heading_anomaly` | Abnormal heading readings | Fault (0) |
| `combined_fault` | Multiple simultaneous anomalies | Fault (0) |

---

## Metrics exposed

| Metric | Type | Description |
|--------|------|-------------|
| `ras_altitude_m` | Gauge | Drone altitude (m) |
| `ras_speed_ms` | Gauge | Drone speed (m/s) |
| `ras_heading_deg` | Gauge | Drone heading (degrees) |
| `ras_latitude` | Gauge | GPS latitude |
| `ras_longitude` | Gauge | GPS longitude |
| `ras_anomaly_label` | Gauge | 0 = normal, 1 = anomaly |
| `ras_health_status` | Gauge | 1 = healthy, 0 = fault |
| `ras_fault_events_total` | Counter | Total healthy → fault transitions |

---

## Requirements

- Python + prometheus_client: `pip install prometheus_client`
- Python + djitellopy (RQ2 only, needs the physical drone): `pip install djitellopy`
- [Prometheus](https://prometheus.io/download) — download and extract
- [Grafana](https://grafana.com/grafana/download) — install with the Windows installer
- Drone Telemetry Tampering Dataset v2 CSV — download from [Kaggle](https://www.kaggle.com/datasets/rasikaekanayakadevlk/drone-telemetry-tampering-dataset-v2)
- DJI Tello drone, charged, powered on, with the laptop connected to its Wi-Fi access point (RQ2 only)

---

## How to run it (every time)

You need **3 things running** at the same time. Do them in order.

### 1. Start Prometheus

Open **cmd** and run:

```
cd "%USERPROFILE%\Downloads\prometheus-3.11.3.windows-amd64\prometheus-3.11.3.windows-amd64"
prometheus.exe --config.file=prometheus.yml
```

> Leave this window open. Prometheus runs in the background.  
> Open http://localhost:9090 to check it's working.

### 2. Start Grafana

Open a **new cmd window** and run:

```
net start grafana
```

> Open http://localhost:3000 and log in (admin / your password).  
> If you get "service already running" that's fine — it's already running.

### 3. Run the Python exporter

Open another **new cmd window** and run:

```
python "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\ras_exporter.py"
```

> The exporter will replay the dataset one row per second. Leave it running for the full ~190 seconds to cycle through all six phases.

---

## Running the RQ2 live drone path

Same 3-thing pattern, with the live exporter instead of (or alongside) the RQ1 one:

1. Start Prometheus and Grafana as above (the updated `prometheus.yml` now scrapes both exporters).
2. Connect your laptop to the Tello's Wi-Fi access point.
3. Run:

```
python "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\ras_exporter_live.py"
```

4. Check `http://localhost:8001/metrics` shows live numbers, then check the Prometheus targets page (`http://localhost:9090/targets`) shows `ras_drone_live` as **UP**.
5. Check `http://localhost:9090/alerts` to see the RQ2 alert rules and whether any are currently firing.

Both exporters can run at the same time (different ports), so RQ1 evidence stays reproducible while RQ2 work continues.

---

## Viewing the data

**Prometheus UI** — http://localhost:9090  
Type any of these in the search bar and click Graph:

| Query | What it shows |
|-------|--------------|
| `ras_health_status` | 1 = healthy, 0 = fault phase |
| `ras_anomaly_label` | Anomaly flag from dataset |
| `ras_altitude_m` | Drone altitude over time |
| `ras_speed_ms` | Drone speed over time |
| `ras_fault_events_total` | Total fault phase transitions detected |
| `rate(ras_fault_events_total[5m])` | Rate of fault events over 5-minute window |

> Set the time range to **5m** to see data clearly (default 1h is too wide).

**Grafana Dashboard** — http://localhost:3000  
Go to Dashboards → RAS Health Monitoring Dashboard. All eight metrics are shown on one screen including the health status panel, anomaly label, and fault event counter.

---

## Stopping everything

- **Prometheus** — close the cmd window
- **Grafana** — run `net stop grafana` in cmd
- **Exporter** — press `Ctrl+C` in its cmd window

---

## Repository

Thesis code and config: https://github.com/Dmatt547/RAS-monitoring-thesis.git