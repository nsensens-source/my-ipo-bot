import os
import yfinance as yf
from supabase import create_client
import requests
import datetime

# --- ⚙️ CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

# รับค่า TEST_MODE
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"

# เลือกตารางอัตโนมัติ
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

# Settings
STOP_LOSS_IPO = 0.08
STOP_LOSS_SP500 = 0.04
CRASH_THRESHOLD = -1.5 

def notify(msg):
    prefix = "🧪 [TEST] " if IS_TEST_MODE else ""
    requests.post(DISCORD_URL, json={"content": prefix + msg})

def get_market_sentiment():
    if IS_TEST_MODE:
        print(f"🧪 TEST MODE ON: Using Table '{TABLE_NAME}' & Bypassing Circuit Breaker.")
        return {'TH': True, 'US': True} 

    print(f"🛡️ PROD MODE: Using Table '{TABLE_NAME}' & Checking Market Health...")
    markets = {'TH': '^SET.BK', 'US': '^GSPC'}
    status = {}
    
    for region, ticker in markets.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if len(df) < 2:
                status[region] = True
                continue
            prev = df['Close'].iloc[-2]
            curr = df['Close'].iloc[-1]
            change = ((curr - prev) / prev) * 100
            status[region] = change > CRASH_THRESHOLD
        except:
            status[region] = True
            
    return status

def run_monitor():
    start_time = datetime.datetime.now()
    market_health = get_market_sentiment()
    
    # ดึงข้อมูลจาก DB
    res = supabase.table(TABLE_NAME).select("*").neq("status", "sold").execute()
    stocks = res.data
    
    print(f"🔍 Scanning {len(stocks)} stocks...")
    
    scanned_count = 0
    error_count = 0
    action_count = 0

    for item in stocks:
        ticker = item['ticker']
        market_type = item.get('market_type', 'UNKNOWN')
        
        # Determine Region
        region = 'TH' if '.BK' in ticker else 'US'
        
        # Check Circuit Breaker (Skip if market crashed)
        if not market_health.get(region, True):
            print(f"   ⛔ Skip {ticker} (Market Unsafe)")
            continue

        try:
            # Get Data
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y") # 1 Year for 52-week High
            
            if len(df) < 2:
                error_count += 1
                continue
                
            current_price = df['Close'].iloc[-1]
            scanned_count += 1
            
            # --- TRADING LOGIC (Simplified for monitor) ---
            # 1. Breakout Check (Example Logic)
            # หา High สูงสุดในรอบ 1 ปี (ไม่รวมวันนี้)
            high_52w = df['High'][:-1].max() if len(df) > 1 else current_price
            
            # ถ้าวันนี้ราคาทะลุ High เดิม (New High) -> BUY SIGNAL
            if current_price > high_52w and item['status'] == 'watching':
                msg = f"🚀 **BREAKOUT ALERT**: {ticker} hit New 52-Week High!\nPrice: {current_price:.2f}"
                notify(msg)
                # Update Status (ในระบบจริงจะสั่งซื้อตรงนี้)
                # supabase.table(TABLE_NAME).update({"status": "bought"}).eq("ticker", ticker).execute()
                action_count += 1
                
        except Exception as e:
            # print(f"   ❌ Error {ticker}: {e}") # ปิด Error เพื่อความสะอาดใน Log
            error_count += 1
            continue

    # --- REPORTING (เฉพาะ TEST MODE หรือจบวัน) ---
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    
    print(f"✅ Finished. Scanned: {scanned_count}, Errors: {error_count}, Actions: {action_count}")
    
    # ถ้าเป็น Test Mode ให้ส่งสรุปเข้า Discord เสมอ จะได้รู้ว่ารันจบ
    if IS_TEST_MODE:
        summary = f"📊 **SCAN COMPLETE (TEST MODE)**\n"
        summary += f"• Table: `{TABLE_NAME}`\n"
        summary += f"• Scanned: {scanned_count} tickers\n"
        summary += f"• Errors/Delisted: {error_count}\n"
        summary += f"• Actions Triggered: {action_count}\n"
        summary += f"• Time Taken: {duration}"
        notify(summary)

if __name__ == "__main__":
    run_monitor()
