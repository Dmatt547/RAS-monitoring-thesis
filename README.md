# RAS Health Monitoring — Thesis Simulation

Simulates telemetry from a Remote Autonomous System (drone) and monitors it using Prometheus and Grafana. Built for the thesis: **"Monitoring the Health and Reliability of Remote Autonomous Systems"**.

## What it does

- `ras_exporter.py` — Python script that simulates RAS metrics (battery, signal, temperature, packet loss) and exposes them to Prometheus
- `prometheus.yml` — Prometheus config that scrapes the exporter every 5 seconds
- `grafana-dashboard.json` — Pre-built Grafana dashboard showing all metrics in real time

Faults are automatically injected during the simulation:
- **60s** — rapid battery drain
- **120s** — signal degradation
- **180s** — CPU overheating
- **240s** — system recovery

---

## Requirements

- Python + prometheus_client: `pip install prometheus_client`
- [Prometheus](https://prometheus.io/download) — download and extract to your Downloads folder
- [Grafana](https://grafana.com/grafana/download) — install with the Windows installer

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

> You'll see metrics printing every 10 seconds. Leave this running.

---

## Viewing the data

**Prometheus UI** — http://localhost:9090  
Type any of these in the search bar and click Graph:

| Query | What it shows |
|-------|--------------|
| `ras_battery_percent` | Battery level over time |
| `ras_signal_rssi_dbm` | Signal strength (dBm) |
| `ras_cpu_temperature_c` | CPU temperature |
| `ras_health_status` | 1 = healthy, 0 = fault |
| `ras_packet_loss_percent` | Network packet loss |
| `ras_battery_percent < 15` | Fault detection — critical battery |
| `ras_signal_rssi_dbm < -80` | Fault detection — weak signal |
| `ras_cpu_temperature_c > 60` | Fault detection — overheating |
| `ras_health_status == 0` | Only returns data when a fault is active |

> Set the time range to **5m** to see data clearly (default 1h is too wide).

**Grafana Dashboard** — http://localhost:3000  
Go to Dashboards → RAS Health Monitoring Dashboard. All metrics are shown on one screen with the fault events counter and battery gauge.

---

## Stopping everything

- **Prometheus** — just close the cmd window
- **Grafana** — run `net stop grafana` in cmd
- **Exporter** — press `Ctrl+C` in its cmd window
