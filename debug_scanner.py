import pandas as pd
import numpy as np
from scipy.stats import linregress
import yfinance as yf


def debug_pattern(ticker, start_date=None, end_date=None, period="2y"):
    print(f"\n=======================================================")
    print(f"--- Debugging {ticker} ---")
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
    # Find the HIGHEST price point that precedes a significant decline (≥30%).
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

    # Scale minimum base duration with decline severity
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

    consolidation_data = prices[trough_idx:consolidation_end_idx]
    if len(consolidation_data) == 0:
        print("Fail: Consolidation data is empty")
        return

    # Use P90/P10 for the core band, and actual max for breakout threshold
    consolidation_p90 = np.percentile(consolidation_data, 90)
    consolidation_p10 = np.percentile(consolidation_data, 10)
    consolidation_max = np.max(consolidation_data)

    avg_price = np.mean(consolidation_data)
    dynamic_max_range = 1.50
    if avg_price < 20.0:
        dynamic_max_range = 1.80
    elif avg_price < 50.0:
        dynamic_max_range = 1.50

    ratio = consolidation_p90 / consolidation_p10
    print(f"Consolidation band: P10=${consolidation_p10:.2f}, P90=${consolidation_p90:.2f}, Max=${consolidation_max:.2f}")
    print(f"Range ratio (P90/P10): {ratio:.2f}, Max allowed: {dynamic_max_range}")
    if ratio > dynamic_max_range:
        print(f"Fail: Consolidation range too wide")
        return
    else:
        print(f"Pass: Consolidation range OK")

    # Flatness check via linear regression
    x = np.arange(len(consolidation_data))
    slope, _, _, _, _ = linregress(x, consolidation_data)
    normalized_slope = abs(slope) / avg_price

    dynamic_max_slope = 0.0015
    if avg_price < 20.0:
        dynamic_max_slope = 0.015
    elif avg_price < 50.0:
        dynamic_max_slope = 0.0075

    print(f"Consolidation slope (normalized): {normalized_slope:.6f}, Max allowed: {dynamic_max_slope:.4f}")
    if normalized_slope > dynamic_max_slope:
        print(f"Fail: Not flat enough — stock is trending, not consolidating")
        return
    else:
        print(f"Pass: Flat consolidation")

    # ─── Phase 3: Detect the breakout ───
    recent_prices = prices[consolidation_end_idx:]
    breakout_threshold = 1.02

    print(f"\nBreakout check: recent max ${np.max(recent_prices):.2f} vs threshold ${consolidation_max * breakout_threshold:.2f} (consolidation max ${consolidation_max:.2f} × {breakout_threshold})")

    if np.max(recent_prices) < (consolidation_max * breakout_threshold):
        print("Fail: No breakout detected — price didn't exceed consolidation max")
        return

    # Find the first breakout day
    breakout_day_idx = None
    for i, p in enumerate(recent_prices):
        if p > consolidation_max:
            breakout_day_idx = consolidation_end_idx + i
            break

    if breakout_day_idx is None:
        print("Fail: Could not find specific breakout day")
        return

    breakout_date = df.index[breakout_day_idx]
    print(f"Pass: Breakout on {breakout_date.strftime('%Y-%m-%d')} at ${prices[breakout_day_idx]:.2f}")

    # Multi-day volume confirmation
    avg_base_vol = np.mean(volumes[trough_idx:consolidation_end_idx])

    # 5-day average around breakout
    vol_window_start = max(breakout_day_idx - 2, 0)
    vol_window_end = min(breakout_day_idx + 3, len(volumes))
    avg_breakout_vol_5d = np.mean(volumes[vol_window_start:vol_window_end])

    # Max single day in breakout window
    max_single_day_vol = np.max(volumes[consolidation_end_idx:])
    max_vol_day_idx = consolidation_end_idx + np.argmax(volumes[consolidation_end_idx:])

    print(f"\nVolume analysis:")
    print(f"  Base avg volume: {avg_base_vol:,.0f}")
    print(f"  5-day avg around breakout: {avg_breakout_vol_5d:,.0f} ({avg_breakout_vol_5d/avg_base_vol:.2f}x)")
    print(f"  Max single-day volume: {max_single_day_vol:,.0f} ({max_single_day_vol/avg_base_vol:.2f}x) on {df.index[max_vol_day_idx].strftime('%Y-%m-%d')}")

    vol_pass = (avg_breakout_vol_5d >= avg_base_vol * 1.3 or
                max_single_day_vol >= avg_base_vol * 2.0)

    if not vol_pass:
        print("Fail: Breakout volume not confirmed (need 5d avg ≥1.3x OR any day ≥2.0x base avg)")
        return
    else:
        reason = []
        if avg_breakout_vol_5d >= avg_base_vol * 1.3:
            reason.append(f"5d avg {avg_breakout_vol_5d/avg_base_vol:.2f}x ≥ 1.3x")
        if max_single_day_vol >= avg_base_vol * 2.0:
            reason.append(f"single day {max_single_day_vol/avg_base_vol:.2f}x ≥ 2.0x")
        print(f"Pass: Volume confirmed ({', '.join(reason)})")

    print("\n✅ SUCCESS: Long Base Consolidation Breakout Detected!")


if __name__ == "__main__":
    test_tickers = ["AAPL", "TSLA"]
    for t in test_tickers:
        debug_pattern(t)

    # User's specific Robinhood test
    # Testing Robinhood history data, from IPO (2021) to 2024 March to catch the true breakout
    debug_pattern("HOOD", start_date="2021-08-01", end_date="2024-03-31")
