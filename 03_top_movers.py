import requests
import pandas as pd
import os
import sys
from io import StringIO
import re

# --- ⚙️ CONFIG ---
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_TOPMOVER")

def clean_ticker(raw_ticker):
    """
    🧩 ฟังก์ชันล้างชื่อหุ้น: กำจัดตัวอักษรขยะ เช่น 'P PLUG' -> 'PLUG'
    หรือ 'M MARA' -> 'MARA' ที่เกิดจากการดึงปุ่ม Follow ในหน้าเว็บมาด้วย
    """
    if not isinstance(raw_ticker, str):
        return str(raw_ticker)
    
    # แยกคำด้วยช่องว่าง แล้วเอาคำสุดท้าย
    parts = raw_ticker.split()
    clean_name = parts[-1] if parts else raw_ticker
    
    # ล้างตัวอักษรที่ไม่ใช่ A-Z หรือตัวเลข หรือจุด (.)
    clean_name = re.sub(r'[^A-Z0-9.]', '', clean_name.upper())
    return clean_name

def get_most_active(region="US", count=100):
    """ดึงหุ้นที่มีความเคลื่อนไหวสูงสุดแบบเจาะจงภูมิภาค"""
    print(f"🌐 Fetching Top {count} for {region}...")
    
    # 🧩 เปลี่ยน URL เป็น Screener ที่ระบุภูมิภาคชัดเจน
    if region == "TH":
        # เจาะจงภูมิภาค TH (SET)
        url = "https://finance.yahoo.com/screener/predefined/most_actives?count=25&offset=0&region=TH"
        limit = 20
    else:
        # เจาะจงภูมิภาค US
        url = f"https://finance.yahoo.com/screener/predefined/most_actives?count={count}&offset=0&region=US"
        limit = count

    try:
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        res = requests.get(url, headers=header, timeout=20)
        
        # ใช้ StringIO ห่อ HTML
        html_data = StringIO(res.text)
        tables = pd.read_html(html_data)
        
        if not tables:
            print(f"⚠️ No tables found for {region}")
            return []
            
        df = tables[0]
        
        # ดึงรายชื่อมาล้างขยะทีละตัว
        raw_tickers = df['Symbol'].head(limit).tolist()
        clean_tickers = [clean_ticker(t) for t in raw_tickers if t]
        
        # 🧩 Double Check ตลาดไทย: ถ้าสั่ง TH แต่ไม่มีตัวไหนลงท้ายด้วย .BK เลย แสดงว่าโดน Redirect
        if region == "TH" and not any(".BK" in t for t in clean_tickers):
            print(f"❌ Error: Yahoo redirected TH request to US. Attempting fallback...")
            return []

        return clean_tickers
    except Exception as e:
        print(f"❌ Error fetching {region}: {e}")
        return []

def send_to_discord(tickers, market_name):
    if not tickers: 
        print(f"⚠️ No data for {market_name}. Skipping.")
        return
    
    if not DISCORD_URL or DISCORD_URL == "None":
        print("❌ Error: DISCORD_WEBHOOK_TOPMOVER is missing!")
        return
        
    ticker_str = "\n".join(tickers)
    msg = {
        "content": f"🏆 **TOP MOVERS: {market_name}**\n```text\n{ticker_str}\n```"
    }
    
    try:
        res = requests.post(DISCORD_URL, json=msg)
        if res.status_code in [200, 204]:
            print(f"✅ Sent {market_name} to Discord.")
    except: pass

if __name__ == "__main__":
    # รันทั้งสองตลาดถ้าไม่มีระบุมา
    print("🚀 Running Top Movers Scanner...")
    
    # TH Market
    th_list = get_most_active("TH", 20)
    if th_list:
        send_to_discord(th_list, "🇹🇭 THAI MARKET (TOP 20)")
    else:
        print("⚠️ Failed to get TH stocks (Redirect issue).")
        
    # US Market
    us_list = get_most_active("US", 100)
    send_to_discord(us_list, "🇺🇸 US MARKET (TOP 100)")
