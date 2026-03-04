import pandas as pd
import numpy as np
from scipy.signal import find_peaks
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
    
    if len(df) < 150: # Reduced from 252 so we can test smaller historical slices
        print(f"Fail: Not enough data (< 150 days)")
        return
        
    prices = df['Close'].values
    
    # 1. Find prominent peaks and troughs
    # prominence is based on absolute price changes (e.g., $5 drops) rather than relative
    # this helps catch massive drops like HOOD that went from $80 to $8
    peaks, _ = find_peaks(prices, distance=30, prominence=5)
    troughs, _ = find_peaks(-prices, distance=30, prominence=5)
    
    if len(peaks) == 0 or len(troughs) == 0:
        print(f"Fail: Not enough peaks/troughs (peaks found: {len(peaks)}, troughs found: {len(troughs)})")
        return
        
    last_peak_idx = peaks[-1]
    
    subsequent_troughs = troughs[troughs > last_peak_idx]
    
    if len(subsequent_troughs) == 0:
        print("Fail: No major troughs found AFTER the last major peak")
        return
        
    bottom_idx = subsequent_troughs[0]
    
    t1_decline_days = bottom_idx - last_peak_idx
    print(f"Metrics -> Peak Index: {last_peak_idx}, Bottom Index: {bottom_idx}")
    if t1_decline_days < 20: 
        print(f"Fail: Decline period too short (T1 = {t1_decline_days} days < 20)")
        return
    else:
        print(f"Pass: Decline period T1 = {t1_decline_days} days")

    breakout_window = 5
    current_idx = len(prices) - 1
    consolidation_end_idx = current_idx - breakout_window
    
    if bottom_idx >= consolidation_end_idx:
        print("Fail: Bottom is too recent, so there is no consolidation period")
        return
        
    t2_consolidation_days = consolidation_end_idx - bottom_idx
    
    # Calculate required consolidation time
    # Normally 2x the decline. But max out the *requirement* at 90 days so 
    # massive multi-year crashes don't demand 2+ year flat bases.
    required_t2 = min(2 * t1_decline_days, 90)
    
    if t2_consolidation_days < required_t2:
        print(f"Fail: Consolidation too short (T2 = {t2_consolidation_days} days < required {required_t2} days)")
        return
    elif t2_consolidation_days < 60:
        print(f"Fail: Consolidation too short. Met the 2x rule, but T2 = {t2_consolidation_days} days < 60 days (3 months)")
        return
    else:
        print(f"Pass: Consolidation period T2 = {t2_consolidation_days} days (>= 2*T1 and >= 60 days)")
        
    consolidation_data = prices[bottom_idx : consolidation_end_idx]
    if len(consolidation_data) == 0: 
        print("Fail: Consolidation data is empty")
        return
    
    consolidation_max = np.max(consolidation_data)
    consolidation_min = np.min(consolidation_data)
    
    avg_price = np.mean(consolidation_data)
    dynamic_max_range = 1.15
    if avg_price < 20.0:
        dynamic_max_range = 2.50
    elif avg_price < 50.0:
        dynamic_max_range = 1.50
    
    print(f"Consolidation range: Min = ${consolidation_min:.2f}, Max = ${consolidation_max:.2f}")
    if consolidation_max > consolidation_min * dynamic_max_range:
        print(f"Fail: Consolidation range too wide. Max is > {dynamic_max_range} * Min. (Ratio: {consolidation_max/consolidation_min:.2f})")
        return 
    else:
        print(f"Pass: Consolidation range is tight enough (Ratio: {consolidation_max/consolidation_min:.2f} <= {dynamic_max_range})")

    # NEW: Slope check
    x = np.arange(len(consolidation_data))
    slope, _, _, _, _ = linregress(x, consolidation_data)
    avg_price = np.mean(consolidation_data)
    normalized_slope = abs(slope) / avg_price
    
    dynamic_max_slope = 0.0015
    if avg_price < 20.0:
        dynamic_max_slope = 0.030
    elif avg_price < 50.0:
        dynamic_max_slope = 0.0075
    
    print(f"Consolidation Slope (normalized): {normalized_slope:.6f}")
    if normalized_slope > dynamic_max_slope:
        print(f"Fail: Consolidation is not flat enough (normalized slope {normalized_slope:.6f} > {dynamic_max_slope:.4f}). The stock is trending, not consolidating.")
        return
    else:
        print(f"Pass: Consolidation is flat (normalized slope {normalized_slope:.6f} <= {dynamic_max_slope:.4f})")

    recent_prices = prices[consolidation_end_idx:]
    print(f"Recent max price: ${np.max(recent_prices):.2f}, Breakout threshold: ${consolidation_max * 1.02:.2f}")
    
    breakout_idx = -1
    for i, p in enumerate(recent_prices):
        if p > (consolidation_max * 1.02):
            breakout_idx = consolidation_end_idx + i
            break
            
    if breakout_idx == -1:
        print("Fail: No breakout detected in recent prices")
        return
    else:
        breakout_date = df.index[breakout_idx]
        print(f"Pass: Breakout detected! Triggered on {breakout_date.strftime('%Y-%m-%d')} at price ${recent_prices[breakout_idx - consolidation_end_idx]:.2f}")
        
    avg_vol = df['Volume'].iloc[bottom_idx : consolidation_end_idx].mean()
    recent_vol = df['Volume'].iloc[breakout_idx]
    
    print(f"Breakout Volume: {recent_vol:,.0f}, Avg Consolidation Volume: {avg_vol:,.0f}")
    if recent_vol < (avg_vol * 1.5):
        print("Fail: Breakout volume not high enough (recent volume < 1.5x avg volume)")
        return
    else:
        print("Pass: Strong volume detected!")
    
    print("SUCCESS: Target Pattern Matched!")

if __name__ == "__main__":
    test_tickers = ["AAPL", "TSLA"]
    for t in test_tickers:
        debug_pattern(t)
        
    # User's specific Robinhood test
    # Testing Robinhood history data, from IPO (2021) to 2024 March to catch the true peak
    debug_pattern("HOOD", start_date="2021-08-01", end_date="2024-03-31")
