import os
import yfinance as yf
from supabase import create_client
import requests
import datetime
import time

# --- ⚙️ CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

# รับค่า TEST_MODE
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

# Settings
CRASH_THRESHOLD = -1.5 

def notify(msg):
    prefix = "🧪 [TEST] " if IS_TEST_MODE else ""
    requests.post(DISCORD_URL, json={"content": prefix + msg})

def get_market_sentiment():
    if IS_TEST_MODE:
        return {'TH': True, 'US': True} 

    markets = {'TH': '^SET.BK', 'US': '^GSPC'}
    status = {}
    for region, ticker in markets.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if len(df) < 2:
                status[region] = True
                continue
            change = ((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
            status[region] = change > CRASH_THRESHOLD
        except:
            status[region] = True
    return status

def run_monitor():
    print(f"🚀 Starting Monitor [{TABLE_NAME}]...")
    market_health = get_market_sentiment()
    
    # ดึงข้อมูลหุ้นทั้งหมด
    res = supabase.table(TABLE_NAME).select("*").neq("status", "sold").execute()
    stocks = res.data
    
    print(f"🔍 Scanning {len(stocks)} stocks for updates...")
    
    updates_count = 0
    
    for item in stocks:
        ticker = item['ticker']
        region = 'TH' if '.BK' in ticker else 'US'
        
        # Check Circuit Breaker
        if not market_health.get(region, True):
            continue

        try:
            # ดึงราคา
            stock = yf.Ticker(ticker)
            # ดึงประวัติ 1 ปี เพื่อหา 52-Week High
            hist = stock.history(period="1y")
            
            if len(hist) < 2: continue
            
            current_price = hist['Close'].iloc[-1]
            high_52w = hist['High'].max() # ราคาสูงสุดใน 1 ปี
            
            # --- LOGIC การอัปเดต Database ---
            update_data = {}
            
            # 1. อัปเดตราคาล่าสุดเสมอ (ให้ User เห็นว่าบอททำงาน)
            update_data['last_price'] = current_price
            update_data['last_update'] = datetime.datetime.now().isoformat()
            
            # 2. ถ้าเป็นหุ้นใหม่ (base_high เป็น NULL หรือ 0) ให้ตั้งค่าเริ่มต้น
            if not item.get('base_high') or item.get('base_high') == 0:
                print(f"   🆕 Init {ticker}: Base High set to {high_52w:.2f}")
                update_data['base_high'] = high_52w
                update_data['highest_price'] = current_price # เริ่มต้นที่ราคาปัจจุบัน
            
            # 3. เช็ค New High (All-time high ตั้งแต่บอทเฝ้า)
            prev_highest = item.get('highest_price') or 0
            if current_price > prev_highest:
                update_data['highest_price'] = current_price
            
            # 4. ส่งข้อมูลกลับเข้า Database
            supabase.table(TABLE_NAME).update(update_data).eq("id", item['id']).execute()
            updates_count += 1
            
            # (Optional) Breakout Alert
            base_high = item.get('base_high') or high_52w
            if current_price > base_high and item['status'] == 'watching':
                notify(f"🚀 **BREAKOUT**: {ticker} crossed Base High ({base_high:.2f})!\nCurrent: {current_price:.2f}")
                # สั่งซื้อ (เปลี่ยน status)
                # supabase.table(TABLE_NAME).update({"status": "bought", "buy_price": current_price}).eq("id", item['id']).execute()

        except Exception as e:
            # print(f"❌ Error {ticker}: {e}")
            continue
            
    print(f"✅ Updated {updates_count} tickers in Database.")

if __name__ == "__main__":
    run_monitor()
