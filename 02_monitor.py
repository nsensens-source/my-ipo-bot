import os
import yfinance as yf
from supabase import create_client
import requests
import datetime
import time
import pandas as pd

# --- ⚙️ CONFIGURATION ---
print("⚙️ Initializing Configuration...")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

def notify(msg):
    prefix = "🧪 [TEST] " if IS_TEST_MODE else "🟢 [PROD] "
    try:
        requests.post(DISCORD_URL, json={"content": prefix + msg})
    except: pass

def calculate_rsi(data, window=14):
    """คำนวณ RSI และส่งกลับเป็นค่าตัวเลขตัวเดียว (Float)"""
    try:
        if len(data) < window + 1: return 50.0
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        # ดึงเฉพาะค่าล่าสุดออกมาเป็นตัวเลขตัวเดียว
        val = rsi_series.iloc[-1]
        return float(val) if not pd.isna(val) else 50.0
    except:
        return 50.0

def run_monitor():
    print(f"🚀 Starting Monitor Process on Table: '{TABLE_NAME}'")
    
    try:
        res = supabase.table(TABLE_NAME).select("*").execute()
        stocks = res.data
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    if not stocks:
        print("⚠️ Warning: Table is empty.")
        return

    updates_count = 0
    error_count = 0

    print("-" * 50)
    
    for item in stocks:
        ticker = item['ticker']
        status = item.get('status', 'watching')
        m_type = item.get('market_type', 'UNKNOWN')
        
        if status == 'sold': continue

        print(f"🔍 Analyzing: {ticker}", end=" ")

        try:
            stock = yf.Ticker(ticker)
            # ดึงราคา 2 วันล่าสุด
            hist = stock.history(period="2d")
            
            if hist.empty:
                print("❌ No price data")
                error_count += 1
                continue
            
            # บังคับเป็น float เพื่อป้องกัน format error
            current_price = float(hist['Close'].iloc[-1])

            # คำนวณ RSI (ใช้ข้อมูล 1 เดือน)
            full_hist = stock.history(period="1mo")
            rsi_val = calculate_rsi(full_hist['Close'])
            
            # --- อัปเดตข้อมูลลง Database ---
            update_payload = {
                "last_price": current_price,
                "last_update": datetime.datetime.now().isoformat()
            }
            
            # จัดการเรื่อง Base High ถ้ายังไม่มีค่า
            base_high = float(item.get('base_high') or 0)
            if base_high == 0:
                y_hist = stock.history(period="1y")
                base_high = float(y_hist['High'].max()) if not y_hist.empty else current_price
                update_payload['base_high'] = base_high
                update_payload['highest_price'] = current_price

            # บันทึกกลับด้วย ticker (ปลอดภัยกว่า id ถ้าโครงสร้างเปลี่ยน)
            supabase.table(TABLE_NAME).update(update_payload).eq("ticker", ticker).execute()
            
            updates_count += 1
            print(f"✅ Updated: ${current_price:.2f} | RSI: {rsi_val:.1f}")

            # ป้องกันโดน Yahoo บล็อก
            time.sleep(0.2)

        except Exception as e:
            print(f"❌ Error: {e}")
            error_count += 1

    summary = f"📊 **Monitor Summary**: Updated {updates_count}, Errors {error_count}"
    print("-" * 50 + f"\n{summary}")
    if IS_TEST_MODE and updates_count > 0:
        notify(summary)

if __name__ == "__main__":
    run_monitor()
