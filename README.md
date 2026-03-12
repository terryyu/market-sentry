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

## Algorithms

### 1. Long Base Consolidation Breakout
The stock crashes, builds a long base, and breaks out.

```
     Peak ($70)
      /\
     /  \
    /    \  ← Phase 1: Significant decline (≥30%)
   /      \
  /        \_______/\___/\___/\____  ← Phase 2: Long flat consolidation (≥60-200 days)
                                    \
                                     ↗ ← Phase 3: Breakout with volume
```
**Key Rules:**
- Base duration scales with decline: ≥50% drop needs 200 days, ≥30% needs 120 days.
- Max range ratio (P90/P10) is 1.50 (1.80 for cheap stocks).

### 2. Flat Base Breakout
The stock establishes a prior uptrend, consolidates tightly for a shorter period, and breaks out.

```
                                     ↗ ← Phase 3: Breakout with volume
                                    /
            _______/\___/\___/\____/ ← Phase 2: Tight flat consolidation (≥30 days)
           /
          / ← Phase 1: Prior Uptrend
         /
```
**Key Rules:**
- Prior uptrend: Price 60 days before the base must be ≥15% lower than the base average.
- Very tight range: Max range ratio (P90/P10) is strictly **1.25**.

### Shared Breakout Logic
- Price must exceed the **actual consolidation maximum** (structural resistance).
- Volume confirmed via: 5-day avg ≥1.3× base avg **OR** any single day ≥2.0× base avg.

## Testing Against Known Patterns

Edit the `__main__` block in `debug_scanner.py` to test specific tickers:

```python
# Test with custom date range
debug_long_base_pattern("HOOD", start_date="2021-08-01", end_date="2024-03-31")
debug_flat_base_pattern("NVDA", start_date="2023-08-01", end_date="2024-02-28")
```

### Validated Cases

| Ticker | Pattern | Date Range | Result | Reason |
|--------|---------|------------|--------|--------|
| HOOD | Long Base | 2021-08 → 2024-03 | ✅ Match | Textbook long base breakout on 2024-02-14 |
| NVDA | Flat Base | 2023-08 → 2024-02 | ✅ Match | Found the $40-$50 tight base and Jan 2024 breakout |
| AAPL | n/a | 2y | ❌ Reject | Trending up, neither base pattern fits |

## Development

```bash
# Python version
python 3.12+

# Package manager
uv

# All commands should use `uv run` prefix
uv run python <script.py>
```
