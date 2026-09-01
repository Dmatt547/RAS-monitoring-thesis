"""
Post-run alert collection and detection-latency analysis (Phase 2, RQ2.3).

Run this after every fault run. It replaces reading the Prometheus alerts page
and copying numbers into a notebook, which is slow and easy to get wrong.

Two timestamps are needed per run, and they come from different places:

  t_onset  the first sample in the raw 1 Hz telemetry log at which a metric
           crosses its threshold. Computed here from the session CSV using the
           values in prometheus/thresholds.json, so the onset calculation and
           the alerting rules cannot drift apart.

  t_alert  the moment Prometheus actually fired. Prometheus records its own
           alert state as a time series called ALERTS, so this is queried back
           out of Prometheus over the session's time window rather than being
           observed by hand while flying.

Detection latency is t_alert - t_onset, per the methodology. Measuring from the
operator's induction marker instead would fold in the aircraft's physical
response and the operator's reaction time, neither of which RQ2.3 asks about.
The operator marker is still reported alongside, as a check that each run's
fault was induced when intended.

Usage:
    python collect_alerts.py                    # newest session
    python collect_alerts.py FAULT-BAT-01       # one session
    python collect_alerts.py --all              # every session
    python collect_alerts.py --offline          # skip Prometheus, onset only

Writes <session>_alerts.csv beside the session's other files.
"""

import argparse
import csv
import json
import statistics as st
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SESSION_DIR = Path(__file__).parent / "sessions"
THRESHOLDS = Path(__file__).parent / "prometheus" / "thresholds.json"
PROM_URL = "http://localhost:9090"
HOLD_SEC = 5          # the `for:` duration on every rule in ras_alerts.rules.yml
STARTUP_GRACE_SEC = 10  # ignore alerts in the first seconds, before the exporter is up
QUERY_TIMEOUT_SEC = 10

# Which alert corresponds to which onset condition. The keys are the alert names
# in ras_alerts.rules.yml; the values are the label used in the onset report.
ALERT_ONSETS = {
    "DroneLowBattery": "battery",
    "DroneOverTemperature": "temperature",
    "DroneUnstableAttitude": "attitude",
    "DronePollFailure": "liveness",
}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def rolling_sd(values, window):
    out = []
    for i in range(len(values)):
        win = [v for v in values[max(0, i - window + 1):i + 1] if v is not None]
        out.append(st.pstdev(win) if len(win) > 1 else 0.0)
    return out


def rolling_dev(values, window, airborne, min_tof):
    """Full-window deviation, only where the entire window is airborne.

    Mirrors the guard on the alerting rule. A window still filling after takeoff
    has its mean dominated by ground readings, so the deviation measures the
    warm-up rather than the aircraft.
    """
    out = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        win = values[i - window + 1:i + 1]
        tof_win = airborne[i - window + 1:i + 1]
        if (any(v is None for v in win) or values[i] is None
                or any(t is None or t <= min_tof for t in tof_win)):
            out.append(None)
            continue
        out.append(abs(values[i] - st.mean(win)))
    return out


def compute_onsets(rows, th):
    """First SUSTAINED crossing of each monitored condition, plus transients.

    Onset is the first crossing that persists for at least the rule's `for:`
    duration. A stricter reading of the methodology would take the first raw
    crossing of any length, but that produces a latency figure that is not
    about detection: a one-sample excursion early in a flight cannot fire an
    alert, so subtracting its timestamp from a firing that happened minutes
    later measures the gap between two unrelated events.

    Baseline data forced this refinement. On BASE-01, a clean flight, pitch
    dispersion crossed its threshold for exactly one sample at t=29 s. Anchoring
    latency there would have been meaningless.

    Transient crossings are counted separately rather than discarded, because
    their frequency is itself worth reporting: they are near-misses that the
    hold duration is what suppresses.
    """
    iso = [r.get("timestamp_iso") for r in rows]
    el = [num(r.get("elapsed_sec")) for r in rows]
    bat = [num(r.get("bat")) for r in rows]
    temph = [num(r.get("temph")) for r in rows]
    tof = [num(r.get("tof")) for r in rows]
    baro = [num(r.get("baro")) for r in rows]
    pitch_sd = rolling_sd([num(r.get("pitch")) for r in rows], th["rolling_window_sec"])
    roll_sd = rolling_sd([num(r.get("roll")) for r in rows], th["rolling_window_sec"])
    baro_dev = rolling_dev(baro, th["drift_window_sec"], tof,
                           th["airborne_tof_cm"])

    onsets = {}
    transients = {}

    def first(label, predicate):
        """Walk the samples, grouping consecutive crossings into episodes."""
        episodes, run_start = [], None
        for i in range(len(rows)):
            try:
                crossing = bool(predicate(i))
            except (TypeError, KeyError):
                crossing = False
            if crossing and run_start is None:
                run_start = i
            elif not crossing and run_start is not None:
                episodes.append((run_start, i - 1))
                run_start = None
        if run_start is not None:
            episodes.append((run_start, len(rows) - 1))

        sustained = [e for e in episodes
                     if el[e[1]] is not None and el[e[0]] is not None
                     and (el[e[1]] - el[e[0]]) >= HOLD_SEC]
        transients[label] = len(episodes) - len(sustained)
        if sustained:
            i = sustained[0][0]
            onsets[label] = (iso[i], el[i])
        else:
            onsets[label] = None

    first("battery", lambda i: bat[i] is not None
          and bat[i] < th["battery_percent_min"])

    # One-sided: the fault direction for temperature is high. See the comment
    # on the rule in derive_thresholds.py.
    first("temperature", lambda i: temph[i] is not None and tof[i] is not None
          and tof[i] > th["airborne_tof_cm"] and temph[i] > th["temph_max"])

    first("attitude", lambda i: pitch_sd[i] > th["pitch_sd_max"]
          or roll_sd[i] > th["roll_sd_max"])

    # No barometer rule: the sensor has no stable inter-session reference, so
    # no threshold is derived from it. See derive_thresholds.py.

    # Liveness has no threshold: a missing sample is the condition. A gap in the
    # 1 Hz log means the exporter could not poll the aircraft.
    gap = None
    for i in range(1, len(el)):
        if el[i] is not None and el[i - 1] is not None and el[i] - el[i - 1] > 2.0:
            gap = (iso[i], el[i])
            break
    onsets["liveness"] = gap
    transients["liveness"] = 0

    return onsets, transients


def prom_query_range(query, start_ts, end_ts, step=1):
    """Query the Prometheus range API. Returns [] if Prometheus is unreachable."""
    params = urllib.parse.urlencode({
        "query": query, "start": start_ts, "end": end_ts, "step": f"{step}s"})
    url = f"{PROM_URL}/api/v1/query_range?{params}"
    try:
        with urllib.request.urlopen(url, timeout=QUERY_TIMEOUT_SEC) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  Could not reach Prometheus at {PROM_URL}: {exc}")
        print("  Start Prometheus and rerun, or use --offline for onset only.")
        return None
    if payload.get("status") != "success":
        print(f"  Prometheus returned an error: {payload.get('error')}")
        return None
    return payload["data"]["result"]


def collect_alerts(start_dt, end_dt):
    """When each alert first entered the firing state during the session."""
    # The window starts at the session, not before it. DronePollFailure fires
    # legitimately whenever no exporter is running, which is the normal state
    # between flights; counting those would inflate the false positive rate with
    # periods where there was no aircraft to monitor. The end is widened so an
    # alert that resolves shortly after landing is still captured.
    # A few seconds of grace at the start. The exporter binds its port a moment
    # after the session begins, so the first scrape or two can find nothing
    # there and raise a liveness alert against an aircraft that is present and
    # about to report. That is an artefact of process startup rather than a
    # false positive, and counting it would misstate the rate.
    start_ts = start_dt.timestamp() + STARTUP_GRACE_SEC
    # Clamp the end to the session as well. The exporter stops when the session
    # does, so a liveness alert raised after the last sample is reporting the
    # harness shutting down rather than anything about the aircraft.
    end_ts = end_dt.timestamp()
    result = prom_query_range('ALERTS{alertstate="firing"}', start_ts, end_ts)
    if result is None:
        return None

    fired = {}
    for series in result:
        name = series["metric"].get("alertname", "?")
        stamps = [float(v[0]) for v in series["values"]]
        if not stamps:
            continue
        first, last = min(stamps), max(stamps)
        if name not in fired or first < fired[name]["first"]:
            fired[name] = {"first": first, "last": last, "samples": len(stamps)}
        else:
            fired[name]["last"] = max(fired[name]["last"], last)
            fired[name]["samples"] += len(stamps)
    return fired


def analyse(telemetry_path, offline):
    base = str(telemetry_path).replace("_telemetry.csv", "")
    events_path = Path(base + "_events.csv")
    meta_path = Path(base + "_metadata.csv")
    out_path = Path(base + "_alerts.csv")

    rows = load_rows(telemetry_path)
    if not rows:
        print(f"{telemetry_path.name}: empty")
        return

    meta = {}
    if meta_path.exists():
        meta = {r["key"]: r["value"] for r in load_rows(meta_path)}

    th = json.loads(THRESHOLDS.read_text())
    onsets, transients = compute_onsets(rows, th)

    start_dt = datetime.fromisoformat(rows[0]["timestamp_iso"])
    end_dt = datetime.fromisoformat(rows[-1]["timestamp_iso"])

    print(f"\n=== {Path(base).name} ===")
    print(f"  mode: {meta.get('mode', 'unknown')}   "
          f"battery: {meta.get('battery_id', '?')}   "
          f"duration: {rows[-1].get('elapsed_sec')}s")

    # operator marker, t_induce
    induce = None
    if events_path.exists():
        for e in load_rows(events_path):
            if e["event"] == "operator_marker":
                induce = (e["timestamp_iso"], float(e["elapsed_sec"]))
                break
    print(f"  t_induce (operator marker): "
          f"{f'{induce[1]:.1f}s' if induce else 'none recorded'}")

    fired = None if offline else collect_alerts(start_dt, end_dt)

    print(f"\n  {'alert':<24}{'t_onset':>9}{'t_alert':>9}{'latency':>9}{'transient':>10}  outcome")
    out_rows = []
    for alert, key in ALERT_ONSETS.items():
        onset = onsets.get(key)
        onset_el = onset[1] if onset else None

        alert_el = None
        if fired and alert in fired:
            alert_el = fired[alert]["first"] - start_dt.timestamp()

        if alert_el is not None and onset_el is not None:
            latency = alert_el - onset_el
            outcome = "fired"
        elif alert_el is not None:
            latency = None
            outcome = "fired, no onset in telemetry"
        elif onset_el is not None:
            latency = None
            outcome = "MISSED - threshold crossed, no alert" if not offline else "onset only"
        else:
            latency = None
            outcome = "-"

        print(f"  {alert:<24}"
              f"{(f'{onset_el:.0f}s' if onset_el is not None else '-'):>9}"
              f"{(f'{alert_el:.0f}s' if alert_el is not None else '-'):>9}"
              f"{(f'{latency:.0f}s' if latency is not None else '-'):>9}"
              f"{transients.get(key, 0):>10}"
              f"  {outcome}")

        out_rows.append({
            "session": Path(base).name,
            "mode": meta.get("mode", ""),
            "alert": alert,
            "t_onset_elapsed_sec": f"{onset_el:.1f}" if onset_el is not None else "",
            "t_onset_iso": onset[0] if onset else "",
            "t_alert_elapsed_sec": f"{alert_el:.1f}" if alert_el is not None else "",
            "detection_latency_sec": f"{latency:.1f}" if latency is not None else "",
            "t_induce_elapsed_sec": f"{induce[1]:.1f}" if induce else "",
            "transient_crossings": transients.get(key, 0),
            "outcome": outcome,
        })

    if offline:
        print("\n  (offline: t_alert not collected - start Prometheus and rerun)")

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"\n  wrote {out_path.name}")


def main():
    ap = argparse.ArgumentParser(description="Collect alerts and compute detection latency.")
    ap.add_argument("session_id", nargs="?", help="e.g. FAULT-BAT-01 (default: newest)")
    ap.add_argument("--all", action="store_true", help="every session")
    ap.add_argument("--offline", action="store_true",
                    help="skip Prometheus; compute t_onset only")
    args = ap.parse_args()

    if not THRESHOLDS.exists():
        print(f"No {THRESHOLDS.name}. Run derive_thresholds.py first.")
        sys.exit(1)

    files = sorted(SESSION_DIR.glob("*_telemetry.csv"))
    if not files:
        print("No sessions found.")
        sys.exit(1)

    if args.all:
        targets = files
    elif args.session_id:
        targets = [f for f in files if f.name.startswith(args.session_id)]
        if not targets:
            print(f"No session matching '{args.session_id}'.")
            sys.exit(1)
    else:
        targets = [files[-1]]

    for f in targets:
        analyse(f, args.offline)


if __name__ == "__main__":
    main()
