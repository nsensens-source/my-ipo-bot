import os
import yfinance as yf
from supabase import create_client
import requests
import datetime
import time

# --- ⚙️ CONFIGURATION ---
print("⚙️ Initializing Configuration...")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: SUPABASE_URL or SUPABASE_KEY is missing from environment variables!")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# รับค่า TEST_MODE
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

def notify(msg):
    prefix = "🧪 [TEST] " if IS_TEST_MODE else "🟢 [PROD] "
    try:
        requests.post(DISCORD_URL, json={"content": prefix + msg})
    except Exception as e:
        print(f"⚠️ Failed to send Discord notification: {e}")

def calculate_rsi(data, window=14):
    if len(data) < window + 1: return 50
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_monitor():
    print(f"🚀 Starting Monitor Process on Table: '{TABLE_NAME}'")
    
    # --- 1. ตรวจสอบการเชื่อมต่อและดึงข้อมูล ---
    try:
        # ดึงข้อมูลทั้งหมดมาตรวจสอบ (ไม่กรองใน Query เพื่อเลี่ยงปัญหา RLS/Status mismatch)
        res = supabase.table(TABLE_NAME).select("*").execute()
        stocks = res.data
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    if stocks is None:
        print("❌ Data Retrieval Error: Response from Supabase is None. Check your RLS policies!")
        return

    total_in_db = len(stocks)
    print(f"📊 Database Scan: Found {total_in_db} total tickers in '{TABLE_NAME}'")

    if total_in_db == 0:
        print("⚠️ Warning: Table is empty. Nothing to monitor.")
        return

    updates_count = 0
    error_count = 0
    skipped_sold = 0

    print("-" * 50)
    
    for item in stocks:
        ticker = item['ticker']
        status = item.get('status', 'watching')
        m_type = item.get('market_type', 'UNKNOWN')
        
        # กรองตัวที่ขายไปแล้วออกในระดับ Code
        if status == 'sold':
            skipped_sold += 1
            continue

        print(f"🔍 Analyzing: {ticker} | Type: {m_type} | Status: {status}")
        
        # --- 2. กำหนดค่า TP/SL ตามสัญชาติหุ้น ---
        is_thai = '.BK' in ticker
        if is_thai:
            tp_percent, sl_percent = 1.05, 0.97  # +5% / -3%
        else:
            tp_percent, sl_percent = 1.10, 0.95  # +10% / -5%

        try:
            # --- 3. ดึงราคาปัจจุบัน (Force Refresh 2d) ---
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            
            if hist.empty:
                print(f"   ⚠️ {ticker}: No price data found (Possible Delisted/Wrong Suffix)")
                error_count += 1
                continue
            
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price

            # --- 4. คำนวณ RSI สำหรับสัญญาณ Rebound ---
            full_hist = stock.history(period="1mo")
            rsi_val = calculate_rsi(full_hist['Close']) if len(full_hist) > 14 else 50
            
            # --- 5. LOGIC การแจ้งเตือน (Signals) ---
            signal_msg = ""
            
            # กุล่ม LONG: ดู New High / Breakout
            if "LONG" in m_type or "MOONSHOT" in m_type or "BASE" in m_type or "FAVOURITE" in m_type:
                base_high = item.get('base_high') or 0
                if current_price > base_high and base_high > 0:
                    signal_msg = f"🚀 **BREAKOUT**: {current_price:.2f} > {base_high:.2f}"
            
            # กลุ่ม SHORT: ดู RSI Oversold (เล่นเด้ง)
            elif "SHORT" in m_type:
                if rsi_val < 30:
                    signal_msg = f"📉 **REBOUND SIGNAL**: RSI={rsi_val:.2f} (Oversold)"

            # --- 6. LOGIC การขาย (TP/SL) ---
            update_payload = {
                "last_price": current_price,
                "last_update": datetime.datetime.now().isoformat()
            }

            if status == 'bought':
                buy_price = item.get('buy_price', 0)
                if buy_price > 0:
                    gain_loss = ((current_price / buy_price) - 1) * 100
                    if current_price >= (buy_price * tp_percent):
                        notify(f"💰 **TAKE PROFIT**: {ticker}\nSell: {current_price:.2f} (+{gain_loss:.2f}%)")
                        update_payload['status'] = 'sold'
                        update_payload['sell_price'] = current_price
                    elif current_price <= (buy_price * sl_percent):
                        notify(f"❌ **STOP LOSS**: {ticker}\nSell: {current_price:.2f} ({gain_loss:.2f}%)")
                        update_payload['status'] = 'sold'
                        update_payload['sell_price'] = current_price

            # --- 7. บันทึกข้อมูลกลับลง Database ---
            # ใช้คอลัมน์ 'id' เป็นตัวระบุแถว (ตรวจสอบชื่อคอลัมน์ใน Supabase ให้ตรงกัน)
            supabase.table(TABLE_NAME).update(update_payload).eq("id", item['id']).execute()
            updates_count += 1
            print(f"   ✅ Updated: Price=${current_price:.2f} | RSI={rsi_val:.1f}")

            # ป้องกัน Rate Limit
            time.sleep(0.2)

        except Exception as e:
            print(f"   ❌ Error processing {ticker}: {e}")
            error_count += 1

    # --- 8. สรุปรายงานการรัน ---
    summary = (
        f"📊 **Monitor Execution Summary**\n"
        f"• Total Checked: {updates_count}\n"
        f"• Sold (Skipped): {skipped_sold}\n"
        f"• Errors/Failed: {error_count}\n"
        f"• Time Taken: {datetime.datetime.now().strftime('%H:%M:%S')}"
    )
    print("-" * 50)
    print(summary)
    
    if IS_TEST_MODE:
        notify(summary)

if __name__ == "__main__":
    run_monitor()
