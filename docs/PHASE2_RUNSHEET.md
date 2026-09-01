# Phase 2 — Fault Injection Run Sheet

Nine runs: three fault classes, three repetitions each.

Same rules as Phase 1: indoors, lights on, full battery each run, drone cooled
to ambient before each — **except thermal runs, which need the opposite.**

Prometheus must be running for every Phase 2 run. The alert log is the data.

---

## Where this sits in the experiment

The whole thesis is one experimental design run as two studies against one
artefact. Study 2 is split into three phases.

| | Study / Phase | What it does | Answers | Status |
|---|---|---|---|---|
| **Study 1** | Dataset replay | Replays pre-labelled telemetry through the pipeline. Health state comes from the dataset label, so only the pipeline is under test. | RQ1.1, RQ1.2 | Complete (T1) |
| **Study 2 — Phase 1** | Baseline | 5 normal flights on the physical Tello. Establishes what normal looks like for every metric. Thresholds are derived from this. | RQ2.1 | Complete |
| **Study 2 — Phase 2** | Fault injection | 9 runs, 3 fault classes x 3 repetitions, plus held-out normal flights. Tests whether the rules detect faults with no labels. | RQ2.2, RQ2.3 | This document |
| **Study 2 — Phase 3** | Evaluation | Confusion matrix, detection latency, false positive rate, metric coverage, computed from the archived logs. | RQ2.2, RQ2.3 | After Phase 2 |

The order is not incidental. Study 1 removes the pipeline as a possible source
of error, so any detection failure in Study 2 belongs to the thresholds and
alerting rules rather than to ingestion, storage or query. Phase 1 must precede
Phase 2 for the same reason: a threshold cannot be tested before it has been
derived, and it cannot be derived from the data it will later be judged against.

---

## The nine runs, plus the held-out normal flights

Fly them in this order. The FP flights come first because they establish the
false positive rate on an aircraft in known-good condition, before any fault run
has warmed or discharged it.

| # | Session ID | Mode | Battery | Condition before flight | Fault induced | Rule under test | Expected outcome |
|---|---|---|---|---|---|---|---|
| — | `FP-01` | baseline | B1, full | Cooled to ambient | None | All five | No alert |
| — | `FP-02` | baseline | B2, full | Cooled to ambient | None | All five | No alert |
| — | `FP-03` | baseline | B1, full | Cooled to ambient | None | All five | No alert |
| 1 | `FAULT-BAT-01` | battery | B1, full | Cooled to ambient | Flight continues to the aircraft's low-battery failsafe | `DroneLowBattery` | Fires at 31%, with lead time before the failsafe |
| 2 | `FAULT-BAT-02` | battery | B2, full | Cooled to ambient | As above | `DroneLowBattery` | As above, on the faster-depleting cell |
| 3 | `FAULT-BAT-03` | battery | B1, full | Cooled to ambient | As above | `DroneLowBattery` | As above |
| 4 | `FAULT-LINK-01` | link | B2, full | Cooled to ambient | Operator walks away, then occludes line of sight | `DronePollFailure`, SNR | Poll failure fires; SNR may not move |
| 5 | `FAULT-LINK-02` | link | B1, full | Cooled to ambient | As above, greater separation | `DronePollFailure`, SNR | As above |
| 6 | `FAULT-LINK-03` | link | B2, full | Cooled to ambient | As above | `DronePollFailure`, SNR | As above |
| 7 | `FAULT-THERM-01` | thermal | B1, part-discharged | **Warm.** Within 10 min of a previous flight | Continuous 100 cm/s manoeuvring, no hover rest | `DroneTemperatureOutOfRange`, `DroneUnstableAttitude` | Temperature above 63 C; attitude dispersion above baseline |
| 8 | `FAULT-THERM-02` | thermal | B2, part-discharged | **Warm.** Straight after run 7 | As above | As above | As above |
| 9 | `FAULT-THERM-03` | thermal | B1, part-discharged | **Warm.** Straight after run 8 | As above | As above | As above |

Note the deliberate inversion in the last three rows. Every other run in this
thesis requires a cooled aircraft; the thermal runs require a warm one, because
baseline measurement showed that flight cools the airframe rather than heating
it. Cooling the aircraft before a thermal run would prevent the fault condition
from occurring at all.

Batteries are alternated so that neither cell is confounded with a single fault
class. B1 and B2 deplete at measurably different rates (7.25 against
10.50 %/min), so both must appear in the depletion runs.

Each run classifies into one of three outcomes: **true positive** (the rule
matching the induced fault fired), **false negative** (no rule fired), or
**misclassification** (a rule fired, but for the wrong fault class). Those nine
outcomes make the confusion matrix.

---

## Before you start

Start Prometheus and leave it running all session:

```powershell
cd "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\prometheus"
& "C:\Users\danie\Downloads\prometheus-3.11.3.windows-amd64\prometheus-3.11.3.windows-amd64\prometheus.exe" --config.file=prometheus.yml
```

Check http://localhost:9090/alerts shows all five rules.

---

## First: the false positive test

Before any faults, fly **2 or 3 normal sessions** with Prometheus running.
Cooled drone, full battery, lights on.

```
python flight_session.py
```

Session IDs `FP-01`, `FP-02`, `FP-03`.

Nothing should fire. Anything that does is your false positive rate. Note the
alert name, the time it fired and how long it stayed active.

These are held out from threshold derivation, which is what makes the figure
meaningful — see edit 8 in `Thesis/METHODOLOGY_EDITS.md`.

---

## Fault 1: Battery depletion — 3 runs

```
python flight_session.py --mode battery
```

IDs: `FAULT-BAT-01`, `-02`, `-03`.

The harness will **not** land the drone. It flies until the Tello's own
low-battery failsafe lands it — that failsafe is the thing being measured. The
run ends with a `failsafe_engaged` event, which is the expected outcome, not an
error.

What you are measuring: did `DroneLowBattery` fire at 31%, and how much lead
time did that give before the failsafe engaged?

Full battery each run. Alternate B1 and B2 — they deplete at different rates
(7.25 vs 10.50 %/min) and both should be represented.

---

## Fault 2: Link degradation — 3 runs

```
python flight_session.py --mode link
```

IDs: `FAULT-LINK-01`, `-02`, `-03`.

The drone hovers in place for up to 10 minutes. **You** create the fault by
walking away with the laptop, then putting a wall between you and it.

**Press ENTER the moment you start walking.** That writes `t_induce` to the
events log. Only you know when you started, so nothing else can record it.

Keep the drone in sight the whole time. If the link drops entirely the drone
will land itself, which is a valid outcome — that is what `DronePollFailure`
exists to catch.

What you are measuring: did SNR fall at all, and did `DronePollFailure` fire?

> Note: SNR read a flat 90 in all five baseline sessions. If it stays at 90 as
> you walk away, that is a finding — report SNR as unusable on this platform and
> rely on liveness. Do not treat it as a failed run.

---

## Fault 3: Thermal and load stress — 3 runs

```
python flight_session.py --mode thermal
```

IDs: `FAULT-THERM-01`, `-02`, `-03`.

**Do not cool the drone between these.** That is the opposite of the Phase 1
rule and it is deliberate: baseline data showed flying *cools* the aircraft, so
aggressive manoeuvring alone will not produce a thermal fault. Consecutive
sorties will.

Protocol per run:

1. Fly a normal baseline flight first, or reuse the drone straight from the
   previous thermal run
2. Wait no more than 10 minutes
3. Fly the thermal run on a **part-discharged** battery (around 50-60%)
4. Repeat

The mode flies continuously at 100 cm/s with no hover rest — forward/back,
left/right, full rotations both ways, up/down.

What you are measuring: did `DroneTemperatureOutOfRange` and
`DroneUnstableAttitude` fire?

Reference: an accidental run of exactly this on 30 August started at 86 °C and
held 64-82 °C in flight, against a 56-65 °C baseline. The alert fired correctly.

---

## After every run

Two commands. Nothing is recorded by hand.

```
python check_session.py
python collect_alerts.py
```

`collect_alerts.py` does the whole measurement:

- **t_onset** from the telemetry CSV, using the values in
  `prometheus/thresholds.json`, so the onset calculation and the alerting rules
  cannot drift apart. Both come from the same derivation run.
- **t_alert** queried back out of Prometheus. Prometheus records its own alert
  state as a series called `ALERTS`, so the firing times are retrieved rather
  than watched for. Prometheus must be running.
- **detection latency** = `t_alert - t_onset`
- **t_induce** from the `operator_marker` event you wrote by pressing ENTER

It writes `<session>_alerts.csv` beside the other session files, and prints:

```
alert                     t_onset  t_alert  latency transient  outcome
DroneLowBattery               95s     101s       6s         0  fired
DroneOverTemperature            -        -        -         0  -
```

Read the outcome column against the confusion matrix:

| Outcome shown | Classification |
|---|---|
| `fired` on the rule under test | True positive |
| `MISSED - threshold crossed, no alert` | False negative |
| `fired` on a rule that is not the one under test | Misclassification |
| `fired, no onset in telemetry` | Investigate — the alert has no basis in the raw log |

### Two things the tool does that matter

**Onset means a sustained crossing**, not any crossing. A one-sample excursion
cannot fire an alert, so anchoring latency to it would measure the gap between
two unrelated events. Every rule holds for 5 s, so onset is the first crossing
that lasts at least that long. Brief crossings are counted in the `transient`
column instead of being discarded, because how often the hold duration saves you
is worth reporting: the clean baselines show 2 to 3 transient attitude crossings
each and no alerts.

**Prometheus must be running during the flight**, not just afterwards. It can
only report alerts it evaluated at the time. If you forget, the telemetry CSV
still gives you t_onset — run `collect_alerts.py --offline` — but that run
cannot contribute to detection rate or latency, only to the threshold analysis.

---

## What the nine runs produce

- **Confusion matrix** → detection rate, target ≥8 of 9
- **Latency distribution** → median ≤5 s, max ≤10 s
- **False positive rate** → from the FP flights, target ≤1 per 10 min

That is M5 and M6 done, and RQ2.2 and RQ2.3 answered.
