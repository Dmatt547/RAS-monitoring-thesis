# RAS Health Monitoring — Thesis Code

"Monitoring the Health and Reliability of Remote Autonomous Systems"
Daniel Mattioli · Deakin Honours · Supervisor: Kevin Lee

---

## Folder layout

```
Code/
  flight_session.py       1. fly a session          <- run these three,
  check_session.py        2. check it                  in this order
  derive_thresholds.py    3. derive thresholds

  sessions/               your flight data (the evidence)
  prometheus/             prometheus.yml, alert rules, grafana dashboard
  docs/                   BASELINE_RUNSHEET.md — how to run a flight day
  study1-rq1/             Trimester 1, finished — dataset replay exporter
  archive/                superseded, kept for reference only
```

Start with `docs/BASELINE_RUNSHEET.md`.

---

## The three scripts

**`flight_session.py`** — flies the fixed manoeuvre script, logs telemetry at
1 Hz, writes event markers, prompts for session metadata, and exports to
Prometheus on port 8001. One process holds the drone, so this replaces the old
`ras_exporter_live.py` entirely.

```
python flight_session.py                # a real session
python flight_session.py --dry          # no motors, verify logging
```

Writes three files per session into `sessions/`:

| File | What it is |
|---|---|
| `_telemetry.csv` | the 1 Hz log — this is the data |
| `_events.csv` | manoeuvre step and stop-reason timestamps — needed for Phase 2 latency |
| `_metadata.csv` | venue, ambient temp, battery ID — explains session-to-session differences |

**`check_session.py`** — run straight after landing. Checks sample coverage,
gaps, battery, SNR, step coverage and metadata. Ends with USABLE or RE-FLY.

```
python check_session.py                 # newest session
python check_session.py --all           # all of them
```

**`derive_thresholds.py`** — pools every BASE-* session and applies the four
derivation rules from the methodology. Prints the threshold table and writes
`prometheus/ras_alerts.derived.yml`.

---

## Where things stand

- **Study 1 (RQ1, Trimester 1, done)** — Prometheus pipeline validated against
  replayed telemetry with pre-labelled health status. Code in `study1-rq1/`.
- **Study 2 (RQ2, current)** — physical Tello, raw unlabelled telemetry,
  Prometheus alert rules detecting faults on their own.
  - Phase 1 baseline: in progress
  - Phase 2 fault injection: not started
  - `prometheus/ras_alerts.rules.yml` still holds placeholder thresholds.
    Replace it with the derived file once all five baseline sessions are in.

---

## Requirements

```
pip install djitellopy prometheus_client
```

Prometheus is only needed for Phase 2. Phase 1 baseline collection writes CSVs
and needs nothing running.

Repo: https://github.com/Dmatt547/RAS-monitoring-thesis.git
