import sys
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from scipy.stats import linregress
import yfinance as yf
from fetch_tickers import get_nasdaq_large_caps

def find_consolidation_breakout(df: pd.DataFrame, 
                                min_decline_days: int = 20, 
                                min_consolidation_days: int = 60,
                                max_consolidation_range: float = 1.15, 
                                max_consolidation_slope: float = 0.0015,
                                breakout_threshold: float = 1.02, 
                                volume_multiplier: float = 1.5) -> bool:
    """
    Detects a 'Long Base Consolidation' or 'Rounding Bottom Breakout' pattern.
    
    Args:
        df: DataFrame with 'Close' and 'Volume' columns, indexed by Date. expected > 252 rows.
        min_decline_days: Minimum days for the initial decline (T1).
        min_consolidation_days: Minimum days the consolidation must last, e.g., 60 trading days = ~3 months.
        max_consolidation_range: The maximum ratio of highest to lowest price during consolidation (T2).
        max_consolidation_slope: The maximum absolute allowed slope (normalized) to ensure it is sideways, not climbing.
        breakout_threshold: The percentage by which the recent price must exceed the consolidation high.
        volume_multiplier: The required volume spike compared to the consolidation average.
    """
    if len(df) < 252:
        return False
        
    prices = df['Close'].values
    
    # 1. Find prominent peaks and troughs
    # prominence is 10% of max price to filter out micro-fluctuations
    peaks, _ = find_peaks(prices, distance=20, prominence=np.max(prices)*0.1)
    troughs, _ = find_peaks(-prices, distance=20, prominence=np.max(prices)*0.1)
    
    if len(peaks) == 0 or len(troughs) == 0:
        return False
        
    # Get the most recent major peak
    last_peak_idx = peaks[-1]
    
    # Find the first trough AFTER the last major peak
    subsequent_troughs = troughs[troughs > last_peak_idx]
    
    if len(subsequent_troughs) == 0:
        return False
        
    bottom_idx = subsequent_troughs[0]
    
    # Calculate T1 (Decline Period)
    t1_decline_days = bottom_idx - last_peak_idx
    if t1_decline_days < min_decline_days: 
        return False

    # 2. Analyze the Consolidation Period (T2)
    # Breakout window is the most recent 5 days
    breakout_window = 5
    current_idx = len(prices) - 1
    
    consolidation_end_idx = current_idx - breakout_window
    
    if bottom_idx >= consolidation_end_idx:
        return False
        
    t2_consolidation_days = consolidation_end_idx - bottom_idx
    
    # RULE: Consolidation (T2) must be at least 2x the decline period (T1) OR at least the strict minimum
    if t2_consolidation_days < (2 * t1_decline_days) or t2_consolidation_days < min_consolidation_days:
        return False
        
    consolidation_data = prices[bottom_idx : consolidation_end_idx]
    if len(consolidation_data) == 0: 
        return False
    
    consolidation_max = np.max(consolidation_data)
    consolidation_min = np.min(consolidation_data)
    
    # Dynamic range allowed: lower priced stocks (which have huge % moves on small $ moves) 
    # get a wider band than $100+ stocks
    avg_price = np.mean(consolidation_data)
    dynamic_max_range = max_consolidation_range
    if avg_price < 20.0:
        dynamic_max_range = 2.50 # Extremely forgiving for $10-15 stocks like HOOD was
    elif avg_price < 50.0:
        dynamic_max_range = 1.50 # Forgiving for mid-priced
        
    # Consolidation band must be relatively tight
    if consolidation_max > consolidation_min * dynamic_max_range:
        return False 

    # NEW: Consolidation must actually be flat (not steadily trending up like VNOM)
    # We use linear regression to find the slope of the consolidation period
    x = np.arange(len(consolidation_data))
    slope, _, _, _, _ = linregress(x, consolidation_data)
    
    # Normalize slope as a percentage of the average price
    avg_price = np.mean(consolidation_data)
    normalized_slope = abs(slope) / avg_price
    
    dynamic_max_slope = max_consolidation_slope
    if avg_price < 20.0:
        dynamic_max_slope = max_consolidation_slope * 20 # Tolerate much higher math slope for choppy low-priced stocks
    elif avg_price < 50.0:
        dynamic_max_slope = max_consolidation_slope * 5
    
    if normalized_slope > dynamic_max_slope:
        return False

    # 3. Detect the Breakout
    recent_prices = prices[consolidation_end_idx:]
    if np.max(recent_prices) < (consolidation_max * breakout_threshold):
        return False
        
    # Volume check for the breakout
    avg_vol = df['Volume'].iloc[bottom_idx : consolidation_end_idx].mean()
    recent_vol = df['Volume'].iloc[-1]
    
    if recent_vol < (avg_vol * volume_multiplier):
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
