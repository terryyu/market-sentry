import pandas as pd
import numpy as np
from scipy.stats import linregress
import yfinance as yf


def debug_long_base_pattern(ticker, start_date=None, end_date=None, period="2y"):
    print(f"\n=======================================================")
    print(f"--- Debugging Long Base: {ticker} ---")
    ticker_obj = yf.Ticker(ticker)

    if start_date and end_date:
        df = ticker_obj.history(start=start_date, end=end_date, interval="1d")
        print(f"Using date range: {start_date} to {end_date} (Found {len(df)} days)")
    else:
        df = ticker_obj.history(period=period, interval="1d")
        print(f"Using period: {period} (Found {len(df)} days)")

    if len(df) < 150:
        print(f"Fail: Not enough data (<150 days)")
        return

    prices = df['Close'].values
    volumes = df['Volume'].values

    # ─── Phase 1: Find the structural peak and subsequent decline ───
    min_decline_pct = 0.30
    min_decline_days = 20

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
        print("Fail: No significant peak-to-trough decline (≥30%) found")
        return

    decline_pct = (prices[peak_idx] - prices[trough_idx]) / prices[peak_idx]
    t1_decline_days = trough_idx - peak_idx

    print(f"Structural Peak: day {peak_idx} ({df.index[peak_idx].strftime('%Y-%m-%d')}) = ${prices[peak_idx]:.2f}")
    print(f"Trough: day {trough_idx} ({df.index[trough_idx].strftime('%Y-%m-%d')}) = ${prices[trough_idx]:.2f}")
    print(f"Decline: {decline_pct*100:.1f}% over {t1_decline_days} days")

    if t1_decline_days < min_decline_days:
        print(f"Fail: Decline period too short (T1 = {t1_decline_days} days < {min_decline_days})")
        return
    else:
        print(f"Pass: Decline period T1 = {t1_decline_days} days")

    # ─── Phase 2: Analyze the consolidation base ───
    breakout_window = 30
    current_idx = len(prices) - 1
    consolidation_end_idx = current_idx - breakout_window

    if trough_idx >= consolidation_end_idx:
        print("Fail: Trough is too recent, no consolidation period")
        return

    t2_consolidation_days = consolidation_end_idx - trough_idx

    if decline_pct >= 0.50:
        required_min_days = 200
    elif decline_pct >= 0.30:
        required_min_days = 120
    else:
        required_min_days = 60

    required_t2 = max(required_min_days, min(2 * t1_decline_days, 90))

    if t2_consolidation_days < required_t2:
        print(f"Fail: Consolidation too short (T2 = {t2_consolidation_days} days < required {required_t2} days)")
        print(f"  (Decline was {decline_pct*100:.0f}%, requiring min {required_min_days} days)")
        return
    else:
        print(f"Pass: Consolidation T2 = {t2_consolidation_days} days (>= {required_t2})")

    _debug_consolidation_and_breakout(df, prices, volumes, trough_idx, consolidation_end_idx, 1.50, 0.0015, 1.02, 1.3)


def debug_flat_base_pattern(ticker, start_date=None, end_date=None, period="1y"):
    print(f"\n=======================================================")
    print(f"--- Debugging Flat Base: {ticker} ---")
    ticker_obj = yf.Ticker(ticker)

    if start_date and end_date:
        df = ticker_obj.history(start=start_date, end=end_date, interval="1d")
        print(f"Using date range: {start_date} to {end_date} (Found {len(df)} days)")
    else:
        df = ticker_obj.history(period=period, interval="1d")
        print(f"Using period: {period} (Found {len(df)} days)")

    if len(df) < 100:
        print(f"Fail: Not enough data (<100 days)")
        return

    prices = df['Close'].values
    volumes = df['Volume'].values
    
    breakout_window = 30
    current_idx = len(prices) - 1
    
    # We check if there is a breakout recently
    match_found = False
    
    for b_idx in range(current_idx - breakout_window + 1, current_idx + 1):
        cand_end_idx = b_idx - 1
        max_lookback = 120
        start_search = max(0, cand_end_idx - max_lookback)
        min_base_days = 30
        max_consolidation_range = 1.25
        
        cand_start_idx = None
        for candidate_start in range(start_search, cand_end_idx - min_base_days):
            window = prices[candidate_start:cand_end_idx]
            p90 = np.percentile(window, 90)
            p10 = np.percentile(window, 10)
            if p90 <= p10 * max_consolidation_range:
                cand_start_idx = candidate_start
                break
                
        if cand_start_idx is not None:
            pre_base_start = max(0, cand_start_idx - 60)
            pre_base_prices = prices[pre_base_start:cand_start_idx]
            
            if len(pre_base_prices) > 0:
                base_avg = np.mean(prices[cand_start_idx:cand_end_idx])
                pre_base_min = np.min(pre_base_prices)
                
                print(f"Evaluating candidate base: {df.index[cand_start_idx].strftime('%Y-%m-%d')} to {df.index[cand_end_idx].strftime('%Y-%m-%d')}")
                print(f"  Pre-base low (60d before): ${pre_base_min:.2f} (Required: < ${base_avg*0.85:.2f} to prove prior uptrend)")
                
                if pre_base_min <= base_avg * 0.85:
                    print(f"  Pass: Prior uptrend verified")
                    if _debug_consolidation_and_breakout(df, prices, volumes, cand_start_idx, cand_end_idx, 
                                                         max_consolidation_range, 0.0050, 1.02, 1.3):
                        match_found = True
                        break
                else:
                    print(f"  Fail: No significant prior uptrend")
                    
    if not match_found:
        print("\nFail: No recent Flat Base Breakout detected.")


def _debug_consolidation_and_breakout(df, prices, volumes, start_idx, end_idx, 
                                      max_range, max_slope, breakout_threshold, volume_mult):
    """
    Shared debugging helper for the consolidation and breakout phases.
    """
    consolidation_data = prices[start_idx:end_idx]
    if len(consolidation_data) == 0:
        print("Fail: Consolidation data is empty")
        return False

    consolidation_p90 = np.percentile(consolidation_data, 90)
    consolidation_p10 = np.percentile(consolidation_data, 10)
    consolidation_max = np.max(consolidation_data)

    avg_price = np.mean(consolidation_data)
    dynamic_max_range = max_range
    if avg_price < 20.0:
        dynamic_max_range = max_range * 1.2
    elif avg_price < 50.0 and max_range > 1.25:
        dynamic_max_range = max_range * 1.0

    ratio = consolidation_p90 / consolidation_p10
    print(f"Consolidation band: P10=${consolidation_p10:.2f}, P90=${consolidation_p90:.2f}, Max=${consolidation_max:.2f}")
    print(f"Range ratio (P90/P10): {ratio:.2f}, Max allowed: {dynamic_max_range}")
    if ratio > dynamic_max_range:
        print(f"Fail: Consolidation range too wide")
        return False
    else:
        print(f"Pass: Consolidation range OK")

    x = np.arange(len(consolidation_data))
    slope, _, _, _, _ = linregress(x, consolidation_data)
    normalized_slope = abs(slope) / avg_price

    dynamic_max_slope = max_slope
    if avg_price < 20.0:
        dynamic_max_slope = max_slope * 10
    elif avg_price < 50.0:
        dynamic_max_slope = max_slope * 5

    print(f"Consolidation slope (normalized): {normalized_slope:.6f}, Max allowed: {dynamic_max_slope:.4f}")
    if normalized_slope > dynamic_max_slope:
        print(f"Fail: Not flat enough — stock is trending, not consolidating")
        return False
    else:
        print(f"Pass: Flat consolidation")

    # ─── Phase 3: Detect the breakout ───
    recent_prices = prices[end_idx:]

    print(f"\nBreakout check: recent max ${np.max(recent_prices):.2f} vs threshold ${consolidation_max * breakout_threshold:.2f} (consolidation max ${consolidation_max:.2f} × {breakout_threshold})")

    if np.max(recent_prices) < (consolidation_max * breakout_threshold):
        print("Fail: No breakout detected — price didn't exceed consolidation max")
        return False

    breakout_day_idx = None
    for i, p in enumerate(recent_prices):
        if p > consolidation_max:
            breakout_day_idx = end_idx + i
            break

    if breakout_day_idx is None:
        print("Fail: Could not find specific breakout day")
        return False

    breakout_date = df.index[breakout_day_idx]
    print(f"Pass: Breakout on {breakout_date.strftime('%Y-%m-%d')} at ${prices[breakout_day_idx]:.2f}")

    # Multi-day volume confirmation
    avg_base_vol = np.mean(volumes[start_idx:end_idx])

    vol_window_start = max(breakout_day_idx - 2, 0)
    vol_window_end = min(breakout_day_idx + 3, len(volumes))
    avg_breakout_vol_5d = np.mean(volumes[vol_window_start:vol_window_end])

    max_single_day_vol = np.max(volumes[end_idx:])
    max_vol_day_idx = end_idx + np.argmax(volumes[end_idx:])

    print(f"\nVolume analysis:")
    print(f"  Base avg volume: {avg_base_vol:,.0f}")
    print(f"  5-day avg around breakout: {avg_breakout_vol_5d:,.0f} ({avg_breakout_vol_5d/avg_base_vol:.2f}x)")
    print(f"  Max single-day volume: {max_single_day_vol:,.0f} ({max_single_day_vol/avg_base_vol:.2f}x) on {df.index[max_vol_day_idx].strftime('%Y-%m-%d')}")

    vol_pass = (avg_breakout_vol_5d >= avg_base_vol * volume_mult or
                max_single_day_vol >= avg_base_vol * 2.0)

    if not vol_pass:
        print(f"Fail: Breakout volume not confirmed (need 5d avg ≥{volume_mult}x OR any day ≥2.0x base avg)")
        return False
    else:
        reason = []
        if avg_breakout_vol_5d >= avg_base_vol * volume_mult:
            reason.append(f"5d avg {avg_breakout_vol_5d/avg_base_vol:.2f}x ≥ {volume_mult}x")
        if max_single_day_vol >= avg_base_vol * 2.0:
            reason.append(f"single day {max_single_day_vol/avg_base_vol:.2f}x ≥ 2.0x")
        print(f"Pass: Volume confirmed ({', '.join(reason)})")

    print(f"\n✅ SUCCESS: Pattern Detected!")
    return True


if __name__ == "__main__":
    # Test Long Base
    print("\n--- Testing LONG BASE ---")
    debug_long_base_pattern("HOOD", start_date="2021-08-01", end_date="2024-03-31")
    
    # Test Flat Base
    print("\n--- Testing FLAT BASE ---")
    debug_flat_base_pattern("NVDA", start_date="2023-08-01", end_date="2024-02-28")
