# Market Sentry

A stock scanner that detects **Long Base Consolidation Breakout** patterns — stocks that have experienced a significant decline, consolidated in a tight range for an extended period, then broken out with volume confirmation.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the full scanner (scans all NASDAQ >$10B market cap)
uv run python scanner.py

# Debug a specific ticker with verbose output
uv run python debug_scanner.py
```

## Project Structure

| File | Purpose |
|------|---------|
| `scanner.py` | Core detection algorithm (`find_consolidation_breakout`) + batch scanner |
| `debug_scanner.py` | Same algorithm with step-by-step diagnostic output for tuning/debugging |
| `fetch_tickers.py` | Fetches NASDAQ large/mega cap tickers from Nasdaq API |
| `main.py` | Entry point |

## Algorithm: Long Base Consolidation Breakout

The pattern has three phases:

```
     Peak ($70)
      /\
     /  \
    /    \  ← Phase 1: Significant decline (≥30%)
   /      \
  /        \_______/\___/\___/\____  ← Phase 2: Long flat consolidation
                                    \
                                     ↗ ← Phase 3: Breakout with volume
```

### Detection Logic

**Phase 1 — Find Structural Peak & Decline:**
- Finds the highest price point that precedes a ≥30% decline
- Uses the actual highest price (not `find_peaks` last peak) to avoid picking minor bumps within the base

**Phase 2 — Consolidation Base:**
- Base duration scales with decline severity:
  - ≥50% decline → ≥200 trading days (~10 months)
  - ≥30% decline → ≥120 trading days (~6 months)
- P90/P10 range ratio must be ≤1.80 (cheap stocks) or ≤1.50 (others)
- Linear regression slope must be near-zero (flat, not trending)

**Phase 3 — Breakout Confirmation:**
- Price must exceed the **actual consolidation maximum** (structural resistance)
- Volume confirmed via: 5-day avg ≥1.3× base avg **OR** any single day ≥2.0× base avg

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_decline_pct` | 0.30 | Minimum decline from peak to trough (30%) |
| `min_decline_days` | 20 | Minimum trading days for the decline |
| `max_consolidation_range` | 1.50 | Max P90/P10 ratio (dynamically adjusted for price) |
| `max_consolidation_slope` | 0.0015 | Max normalized slope (dynamically adjusted) |
| `breakout_threshold` | 1.02 | Price must be ≥102% of consolidation max |
| `volume_multiplier` | 1.3 | 5-day avg volume must be ≥1.3× base avg |

## Testing Against Known Patterns

Edit the `__main__` block in `debug_scanner.py` to test specific tickers:

```python
# Test with custom date range
debug_pattern("HOOD", start_date="2021-08-01", end_date="2024-03-31")

# Test with default 2-year lookback
debug_pattern("AAPL")
```

### Validated Cases

| Ticker | Date Range | Result | Reason |
|--------|-----------|--------|--------|
| HOOD | 2021-08 → 2024-03 | ✅ Match | Textbook long base breakout on 2024-02-14 |
| AAPL | 2y | ❌ Reject | Trending up, not flat consolidation |
| TSLA | 2y | ❌ Reject | Base too short for decline severity |

## Development

```bash
# Python version
python 3.12+

# Package manager
uv

# All commands should use `uv run` prefix
uv run python <script.py>
```
