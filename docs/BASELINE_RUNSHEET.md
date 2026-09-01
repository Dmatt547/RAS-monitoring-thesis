# Phase 1 Baseline — Run Sheet

Five sessions: BASE-01 to BASE-05. One battery each. Indoors.

You do **not** need Prometheus running. The harness writes the CSV itself.

---

## 1. Install (once)

```
pip install djitellopy prometheus_client
```

---

## 2. Windows setup (once)

Device Manager → Network adapters → your Wi-Fi adapter → Properties →
Power Management → untick "Allow the computer to turn off this device".

Turn off "Connect automatically" on your home Wi-Fi. Otherwise Windows will
leave the Tello network mid-flight to get back to the internet.

---

## 3. Connect

1. Power on the Tello. LED blinks amber.
2. Join the `TELLO-XXXXXX` Wi-Fi. No password.
3. Check you're on it:

```
netsh wlan show interfaces
```

The SSID line must say TELLO-something.

---

## 4. Dry run (once, before any flying)

Drone stays on the desk. No motors.

```
python "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\flight_session.py" --dry --duration 60
```

Session ID: `DRY-01`

Then:

```
python "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\check_session.py" DRY-01
```

Ignore the duration FAIL — 60s is meant to be short. Check these two lines:

- `snr coverage` — should be 90%+
- `snr freshness` — max age under 15s

If SNR is blank, open `flight_session.py` and change `SNR_INTERVAL_SEC = 5.0`
to `10.0`, then rerun. Keep whatever value works for all five sessions.

---

## 5. Fly a session

Clear about 4m of space around the takeoff point.

```
python "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\flight_session.py"
```

It asks for: session ID, venue, indoor/outdoor, ambient temperature, battery ID,
cycle count, notes.

**It takes off 2 seconds after the last answer.** Area clear before you hit Enter.

Then leave it alone. It flies takeoff → hover → translate → rotate → hover on a
loop, lands itself at 8 minutes or 15% battery. Ctrl+C lands it early.

---

## 6. Check it, before the next flight

```
python "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\check_session.py"
```

Ends with **USABLE** or **RE-FLY THIS SESSION**. Re-fly now if it failed.

Let the drone cool down before the next session, or its temperature readings
start biased by the last flight.

Repeat steps 5 and 6 until you have BASE-01 through BASE-05.

---

## 7. Done

```
python "C:\Users\danie\OneDrive\Documents\UNI\YEAR 4\SIT723 - Research Techniques and Apps\Code\check_session.py" --all
```

Want 5/5 usable. Files are in `Code\sessions\` — three per session:

- `_telemetry.csv` — the 1 Hz log. **This is the data.**
- `_events.csv` — step and event markers
- `_metadata.csv` — venue, temp, battery

Commit them. They're your evidence.

---

## If something breaks

| Problem | Fix |
|---|---|
| `Did not receive a state packet` | Not on the Tello Wi-Fi, or `ras_exporter_live.py` is still running. Only one program can hold the drone. |
| Connection drops mid-flight | Windows switched networks. Redo step 2. |
| Takeoff refused | Battery under 25%. Swap it. |
| Sample gaps in the check | Wi-Fi power saving. Redo step 2. |
| SNR blank | Raise `SNR_INTERVAL_SEC`. If still blank, report SNR as unavailable — that's a finding, not a failure. |
| Drone hits something | 80cm translation too big for the room. Reduce it in `_cycle()` — same value for all five sessions. |

---

## Later, not now

Prometheus is for Phase 2, where you need alert firing timestamps to measure
detection latency. For Phase 1 you only need the CSVs.

Before Phase 2: derive the thresholds from the pooled baseline data and replace
the placeholders in `ras_alerts.rules.yml`, including the assumed 60 °C.
