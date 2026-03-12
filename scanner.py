import sys
import pandas as pd
import numpy as np
from scipy.stats import linregress
import yfinance as yf
from fetch_tickers import get_nasdaq_large_caps


def check_consolidation_and_breakout(prices: np.ndarray, volumes: np.ndarray, 
                                     start_idx: int, end_idx: int,
                                     max_consolidation_range: float, 
                                     max_consolidation_slope: float,
                                     breakout_threshold: float, 
                                     volume_multiplier: float) -> tuple[bool, int | None]:
    """
    Shared helper to analyze the consolidation base and confirm the breakout.
    Returns (True, breakout_day_idx) if valid, else (False, None).
    """
    consolidation_data = prices[start_idx:end_idx]
    if len(consolidation_data) == 0:
        return False, None

    # Use P90/P10 to define the core consolidation band (ignores extreme wicks)
    consolidation_p90 = np.percentile(consolidation_data, 90)
    consolidation_p10 = np.percentile(consolidation_data, 10)
    consolidation_max = np.max(consolidation_data)

    # Dynamic range: slightly looser thresholds for cheaper stocks
    avg_price = np.mean(consolidation_data)
    dynamic_max_range = max_consolidation_range
    if avg_price < 20.0:
        dynamic_max_range = max_consolidation_range * 1.2
    elif avg_price < 50.0:
        dynamic_max_range = max_consolidation_range * 1.0

    if consolidation_p90 > consolidation_p10 * dynamic_max_range:
        return False, None

    # Flatness check via linear regression
    x = np.arange(len(consolidation_data))
    slope, _, _, _, _ = linregress(x, consolidation_data)
    normalized_slope = abs(slope) / avg_price

    dynamic_max_slope = max_consolidation_slope
    if avg_price < 20.0:
        dynamic_max_slope = max_consolidation_slope * 10
    elif avg_price < 50.0:
        dynamic_max_slope = max_consolidation_slope * 5

    if normalized_slope > dynamic_max_slope:
        return False, None

    # ─── Detect the breakout ───
    recent_prices = prices[end_idx:]

    # Require price to break above the ACTUAL consolidation maximum
    # (not just P90). This prevents false signals from moves within the base.
    if np.max(recent_prices) < (consolidation_max * breakout_threshold):
        return False, None

    # Find the first day that breaks above consolidation max
    breakout_day_idx = None
    for i in range(len(recent_prices)):
        if recent_prices[i] > consolidation_max:
            breakout_day_idx = end_idx + i
            break

    if breakout_day_idx is None:
        return False, None

    # Multi-day volume confirmation:
    #   - 5-day average volume ≥ volume_multiplier × base average, OR
    #   - Any single day ≥ 2.0× base average (catches earnings-driven breakouts)
    avg_base_vol = np.mean(volumes[start_idx:end_idx])

    # Check 5-day average volume around the breakout
    vol_window_start = max(breakout_day_idx - 2, 0)
    vol_window_end = min(breakout_day_idx + 3, len(volumes))
    avg_breakout_vol_5d = np.mean(volumes[vol_window_start:vol_window_end])

    # Check if any single day in the breakout window has a big volume spike
    max_single_day_vol = np.max(volumes[end_idx:])

    vol_pass = (avg_breakout_vol_5d >= avg_base_vol * volume_multiplier or
                max_single_day_vol >= avg_base_vol * 2.0)

    if not vol_pass:
        return False, None

    return True, breakout_day_idx


def find_long_base_breakout(df: pd.DataFrame,
                            min_decline_pct: float = 0.30,
                            min_decline_days: int = 20,
                            max_consolidation_range: float = 1.50,
                            max_consolidation_slope: float = 0.0015,
                            breakout_threshold: float = 1.02,
                            volume_multiplier: float = 1.3) -> bool:
    """
    Detects a 'Long Base Consolidation Breakout' pattern.

    The pattern consists of three phases:
      1. A significant decline from a structural peak (≥30% drop).
      2. A long, flat consolidation base (duration scaled to decline severity).
      3. A breakout above the consolidation high, confirmed by sustained volume.
    """
    if len(df) < 200:
        return False

    prices = df['Close'].values
    volumes = df['Volume'].values

    # Phase 1: Find highest price that precedes a significant decline
    peak_idx = None
    trough_idx = None

    for candidate_peak in range(len(prices) - min_decline_days):
        future_prices = prices[candidate_peak + 1:]
        future_min_offset = np.argmin(future_prices)
        future_min_idx = candidate_peak + 1 + future_min_offset
        decline_pct = (prices[candidate_peak] - prices[future_min_idx]) / prices[candidate_peak]

        if decline_pct >= min_decline_pct:
            if peak_idx is None or prices[candidate_peak] > prices[peak_idx]:
                peak_idx = candidate_peak
                trough_idx = future_min_idx

    if peak_idx is None or trough_idx is None:
        return False

    t1_decline_days = trough_idx - peak_idx
    if t1_decline_days < min_decline_days:
        return False

    decline_pct = (prices[peak_idx] - prices[trough_idx]) / prices[peak_idx]

    # Phase 2: Base duration requirements
    breakout_window = 30
    current_idx = len(prices) - 1
    consolidation_end_idx = current_idx - breakout_window

    if trough_idx >= consolidation_end_idx:
        return False

    t2_consolidation_days = consolidation_end_idx - trough_idx

    if decline_pct >= 0.50:
        required_min_days = 200
    elif decline_pct >= 0.30:
        required_min_days = 120
    else:
        required_min_days = 60

    required_t2 = max(required_min_days, min(2 * t1_decline_days, 90))

    if t2_consolidation_days < required_t2:
        return False

    passed, _ = check_consolidation_and_breakout(
        prices, volumes, trough_idx, consolidation_end_idx,
        max_consolidation_range, max_consolidation_slope,
        breakout_threshold, volume_multiplier
    )
    return passed


def find_flat_base_breakout(df: pd.DataFrame,
                            min_base_days: int = 30,
                            max_consolidation_range: float = 1.25,
                            max_consolidation_slope: float = 0.0050,
                            breakout_threshold: float = 1.02,
                            volume_multiplier: float = 1.3) -> bool:
    """
    Detects a 'Flat Base' (or Rectangle) breakout pattern.
    
    The pattern consists of:
      1. A prior uptrend (price before the base is significantly lower).
      2. A tight, flat consolidation base (e.g., max P90/P10 ratio of 1.25) lasting ≥30 days.
      3. A breakout above the consolidation high, confirmed by sustained volume.
    """
    if len(df) < 100:
        return False

    prices = df['Close'].values
    volumes = df['Volume'].values

    breakout_window = 30
    current_idx = len(prices) - 1
    
    # We look for a breakout in the recent window. To do so, we iterate 
    # over recent days to find a day that breaks above a viable tight base.
    for b_idx in range(current_idx - breakout_window + 1, current_idx + 1):
        cand_end_idx = b_idx - 1
        
        # Backwards search for the longest base that meets tightness criteria
        max_lookback = 120 # maximum typical base length for flat base (~6 months)
        start_search = max(0, cand_end_idx - max_lookback)
        
        cand_start_idx = None
        for candidate_start in range(start_search, cand_end_idx - min_base_days):
            window = prices[candidate_start:cand_end_idx]
            p90 = np.percentile(window, 90)
            p10 = np.percentile(window, 10)
            if p90 <= p10 * max_consolidation_range:
                cand_start_idx = candidate_start
                break # Iterating from oldest to newest finds the longest valid base
                
        if cand_start_idx is not None:
            # Check for Prior Uptrend: The lowest price in the 60 days before the base
            # should be at least 15% lower than the base average.
            pre_base_start = max(0, cand_start_idx - 60)
            pre_base_prices = prices[pre_base_start:cand_start_idx]
            
            if len(pre_base_prices) > 0:
                base_avg = np.mean(prices[cand_start_idx:cand_end_idx])
                pre_base_min = np.min(pre_base_prices)
                
                if pre_base_min <= base_avg * 0.85:
                    passed, _ = check_consolidation_and_breakout(
                        prices, volumes, cand_start_idx, cand_end_idx,
                        max_consolidation_range, max_consolidation_slope,
                        breakout_threshold, volume_multiplier
                    )
                    if passed:
                        return True

    return False


def scan_stocks(tickers):
    matched_long_base = []
    matched_flat_base = []
    
    print(f"Scanning {len(tickers)} tickers. This might take a moment...")
    for i, ticker in enumerate(tickers):
        try:
            ticker_obj = yf.Ticker(ticker)
            # Fetch 2 years of daily data
            df = ticker_obj.history(period="2y", interval="1d")
            
            if df.empty or len(df) < 200:
                continue
                
            match_found = False
            
            if find_long_base_breakout(df):
                print(f"\n[{i+1}/{len(tickers)}] \033[92m[LONG BASE] Match found: {ticker}\033[0m")
                matched_long_base.append(ticker)
                match_found = True
                
            if find_flat_base_breakout(df):
                print(f"\n[{i+1}/{len(tickers)}] \033[94m[FLAT BASE] Match found: {ticker}\033[0m")
                matched_flat_base.append(ticker)
                match_found = True
                
            if not match_found:
                sys.stdout.write(".")
                sys.stdout.flush()
                
        except Exception as e:
            print(f"\nError processing {ticker}: {e}")
            
    print("\nScan complete.")
    return matched_long_base, matched_flat_base


if __name__ == "__main__":
    print("Fetching NASDAQ >$10B companies...")
    nasdaq_large_caps = get_nasdaq_large_caps()
    
    # Filter out preferred shares (which often have low volume/weird data)
    target_tickers = [t for t in nasdaq_large_caps if len(t) <= 4 and '-' not in t]
    
    print(f"Starting Breakout Scanner for {len(target_tickers)} stocks...")
    matches_long, matches_flat = scan_stocks(target_tickers)
    
    if matches_long:
        print("\n=== STOCKS MATCHING LONG BASE ===")
        for m in matches_long:
            print(f"- {m}")
    else:
        print("\nNo stocks matched the Long Base pattern today.")
        
    if matches_flat:
        print("\n=== STOCKS MATCHING FLAT BASE ===")
        for m in matches_flat:
            print(f"- {m}")
    else:
        print("\nNo stocks matched the Flat Base pattern today.")
