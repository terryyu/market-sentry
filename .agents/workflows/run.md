---
description: How to run the market-sentry stock scanner and debug tools
---

# Running Market Sentry

This project uses **uv** as the package manager. All Python commands must be prefixed with `uv run`.

## Setup

// turbo
1. Install dependencies:
```bash
cd /Users/yaodongyu/develop/market-sentry && uv sync
```

## Common Commands

// turbo-all

### Run the full scanner (NASDAQ >$10B market cap)
```bash
cd /Users/yaodongyu/develop/market-sentry && uv run python scanner.py
```

### Debug a specific ticker with verbose output
```bash
cd /Users/yaodongyu/develop/market-sentry && uv run python debug_scanner.py
```

### Run a quick inline test on a single ticker
```bash
cd /Users/yaodongyu/develop/market-sentry && uv run python -c "
from debug_scanner import debug_pattern
debug_pattern('HOOD', start_date='2021-08-01', end_date='2024-03-31')
"
```

### Fetch the NASDAQ ticker list
```bash
cd /Users/yaodongyu/develop/market-sentry && uv run python fetch_tickers.py
```

## Important Notes

- **Always use `uv run`** — do NOT use bare `python` as dependencies are managed by uv
- **Python version**: 3.12+ (see `.python-version`)
- **Data source**: yfinance (Yahoo Finance API) — may be rate-limited with large scans
- **The scanner fetches live data** — results change daily
- **For historical testing**, use `debug_pattern()` with `start_date` and `end_date` params
