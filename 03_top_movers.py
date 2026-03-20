import requests
import pandas as pd
import os
import sys
from io import StringIO

# --- ⚙️ CONFIG ---
# ดึงจาก Environment ของ GitHub ถ้าไม่มีให้ใส่ URL ตรงๆ ในเครื่องหมายคำพูดด้านล่าง
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_TOPMOVER") or "ใส่_URL_Webhook_ของคุณที่นี่_ถ้าจะรันในเครื่องตัวเอง"

def get_most_active(region="US", count=100):
    """ดึงหุ้นที่มีความเคลื่อนไหวสูงสุดจาก Yahoo Finance"""
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
        
        # ✅ แก้ไข FutureWarning: ใช้ StringIO ตามที่ Pandas แนะนำ
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
    if not tickers: 
        print(f"⚠️ No tickers to send for {market_name}")
        return
    
    if not DISCORD_URL or DISCORD_URL == "None":
        print("❌ Error: DISCORD_WEBHOOK is not defined!")
        return
        
    ticker_str = "\n".join(tickers)
    msg = {
        "content": f"🏆 **TOP MOVERS: {market_name}**\nพบหุ้นที่มีความเคลื่อนไหวสูงสุด {len(tickers)} อันดับแรก\n```text\n{ticker_str}\n```"
    }
    
    try:
        res = requests.post(DISCORD_URL, json=msg)
        if res.status_code == 204:
            print(f"✅ Successfully sent {market_name} to Discord.")
        else:
            print(f"❌ Discord error: {res.status_code}")
    except Exception as e:
        print(f"❌ Failed to send to Discord: {e}")

if __name__ == "__main__":
    market = sys.argv[1].upper() if len(sys.argv) > 1 else "US"
    
    if market == "TH":
        top_list = get_most_active("TH", 20)
        send_to_discord(top_list, "🇹🇭 THAI MARKET (TOP 20)")
    else:
        top_list = get_most_active("US", 100)
        send_to_discord(top_list, "🇺🇸 US MARKET (TOP 100)")
```
