import requests
import pandas as pd
import os
import sys

# --- ⚙️ CONFIG ---
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

def get_most_active(region="US", count=100):
    """ดึงหุ้นที่มีความเคลื่อนไหวสูงสุดจาก Yahoo Finance"""
    print(f"🌐 Fetching Top {count} Most Active stocks for {region}...")
    
    # URL สำหรับ US และ TH (Yahoo Finance Screener)
    if region == "TH":
        url = f"https://finance.yahoo.com/markets/stocks/most-active/?dependent=it&region=TH"
        limit = 20
    else:
        url = f"https://finance.yahoo.com/markets/stocks/most-active/?start=0&count={count}"
        limit = count

    try:
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=header)
        tables = pd.read_html(res.text)
        df = tables[0]
        
        # คัดเอาเฉพาะชื่อย่อ (Symbol)
        tickers = df['Symbol'].head(limit).tolist()
        return tickers
    except Exception as e:
        print(f"❌ Error fetching {region} movers: {e}")
        return []

def send_to_discord(tickers, market_name):
    if not tickers: return
    
    ticker_str = "\n".join(tickers)
    msg = {
        "content": f"🏆 **TOP MOVERS: {market_name}**\nพบหุ้นที่มีความเคลื่อนไหวสูงสุด {len(tickers)} อันดับแรก\n```text\n{ticker_str}\n```"
    }
    requests.post(DISCORD_URL, json=msg)

if __name__ == "__main__":
    market = sys.argv[1] if len(sys.argv) > 1 else "US"
    
    if market == "TH":
        top_th = get_most_active("TH", 20)
        send_to_discord(top_th, "🇹🇭 THAI MARKET (TOP 20)")
    else:
        top_us = get_most_active("US", 100)
        send_to_discord(top_us, "🇺🇸 US MARKET (TOP 100)")
