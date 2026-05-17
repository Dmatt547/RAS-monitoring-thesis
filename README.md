# RAS Health Monitoring — Thesis (T1 2026)

Monitors the health of a Remote Autonomous System (drone) using Prometheus and Grafana. Built for the thesis: **"Monitoring the Health and Reliability of Remote Autonomous Systems"**.

This repository covers **RQ1 (Trimester 1)**: validating a Prometheus-based monitoring pipeline using real drone telemetry replayed from the [Drone Telemetry Tampering Dataset v2](https://www.kaggle.com/datasets/rasikaekanayakadevlk/drone-telemetry-tampering-dataset-v2) (Kaggle). Physical DJI Tello drone integration is planned for RQ2 in Trimester 2.

## What it does

- `ras_exporter.py` — Python script that replays drone telemetry from a CSV dataset row by row and exposes the metrics to Prometheus via HTTP on port 8000
- `prometheus.yml` — Prometheus config that scrapes the exporter every 15 seconds
- `grafana-dashboard.json` — Pre-built Grafana dashboard showing all metrics in real time

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
- [Prometheus](https://prometheus.io/download) — download and extract
- [Grafana](https://grafana.com/grafana/download) — install with the Windows installer
- Drone Telemetry Tampering Dataset v2 CSV — download from [Kaggle](https://www.kaggle.com/datasets/rasikaekanayakadevlk/drone-telemetry-tampering-dataset-v2)

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