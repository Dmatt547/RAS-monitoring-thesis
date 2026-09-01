# Rejected baseline sessions

Not deleted — kept as a record of what was collected and why it was set aside.

| Session | Date | Environment | Why rejected |
|---|---|---|---|
| BASE-01 | 28 Aug | outdoor | Started on a 74% battery; blank metadata |
| BASE-02 | 28 Aug | outdoor | Environment differs from the Phase 1 set |
| BASE-03 | 29 Aug | indoor | Flown 8 min after the previous session, no cool-down |
| FP-01 (17:41) | 30 Aug | indoor | Flown against a superseded rule set; Prometheus had not been restarted after the temperature and barometer rules were corrected |
| FP-01 (20:00) | 30 Aug | indoor | Started on a 73% battery, below the 80% comparability minimum |

The BASE-01 flown on 29 August was reinstated: it was the first flight of
that day (drone at ambient), 100% battery, flown indoors in the room used for
the rest of the Phase 1 set, and it passed every check. It is BASE-01 of the
final baseline set.

The rejected sessions were logged as `indoor` in metadata because the environment prompt
defaulted to "indoor" when skipped. The prompt now requires an explicit answer.

These sessions still produced two findings that hold regardless of environment:

1. The Tello is hottest at power-on and cools in flight, so a `temph > 60`
   overheat rule fires during healthy flight. This is the origin of the Week 2
   false positive.
2. Barometer readings shifted ~20 cm between 28 and 29 August with atmospheric
   pressure. An absolute baro band cannot be derived across days; it has to be a
   within-session drift metric.
