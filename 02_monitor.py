import os
import yfinance as yf
from supabase import create_client
import requests
import datetime
import time

# --- ⚙️ CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

def notify(msg):
    prefix = "🧪 [TEST] " if IS_TEST_MODE else ""
    requests.post(DISCORD_URL, json={"content": prefix + msg})

def run_monitor():
    print(f"🚀 Starting Smart Monitor [{TABLE_NAME}]...")
    
    # ดึงข้อมูลจาก DB เฉพาะตัวที่ยังไม่ได้ขาย
    res = supabase.table(TABLE_NAME).select("*").neq("status", "sold").execute()
    stocks = res.data
    
    updates_count = 0
    
    for item in stocks:
        ticker = item['ticker']
        is_thai = '.BK' in ticker
        
        # --- ⚙️ SET TP/SL BY REGION ---
        if is_thai:
            tp_percent = 1.05  # กำไร 5%
            sl_percent = 0.97  # ขาดทุน 3%
        else:
            tp_percent = 1.10  # กำไร 10%
            sl_percent = 0.95  # ขาดทุน 5%

        try:
            # ใช้ period="2d" เพื่อบังคับดึงข้อมูลใหม่ล่าสุด
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d") 
            
            if len(hist) < 1: continue
            
            current_price = hist['Close'].iloc[-1]
            
            # --- 🛠️ UPDATE PRICE DATA ---
            update_payload = {
                "last_price": current_price,
                "last_update": datetime.datetime.now().isoformat()
            }
            
            # ถ้าเป็นหุ้นถืออยู่ (Bought) ให้เช็คจุดขาย
            if item['status'] == 'bought':
                buy_price = item.get('buy_price', 0)
                
                if buy_price > 0:
                    # 💰 Check Take Profit
                    if current_price >= (buy_price * tp_percent):
                        notify(f"💰 **TAKE PROFIT**: {ticker}\nSell at: {current_price:.2f} (Gain: {((current_price/buy_price)-1)*100:.2f}%)")
                        update_payload['status'] = 'sold'
                        update_payload['sell_price'] = current_price
                    
                    # 📉 Check Stop Loss
                    elif current_price <= (buy_price * sl_percent):
                        notify(f"❌ **STOP LOSS**: {ticker}\nSell at: {current_price:.2f} (Loss: {((current_price/buy_price)-1)*100:.2f}%)")
                        update_payload['status'] = 'sold'
                        update_payload['sell_price'] = current_price

            # อัปเดต DB
            supabase.table(TABLE_NAME).update(update_payload).eq("id", item['id']).execute()
            updates_count += 1
            
            # ชะลอเพื่อป้องกันการโดนบล็อก
            time.sleep(0.3) 

        except Exception as e:
            continue
            
    print(f"✅ Finished! Updated {updates_count} tickers.")

if __name__ == "__main__":
    run_monitor()
