import requests
import pandas as pd
import os
import sys
from io import StringIO

# --- ⚙️ CONFIG ---
# Get Discord Webhook from environment variable
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_TOPMOVER")

def get_most_active(region="US", count=100):
    """Fetch most active stocks from Yahoo Finance"""
    print(f"🌐 Fetching Top {count} Most Active stocks for {region}...")
    
    if region == "TH":
        url = "https://finance.yahoo.com/markets/stocks/most-active/?dependent=it&region=TH"
        limit = 20
    else:
        url = f"https://finance.yahoo.com/markets/stocks/most-active/?start=0&count={count}"
        limit = count

    try:
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=header, timeout=15)
        
        # Use StringIO to wrap the HTML string as recommended by Pandas
        html_data = StringIO(res.text)
        tables = pd.read_html(html_data)
        
        if not tables:
            print(f"⚠️ No tables found for {region}")
            return []
            
        df = tables[0]
        tickers = df['Symbol'].head(limit).tolist()
        return tickers
    except Exception as e:
        print(f"❌ Error fetching {region} movers: {e}")
        return []

def send_to_discord(tickers, market_name):
    """Send ticker list to Discord"""
    if not tickers: 
        print(f"⚠️ No tickers to send for {market_name}")
        return
    
    if not DISCORD_URL or DISCORD_URL == "None":
        print("❌ Error: DISCORD_WEBHOOK_TOPMOVER is not defined!")
        return
        
    ticker_str = "\n".join(tickers)
    msg = {
        "content": f"🏆 **TOP MOVERS: {market_name}**\nพบหุ้นที่มีความเคลื่อนไหวสูงสุด {len(tickers)} อันดับแรก\n```text\n{ticker_str}\n```"
    }
    
    try:
        res = requests.post(DISCORD_URL, json=msg)
        if res.status_code in [200, 204]:
            print(f"✅ Successfully sent {market_name} to Discord.")
        else:
            print(f"❌ Discord error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ Failed to send to Discord: {e}")

if __name__ == "__main__":
    # 🧩 Smart logic: If no argument is provided, run both TH and US
    if len(sys.argv) > 1:
        market = sys.argv[1].upper()
        if market == "TH":
            top_list = get_most_active("TH", 20)
            send_to_discord(top_list, "🇹🇭 THAI MARKET (TOP 20)")
        elif market == "US":
            top_list = get_most_active("US", 100)
            send_to_discord(top_list, "🇺🇸 US MARKET (TOP 100)")
    else:
        # Default behavior: Run both
        print("🚀 No market specified, running both TH and US...")
        th_list = get_most_active("TH", 20)
        send_to_discord(th_list, "🇹🇭 THAI MARKET (TOP 20)")
        
        us_list = get_most_active("US", 100)
        send_to_discord(us_list, "🇺🇸 US MARKET (TOP 100)")
