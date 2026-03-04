import sys
import pandas as pd
import numpy as np
from scipy.stats import linregress
import yfinance as yf
from fetch_tickers import get_nasdaq_large_caps


def find_consolidation_breakout(df: pd.DataFrame,
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

    Args:
        df: DataFrame with 'Close' and 'Volume' columns, indexed by Date.
        min_decline_pct: Minimum percentage decline from peak to trough (0.30 = 30%).
        min_decline_days: Minimum trading days for the decline phase.
        max_consolidation_range: Maximum P90/P10 ratio during consolidation.
        max_consolidation_slope: Maximum normalized slope to ensure flatness.
        breakout_threshold: Multiplier above consolidation max to confirm breakout.
        volume_multiplier: Required volume ratio (5-day avg or single-day) vs base avg.
    """
    if len(df) < 200:
        return False

    prices = df['Close'].values
    volumes = df['Volume'].values

    # ─── Phase 1: Find the structural peak and subsequent decline ───
    # Instead of find_peaks (which picks arbitrary local peaks), find the
    # HIGHEST price point that precedes a significant decline (≥min_decline_pct).
    # This correctly identifies e.g. HOOD's $70 ATH, not a $13 minor bump.

    peak_idx = None
    trough_idx = None

    for candidate_peak in range(len(prices) - min_decline_days):
        # Look for the lowest price after this candidate peak
        future_prices = prices[candidate_peak + 1:]
        future_min_offset = np.argmin(future_prices)
        future_min_idx = candidate_peak + 1 + future_min_offset
        decline_pct = (prices[candidate_peak] - prices[future_min_idx]) / prices[candidate_peak]

        if decline_pct >= min_decline_pct:
            # Among all qualifying peaks, pick the one with the highest price
            if peak_idx is None or prices[candidate_peak] > prices[peak_idx]:
                peak_idx = candidate_peak
                trough_idx = future_min_idx

    if peak_idx is None or trough_idx is None:
        return False

    t1_decline_days = trough_idx - peak_idx
    if t1_decline_days < min_decline_days:
        return False

    decline_pct = (prices[peak_idx] - prices[trough_idx]) / prices[peak_idx]

    # ─── Phase 2: Analyze the consolidation base ───
    breakout_window = 30
    current_idx = len(prices) - 1
    consolidation_end_idx = current_idx - breakout_window

    if trough_idx >= consolidation_end_idx:
        return False

    t2_consolidation_days = consolidation_end_idx - trough_idx

    # Scale minimum base duration with decline severity:
    #   ≥50% decline → ≥200 days (~10 months)
    #   ≥30% decline → ≥120 days (~6 months)
    # Cap the 2× decline rule at 90 days so extreme crashes don't demand
    # impossibly long bases.
    if decline_pct >= 0.50:
        required_min_days = 200
    elif decline_pct >= 0.30:
        required_min_days = 120
    else:
        required_min_days = 60

    required_t2 = max(required_min_days, min(2 * t1_decline_days, 90))

    if t2_consolidation_days < required_t2:
        return False

    consolidation_data = prices[trough_idx:consolidation_end_idx]
    if len(consolidation_data) == 0:
        return False

    # Use P90/P10 to define the core consolidation band (ignores extreme wicks)
    consolidation_p90 = np.percentile(consolidation_data, 90)
    consolidation_p10 = np.percentile(consolidation_data, 10)
    consolidation_max = np.max(consolidation_data)

    # Dynamic range: tighter thresholds than before
    avg_price = np.mean(consolidation_data)
    dynamic_max_range = max_consolidation_range
    if avg_price < 20.0:
        dynamic_max_range = 1.80  # Tightened from 2.50 — was far too permissive
    elif avg_price < 50.0:
        dynamic_max_range = 1.50

    if consolidation_p90 > consolidation_p10 * dynamic_max_range:
        return False

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
        return False

    # ─── Phase 3: Detect the breakout ───
    recent_prices = prices[consolidation_end_idx:]

    # Require price to break above the ACTUAL consolidation maximum
    # (not just P90). This prevents false signals from moves within the base.
    if np.max(recent_prices) < (consolidation_max * breakout_threshold):
        return False

    # Multi-day volume confirmation:
    #   - 5-day average volume ≥ volume_multiplier × base average, OR
    #   - Any single day ≥ 2.0× base average (catches earnings-driven breakouts)
    avg_base_vol = np.mean(volumes[trough_idx:consolidation_end_idx])

    # Find the first day that breaks above consolidation max
    breakout_day_idx = None
    for i in range(len(recent_prices)):
        if recent_prices[i] > consolidation_max:
            breakout_day_idx = consolidation_end_idx + i
            break

    if breakout_day_idx is None:
        return False

    # Check 5-day average volume around the breakout
    vol_window_start = max(breakout_day_idx - 2, 0)
    vol_window_end = min(breakout_day_idx + 3, len(volumes))
    avg_breakout_vol_5d = np.mean(volumes[vol_window_start:vol_window_end])

    # Check if any single day in the breakout window has a big volume spike
    max_single_day_vol = np.max(volumes[consolidation_end_idx:])

    vol_pass = (avg_breakout_vol_5d >= avg_base_vol * volume_multiplier or
                max_single_day_vol >= avg_base_vol * 2.0)

    if not vol_pass:
        return False

    return True

def scan_stocks(tickers):
    matched = []
    print(f"Scanning {len(tickers)} tickers. This might take a moment...")
    for i, ticker in enumerate(tickers):
        try:
            ticker_obj = yf.Ticker(ticker)
            # Fetch 2 years of daily data
            df = ticker_obj.history(period="2y", interval="1d")
            
            if df.empty or len(df) < 252:
                continue
                
            if find_consolidation_breakout(df):
                print(f"[{i+1}/{len(tickers)}] \033[92mMatch found: {ticker}\033[0m")
                matched.append(ticker)
            else:
                sys.stdout.write(".")
                sys.stdout.flush()
                
        except Exception as e:
            print(f"\nError processing {ticker}: {e}")
            
    print("\nScan complete.")
    return matched

if __name__ == "__main__":
    print("Fetching NASDAQ >$10B companies...")
    nasdaq_large_caps = get_nasdaq_large_caps()
    
    # Filter out preferred shares (which often have low volume/weird data)
    target_tickers = [t for t in nasdaq_large_caps if len(t) <= 4 and '-' not in t]
    
    print(f"Starting Long Base Consolidation Breakout Scanner for {len(target_tickers)} stocks...")
    matches = scan_stocks(target_tickers)
    
    if matches:
        print("\n=== STOCKS MATCHING PATTERN ===")
        for m in matches:
            print(f"- {m}")
    else:
        print("\nNo stocks matched the pattern in this sample today.")
        print("Note: This is a rare technical setup, especially among large caps.")
