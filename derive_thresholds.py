"""
Derive Phase 2 alert thresholds from the pooled Phase 1 baseline sessions.

Implements the four metric classes from the methodology's threshold derivation
table. Each class gets its own rule because the metrics behave differently:

  Monotonic  (battery)         -> depletion rate, per battery, worst case
  Settling   (temperature)     -> 99th percentile of the settled region only
  (barometer)                  -> reported only, no rule. See below.
  Variance   (attitude, accel) -> 99th percentile of 5s rolling std dev
  Liveness   (up, absent)      -> binary, nothing to derive

Barometer carries no rule. It was first treated as a bounded metric, then as a
drift metric once the absolute reading proved to track atmospheric pressure
rather than the aircraft. Neither survives contact with the data. The absolute
reference is re-established at each power cycle and moved 165 cm across eight
sessions flown on the same floor, so readings are not comparable between
sessions. Within a session the drift is not stable either: per-session 99th
percentiles across the five baselines span 0.118 to 0.337 cm, a threefold range,
and a held-out normal flight reached 0.873 cm and raised a false alert against a
threshold of 0.31 cm derived from that pooled distribution.

The conclusion parallels the one reached for Wi-Fi SNR by the opposite route.
SNR offers no variance to threshold; the barometer offers too much, with no
stable reference to measure it against. Neither supports threshold-based
detection on this platform, and both are reported as findings rather than
worked around.

Temperature is a settling metric, not a bounded one. It trends toward a steady
operating value rather than varying about a fixed mean: an aircraft starting from
ambient warms from roughly 56 C to 62 C over four minutes, and one starting warm
cools to the same point. Most samples in a four-minute session therefore come
from the warm-up transient rather than from normal steady operation, and pooling
them pulls the percentile below the settled range. Deriving from the whole
session gave a ceiling of 63 C, which sits inside the 62-64 C band the aircraft
occupies once settled, and a held-out normal flight crossed it. The threshold is
therefore taken from the settled region only.

Time-of-flight gets no rule. Its upper tail comes from the aircraft passing over
lower floor area in one particular room, which is a property of the venue and
does not generalise. It is reported as a limitation instead.

Only in-flight samples are pooled. Preflight, takeoff, land and postflight are
excluded: the drone is on the ground or transitioning, so those samples are not
drawn from the normal-operation distribution the thresholds describe.

Outputs a threshold table for the thesis and writes ras_alerts.derived.yml,
which you review and then copy over ras_alerts.rules.yml.

Usage:
    python derive_thresholds.py
"""

import csv
import json
import statistics as st
from pathlib import Path

SESSION_DIR = Path(__file__).parent / "sessions"
OUT_RULES = Path(__file__).parent / "prometheus" / "ras_alerts.derived.yml"
OUT_JSON = Path(__file__).parent / "prometheus" / "thresholds.json"

EXCLUDE_STEPS = {"preflight", "postflight", "takeoff", "land"}
ROLLING_WINDOW = 5      # seconds, per the methodology
SAFETY_MARGIN_MIN = 2.0 # minutes of lead time wanted before the auto-land point
TELLO_AUTOLAND_PCT = 10 # the firmware's own low-battery landing point

BOUNDED = []                 # no metric currently qualifies as stationary
SETTLING = ["temph", "templ"]
SETTLE_TAIL_SEC = 90         # the settled region: last 90 s of each session
DRIFT = []                   # barometer removed: see the module docstring
REPORT_ONLY = ["tof", "baro"]  # measured and reported, but no rule derived
DRIFT_WINDOW = 60            # seconds; matches the PromQL avg_over_time window
AIRBORNE_TOF_CM = 20         # rules that only apply in flight are gated on this
VARIANCE = ["pitch", "roll", "agx", "agy", "agz"]   # yaw excluded: wraps at 360


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def rolling_sd(values, window):
    out = []
    for i in range(len(values)):
        win = [v for v in values[max(0, i - window + 1):i + 1] if v is not None]
        out.append(st.pstdev(win) if len(win) > 1 else 0.0)
    return out


def rolling_dev(values, window):
    """|value - mean of the trailing window|, for FULL windows only.

    This is what a Prometheus `abs(metric - avg_over_time(metric[60s]))`
    expression computes, so the threshold derived here is directly comparable
    to what the alerting rule evaluates at runtime.

    Partial windows are skipped. While the window is still filling, the mean is
    dominated by whatever preceded the current flight regime, so the deviation
    measures the warm-up rather than the aircraft: on BASE-01 it read 0.68 cm
    just after takeoff and settled to under 0.3 cm once the window was full.
    Including those samples would inflate the threshold; evaluating the rule
    during that period produces a false positive. The rule therefore carries a
    matching guard requiring the whole window to be airborne.
    """
    out = []
    for i in range(len(values)):
        if i + 1 < window:
            continue
        win = values[i - window + 1:i + 1]
        if any(v is None for v in win) or values[i] is None:
            continue
        out.append(abs(values[i] - st.mean(win)))
    return out


def pct(values, p):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    i = (len(vals) - 1) * p / 100
    lo, hi = int(i), min(int(i) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)


def main():
    files = sorted(SESSION_DIR.glob("BASE-*_telemetry.csv"))
    if not files:
        print("No BASE-* sessions found.")
        return

    pooled = {k: [] for k in BOUNDED + SETTLING + REPORT_ONLY}
    pooled_settled = {k: [] for k in SETTLING}
    pooled_sd = {k: [] for k in VARIANCE}
    pooled_drift = {k: [] for k in DRIFT}
    per_battery = {}
    sessions = []

    for path in files:
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        meta_path = Path(str(path).replace("_telemetry.csv", "_metadata.csv"))
        meta = {}
        if meta_path.exists():
            with open(meta_path, newline="") as f:
                meta = {r["key"]: r["value"] for r in csv.DictReader(f)}

        flight = [r for r in rows if r.get("step_label") not in EXCLUDE_STEPS]
        sid = meta.get("session_id", path.name[:7])
        batt_id = meta.get("battery_id") or "UNKNOWN"

        # bounded and report-only metrics: pool raw in-flight samples
        for k in BOUNDED + SETTLING + REPORT_ONLY:
            pooled[k].extend(num(r.get(k)) for r in flight)

        # settling metrics: pool only the settled tail of the session, where the
        # warm-up transient has finished and the value has reached its operating
        # point. Including the transient pulls the percentile below the range the
        # aircraft actually occupies in steady operation.
        els = [num(x.get("elapsed_sec")) for x in flight]
        end = max((e for e in els if e is not None), default=0)
        for k in SETTLING:
            pooled_settled[k].extend(
                num(x.get(k)) for x, e in zip(flight, els)
                if e is not None and e > end - SETTLE_TAIL_SEC)

        # drift metrics: deviation from own rolling mean, computed per session
        for k in DRIFT:
            pooled_drift[k].extend(
                rolling_dev([num(r.get(k)) for r in flight], DRIFT_WINDOW))

        # variance metrics: rolling SD computed per session, then pooled
        for k in VARIANCE:
            pooled_sd[k].extend(rolling_sd([num(r.get(k)) for r in flight],
                                           ROLLING_WINDOW))

        # depletion rate: whole session, including ground time
        bats = [num(r.get("bat")) for r in rows]
        bats = [b for b in bats if b is not None]
        els = [num(r.get("elapsed_sec")) for r in rows]
        els = [e for e in els if e is not None]
        rate = None
        if bats and els and els[-1] > 0:
            rate = (bats[0] - bats[-1]) / els[-1] * 60
            per_battery.setdefault(batt_id, []).append(rate)

        sessions.append((sid, batt_id, len(rows), els[-1] if els else 0,
                         bats[0] if bats else None, bats[-1] if bats else None,
                         rate, meta.get("ambient_temp_c", "")))

    # ---------------- report ----------------
    print("=" * 74)
    print("PHASE 1 BASELINE — POOLED THRESHOLD DERIVATION")
    print("=" * 74)
    n_pooled = len([x for x in pooled["temph"] if x is not None])
    print(f"\n{len(files)} sessions, {n_pooled} pooled in-flight samples\n")

    print("Sessions")
    print(f"  {'ID':<9}{'batt':<7}{'rows':>6}{'dur_s':>8}{'bat%':>12}"
          f"{'%/min':>9}{'ambient':>9}")
    for sid, b, n, d, b0, b1, rate, amb in sessions:
        span = f"{b0:.0f}->{b1:.0f}" if b0 is not None else "-"
        print(f"  {sid:<9}{b:<7}{n:>6}{d:>8.0f}{span:>12}"
              f"{(f'{rate:.2f}' if rate else '-'):>9}{amb:>9}")

    print("\n--- Bounded metrics: pooled 1st / 99th percentile ---")
    bounds = {}
    for k in BOUNDED:
        v = [x for x in pooled[k] if x is not None]
        if not v:
            continue
        p1, p50, p99 = pct(v, 1), pct(v, 50), pct(v, 99)
        bounds[k] = (p1, p99)
        print(f"  {k:<7} n={len(v):>5}   p1 {p1:>8.2f}   median {p50:>8.2f}   p99 {p99:>8.2f}")

    print(f"\n--- Settling metrics: p99 of the last {SETTLE_TAIL_SEC}s of each session ---")
    settled = {}
    for k in SETTLING:
        v = [x for x in pooled_settled[k] if x is not None]
        allv = [x for x in pooled[k] if x is not None]
        if not v:
            continue
        settled[k] = pct(v, 99)
        print(f"  {k:<7} settled n={len(v):>4}  p50 {pct(v,50):>6.1f}  p99 {settled[k]:>6.1f}"
              f"   (whole-session p99 was {pct(allv,99):.1f})")
    print("  (the whole-session percentile is depressed by the warm-up transient)")

    print(f"\n--- Drift metrics: p99 of |value - {DRIFT_WINDOW}s rolling mean| ---")
    drift = {}
    for k in DRIFT:
        v = pooled_drift[k]
        if not v:
            continue
        drift[k] = pct(v, 99)
        print(f"  {k:<7} n={len(v):>5}   p99 {drift[k]:>8.3f}   max {max(v):>8.3f}")
    print("  (the absolute value is not used: it tracks atmospheric pressure,"
          " not the platform)")

    print("\n--- Reported only, no rule derived ---")
    for k in REPORT_ONLY:
        v = [x for x in pooled[k] if x is not None]
        if v:
            print(f"  {k:<7} p1 {pct(v,1):>7.1f}   median {pct(v,50):>7.1f}"
                  f"   p99 {pct(v,99):>7.1f}")
    print("  (tof upper tail reflects the venue floor, not the aircraft;")
    print("   baro has no stable inter-session reference, so no rule is derived)")

    print(f"\n--- Variance metrics: p99 of {ROLLING_WINDOW}s rolling std dev ---")
    var = {}
    for k in VARIANCE:
        v = [x for x in pooled_sd[k] if x is not None]
        if not v:
            continue
        var[k] = pct(v, 99)
        print(f"  {k:<7} n={len(v):>5}   p99 {var[k]:>8.2f}   max {max(v):>8.2f}")
    print("  (yaw excluded: wraps 0-359 during the rotate step, so its raw"
          " standard deviation is meaningless)")

    print("\n--- Battery depletion, per battery ---")
    worst = None
    for bid, rates in sorted(per_battery.items()):
        mean = st.mean(rates)
        print(f"  {bid:<8} n={len(rates)}   mean {mean:.2f} %/min   "
              f"runs: {', '.join(f'{r:.2f}' for r in rates)}")
        worst = mean if worst is None else max(worst, mean)
    batt_threshold = None
    if worst:
        batt_threshold = TELLO_AUTOLAND_PCT + worst * SAFETY_MARGIN_MIN
        print(f"\n  worst-case rate {worst:.2f} %/min")
        print(f"  threshold = {TELLO_AUTOLAND_PCT}% auto-land point "
              f"+ {SAFETY_MARGIN_MIN:.0f} min lead x {worst:.2f} %/min "
              f"= {batt_threshold:.0f}%")

    # ---------------- emit rules ----------------
    def g(k, i):
        return bounds[k][i] if k in bounds else None

    lines = [
        "# RQ2 Prometheus alerting rules - DERIVED from Phase 1 baseline data.",
        f"# Generated by derive_thresholds.py from {len(files)} baseline sessions.",
        "# Every threshold below traces to a stated derivation rule; none is assumed.",
        "",
        "groups:",
        "  - name: ras_fault_detection",
        "    rules:",
    ]

    if batt_threshold:
        lines += [
            "      - alert: DroneLowBattery",
            f"        expr: ras_battery_percent < {batt_threshold:.0f}",
            "        for: 5s",
            "        labels:",
            "          severity: warning",
            "        annotations:",
            "          summary: \"Battery approaching the auto-land point\"",
            f"          description: \"Below {batt_threshold:.0f}% - roughly "
            f"{SAFETY_MARGIN_MIN:.0f} min of lead time at the worst observed "
            f"depletion rate of {worst:.2f} %/min.\"",
            "",
        ]

    if "temph" in settled:
        # One-sided, per the "per metric direction" clause of the derivation
        # table. The fault direction for temperature is high; no mechanism on
        # this platform produces an under-temperature fault. A lower bound at
        # the 1st percentile only adds a false positive source: the aircraft is
        # still shedding power-on heat for the first seconds after takeoff, and
        # baseline BASE-01 sat at 56 C for six consecutive seconds there, which
        # a two-sided rule would have fired on with the 5 s hold.
        #
        # Gated on being airborne. Thresholds come from in-flight samples, but
        # 12% of ground samples exceed the ceiling on a healthy aircraft, so
        # without the gate the rule fires before every takeoff.
        gate = f" and on() ras_tof_cm > {AIRBORNE_TOF_CM}"
        lines += [
            "      - alert: DroneOverTemperature",
            f"        expr: (ras_temperature_high_c > {settled['temph']:.0f}){gate}",
            "        for: 5s",
            "        labels:",
            "          severity: warning",
            "        annotations:",
            "          summary: \"Onboard temperature above the in-flight baseline\"",
            f"          description: \"Above the 99th percentile of the settled "
            f"region of normal flight, {settled['temph']:.0f} C. Derived from the "
            f"last {SETTLE_TAIL_SEC}s of each baseline session, because the "
            f"aircraft warms toward an operating point and the earlier transient "
            f"would depress the percentile below the range it actually occupies. "
            f"One-sided: the fault direction for "
            f"temperature is high. Evaluated only while airborne, because the "
            f"Tello is hottest at power-on and cools under rotor airflow, so "
            f"ground samples sit above the in-flight range on a healthy "
            f"aircraft.\"",
            "",
        ]

    if "pitch" in var and "roll" in var:
        lines += [
            "      - alert: DroneUnstableAttitude",
            f"        expr: stddev_over_time(ras_pitch_deg[{ROLLING_WINDOW}s]) > "
            f"{var['pitch']:.2f} or stddev_over_time(ras_roll_deg[{ROLLING_WINDOW}s]) > "
            f"{var['roll']:.2f}",
            "        for: 5s",
            "        labels:",
            "          severity: warning",
            "        annotations:",
            "          summary: \"Attitude dispersion above baseline\"",
            f"          description: \"Rolling {ROLLING_WINDOW}s standard deviation "
            "exceeded the 99th percentile of normal flight - controlled manoeuvring "
            "does not disperse this much.\"",
            "",
        ]

    if "baro" in drift:
        # Drift, not position. The absolute reading tracks atmospheric pressure
        # and moved several cm between sessions in one indoor room, so a pooled
        # percentile band would encode the weather. Deviation from the metric's
        # own recent mean is comparable across sessions.
        lines += [
            "      - alert: DroneBarometricDrift",
            f"        expr: abs(ras_barometer_cm - "
            f"avg_over_time(ras_barometer_cm[{DRIFT_WINDOW}s])) > {drift['baro']:.2f}"
            f" and on() min_over_time(ras_tof_cm[{DRIFT_WINDOW}s]) > {AIRBORNE_TOF_CM}",
            "        for: 5s",
            "        labels:",
            "          severity: warning",
            "        annotations:",
            "          summary: \"Barometric reading drifting from its own recent mean\"",
            f"          description: \"Deviation from the {DRIFT_WINDOW}s rolling "
            f"mean exceeded {drift['baro']:.2f} cm, the 99th percentile of normal "
            f"flight. The absolute reading is not used: it tracks atmospheric "
            f"pressure rather than the aircraft. Evaluated only once the whole "
            f"{DRIFT_WINDOW}s window is airborne data, since a window still "
            f"filling after takeoff measures the warm-up, not the aircraft.\"",
            "",
        ]

    lines += [
        "      - alert: DronePollFailure",
        "        expr: ras_last_poll_success == 0 or up{job=\"ras_drone_live\"} == 0",
        "        for: 2s",
        "        labels:",
        "          severity: critical",
        "        annotations:",
        "          summary: \"Lost contact with the drone\"",
        "          description: \"Liveness is binary and needs no derivation: "
        "missing data is itself the fault condition.\"",
        "",
    ]

    OUT_RULES.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Machine-readable copy of the same numbers. collect_alerts.py reads this to
    # work out t_onset, so the onset calculation and the alerting rules cannot
    # drift apart: both come from this one derivation run.
    OUT_JSON.write_text(json.dumps({
        "sessions": len(files),
        "pooled_in_flight_samples": n_pooled,
        "rolling_window_sec": ROLLING_WINDOW,
        "drift_window_sec": DRIFT_WINDOW,
        "airborne_tof_cm": AIRBORNE_TOF_CM,
        "battery_percent_min": round(batt_threshold, 1) if batt_threshold else None,
        "battery_worst_rate_pct_per_min": round(worst, 2) if worst else None,
        # rounded exactly as the emitted rule rounds it, so collect_alerts.py
        # computes onset against the same number Prometheus evaluates
        "temph_max": float(f'{settled["temph"]:.0f}') if "temph" in settled else None,
        "temph_settle_tail_sec": SETTLE_TAIL_SEC,
        "temph_p1_not_used": g("temph", 0),  # recorded for the write-up, not a rule
        "templ_max": float(f'{settled["templ"]:.0f}') if "templ" in settled else None,
        "baro_drift_max": round(drift["baro"], 3) if "baro" in drift else None,
        "pitch_sd_max": round(var["pitch"], 2) if "pitch" in var else None,
        "roll_sd_max": round(var["roll"], 2) if "roll" in var else None,
        "depletion_rate_by_battery": {k: round(st.mean(v), 2)
                                      for k, v in sorted(per_battery.items())},
    }, indent=2) + "\n", encoding="utf-8")

    print(f"\nWrote {OUT_RULES.name} - review it, then copy over ras_alerts.rules.yml")
    print(f"Wrote {OUT_JSON.name} - read by collect_alerts.py to compute t_onset")


if __name__ == "__main__":
    main()
