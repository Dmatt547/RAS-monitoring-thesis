"""
Post-flight session validator.

Run this immediately after every session, before packing up. It checks whether
the session is usable as evidence, so a bad run is caught while you are still
at the flight site and can re-fly it, rather than at your desk that night.

Usage:
    python check_session.py                     # validate the newest session
    python check_session.py BASE-01             # validate by session ID
    python check_session.py --all               # summarise every session

Exit code is 0 if the session passes, 1 if it fails.
"""

import argparse
import csv
import re
import statistics
import sys
from pathlib import Path

SESSION_DIR = Path(__file__).parent / "sessions"

# Thresholds for a usable session. These are data-quality gates, not fault
# thresholds - they say whether the measurement worked, not whether the drone
# was healthy.
MIN_SAMPLE_COVERAGE = 0.99   # >=99% of expected 1 Hz samples present
MAX_GAP_SEC = 3.0            # no gap longer than this between samples
MIN_SNR_COVERAGE = 0.90      # >=90% of rows carry an SNR value
MAX_SNR_AGE_SEC = 30.0       # SNR polls are starved by blocking flight commands;
                             # 23s observed in BASE-01, which is expected, not a fault
MIN_FLIGHT_SEC = 60.0        # anything shorter is not a baseline session
MIN_START_BATTERY = 80       # start below this and the session is not comparable


class Check:
    def __init__(self):
        self.rows = []

    def add(self, ok, label, detail):
        self.rows.append((ok, label, detail))

    def report(self):
        width = max(len(l) for _, l, _ in self.rows)
        for ok, label, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {label.ljust(width)}  {detail}")
        return all(ok for ok, _, _ in self.rows)


def load(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def num(row, key):
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return None


def validate(telemetry_path):
    events_path = Path(str(telemetry_path).replace("_telemetry.csv", "_events.csv"))
    meta_path = Path(str(telemetry_path).replace("_telemetry.csv", "_metadata.csv"))

    print(f"\n=== {telemetry_path.name} ===")
    rows = load(telemetry_path)
    c = Check()

    if not rows:
        print("  [FAIL] file is empty")
        return False

    elapsed = [num(r, "elapsed_sec") for r in rows]
    elapsed = [e for e in elapsed if e is not None]
    duration = elapsed[-1] - elapsed[0]

    # --- duration -----------------------------------------------------------
    c.add(duration >= MIN_FLIGHT_SEC, "duration",
          f"{duration:.0f}s")

    # --- sample coverage ----------------------------------------------------
    expected = int(duration) + 1
    coverage = len(rows) / expected if expected else 0
    c.add(coverage >= MIN_SAMPLE_COVERAGE, "sample coverage",
          f"{len(rows)} rows / {expected} expected ({coverage:.1%})")

    # --- gaps ---------------------------------------------------------------
    gaps = [(elapsed[i] - elapsed[i - 1]) for i in range(1, len(elapsed))]
    worst = max(gaps) if gaps else 0
    n_bad = sum(1 for g in gaps if g > MAX_GAP_SEC)
    c.add(worst <= MAX_GAP_SEC, "no sample gaps",
          f"worst {worst:.1f}s, {n_bad} over {MAX_GAP_SEC}s")

    # --- battery monotonicity ----------------------------------------------
    bats = [num(r, "bat") for r in rows]
    bats = [b for b in bats if b is not None]
    if bats:
        rises = sum(1 for i in range(1, len(bats)) if bats[i] > bats[i - 1] + 1)
        drop = bats[0] - bats[-1]
        c.add(rises == 0 and drop > 0, "battery depletes",
              f"{bats[0]:.0f}% -> {bats[-1]:.0f}% (drop {drop:.0f}%), "
              f"{rises} anomalous rises")
        c.add(bats[0] >= MIN_START_BATTERY, "full battery at start",
              f"{bats[0]:.0f}% (need >={MIN_START_BATTERY}%)")
        rate = (drop / duration * 60) if duration else 0
        print(f"         depletion rate: {rate:.1f} %/min")
    else:
        c.add(False, "battery depletes", "no battery values")

    # --- SNR ----------------------------------------------------------------
    snr_vals = [r.get("snr_db", "") for r in rows]
    have = sum(1 for v in snr_vals if v not in ("", None))
    snr_cov = have / len(rows)
    c.add(snr_cov >= MIN_SNR_COVERAGE, "snr coverage",
          f"{have}/{len(rows)} rows ({snr_cov:.1%})")

    ages = [num(r, "snr_age_sec") for r in rows]
    ages = [a for a in ages if a is not None]
    if ages:
        c.add(max(ages) <= MAX_SNR_AGE_SEC, "snr freshness",
              f"max age {max(ages):.1f}s")

    # --- manoeuvre step coverage -------------------------------------------
    labels = {r.get("step_label") for r in rows}
    required = {"takeoff", "hover_1", "translate", "rotate", "hover_2", "land"}
    missing = required - labels
    c.add(not missing, "all steps flown",
          "complete" if not missing else f"missing {sorted(missing)}")

    # --- events -------------------------------------------------------------
    meta = {}
    if meta_path.exists():
        meta = {r["key"]: r["value"] for r in load(meta_path)}
    if events_path.exists():
        evs = load(events_path)
        stop = [e for e in evs if e["event"] == "stop_reason"]
        # In battery mode the aircraft lands itself when its failsafe engages, so
        # the harness's own land command afterwards necessarily fails. That is
        # the expected end of a depletion run, not an aborted session.
        mode = meta.get("mode", "")
        ignorable = {"land_failed"} if mode == "battery" else set()
        aborts = [e for e in evs
                  if e["event"] in ("operator_abort", "error", "land_failed")
                  and e["event"] not in ignorable]
        c.add(not aborts, "clean session",
              "no aborts" if not aborts else f"{[a['event'] for a in aborts]}")
        if stop:
            print(f"         stop reason: {stop[0]['detail']}")
    else:
        c.add(False, "events file", "missing")

    # --- metadata -----------------------------------------------------------
    if meta_path.exists():
        meta = {r["key"]: r["value"] for r in load(meta_path)}
        needed = ["venue", "environment", "ambient_temp_c", "battery_id"]
        blank = [k for k in needed if not meta.get(k)]
        c.add(not blank, "metadata complete",
              "complete" if not blank else f"blank: {blank}")
    else:
        c.add(False, "metadata file", "missing")

    # --- descriptive summary (not a pass/fail) ------------------------------
    ok = c.report()
    print("\n  Baseline ranges observed:")
    for field, unit in [("temph", "C"), ("templ", "C"), ("h", "cm"),
                        ("baro", "cm"), ("pitch", "deg"), ("roll", "deg")]:
        vals = [num(r, field) for r in rows]
        vals = [v for v in vals if v is not None]
        if vals:
            print(f"    {field:<7} min {min(vals):>8.1f}  "
                  f"median {statistics.median(vals):>8.1f}  "
                  f"max {max(vals):>8.1f}  {unit}")

    print(f"\n  => {'USABLE' if ok else 'RE-FLY THIS SESSION'}")
    return ok


def _session_time(path):
    """Sort key: the YYYYMMDD_HHMMSS stamp embedded in the filename.

    Sorting the glob alphabetically ranks by session ID first, so FP-03 sorts
    after FAULT-BAT-01 and "the newest session" resolves to the wrong run. The
    timestamp is the only part of the name that orders sessions correctly.
    """
    m = re.search(r"_(\d{8}_\d{6})_", path.name)
    return (m.group(1) if m else "", path.name)

def main():
    ap = argparse.ArgumentParser(description="Validate a flight session.")
    ap.add_argument("session_id", nargs="?", help="e.g. BASE-01 (default: newest)")
    ap.add_argument("--all", action="store_true", help="validate every session")
    args = ap.parse_args()

    if not SESSION_DIR.exists():
        print(f"No sessions directory at {SESSION_DIR}")
        sys.exit(1)

    files = sorted(SESSION_DIR.glob("*_telemetry.csv"), key=_session_time)
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

    results = [validate(f) for f in targets]
    if len(results) > 1:
        print(f"\n{sum(results)}/{len(results)} sessions usable.")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
