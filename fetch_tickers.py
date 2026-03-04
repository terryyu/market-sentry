import requests
import json
import time

def get_nasdaq_large_caps():
    # Fetching NASDAQ screener data
    # We use the Nasdaq API endpoint for their stock screener
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=2000&exchange=NASDAQ&marketcap=mega|large"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        tickers = []
        rows = data.get('data', {}).get('table', {}).get('rows', [])
        for row in rows:
            symbol = row.get('symbol')
            # Handle class shares like BRK.B correctly for yfinance (BRK-B)
            if symbol and not symbol.endswith('W'): # avoid warrants
                tickers.append(symbol.replace('^', '-').replace('.', '-'))
                
        return sorted(list(set(tickers)))
    except Exception as e:
        print(f"Failed to fetch NASDAQ large caps: {e}")
        return []

if __name__ == "__main__":
    tickers = get_nasdaq_large_caps()
    print(f"Found {len(tickers)} large/mega cap NASDAQ stocks.")
    print(tickers[:20]) # Print first 20 as sanity check
