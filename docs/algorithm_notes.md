---
description: Design decisions, lessons learned, and reference data for the long base breakout detection algorithm
---

# Algorithm Design Notes

## Key Design Decision: Why Not `find_peaks`?

The original algorithm used `scipy.signal.find_peaks()` to detect peaks and troughs. This failed for HOOD because:
- `find_peaks` with `distance=20, prominence=5` found 4 peaks, and the code took the **last** one ($13.12 in Jul 2023)
- The **real** structural peak was $70.39 in Aug 2021 — the start of a 90% crash
- The current approach iterates over all price points and finds the **highest** one with a ≥30% subsequent decline

## Key Design Decision: Base Duration Scaling

A fixed 60-day minimum base was too short. Analysis of HOOD showed:
- **62-day base** → false breakout (Sep 2022, price fell back to $9)
- **99-day base** → false breakout (Nov 2022, price fell back to $8)
- **417-day base** → real breakout (Feb 2024, price continued to $40+)

The current scaling:
| Decline Severity | Min Base Duration |
|-----------------|-------------------|
| ≥50% | 200 trading days (~10 months) |
| ≥30% | 120 trading days (~6 months) |
| <30% | 60 trading days (~3 months) |

## Key Design Decision: Multi-Day Volume

Single-day volume checks are unreliable because:
- The breakout might start on a moderate-volume day and then see sustained high volume
- For HOOD, the breakout day (2024-02-14) had 7.53× average volume (earnings), but looking at just the last bar of the data window might show 1.1× 

Current approach: **5-day average ≥1.3× OR any single day ≥2.0×**

## Reference: HOOD Breakout Anatomy

```
Peak:    2021-08-04  $70.39  (IPO spike)
Trough:  2022-06-16  $6.89   (−90.2%, 219 days)
Base:    2022-06 to 2024-02  (417 days, $7–$13 range)
  - P10: $8.42, P90: $11.72, Max: $13.26
  - Ratio (P90/P10): 1.39
  - Normalized slope: 0.000370 (very flat)
  - 10 local highs tested resistance at ~$11–$13
Breakout: 2024-02-14  $13.38 (Q4 2023 earnings catalyst)
  - 5-day avg volume: 3.84× base average
  - Peak single-day volume: 7.53× base average
  - Continued to $40+ in following months
```

## Consolidation Range Thresholds

| Avg Price | Max P90/P10 Ratio | Max Normalized Slope |
|-----------|-------------------|---------------------|
| <$20 | 1.80 | 0.015 |
| $20–$50 | 1.50 | 0.0075 |
| >$50 | 1.50 | 0.0015 |

## False Positive Cases to Watch

- **VNOM-type**: Steady uptrend misidentified as consolidation → caught by slope check
- **Short base after big crash**: Price pops above range after only 60–90 days → caught by duration scaling
- **Within-range moves**: Price exceeds P90 but not the actual max → caught by structural resistance check
