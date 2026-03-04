import os
import yfinance as yf
from supabase import create_client
import requests
import datetime
import time
import pandas as pd

# --- ⚙️ CONFIGURATION ---
print("⚙️ Initializing Monitor (Signal Scanner)...")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

def notify(msg):
    prefix = "🔭 [MONITOR] " if IS_TEST_MODE else "📡 [SIGNAL] "
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
        val = rsi_series.iloc[-1]
        return float(val) if not pd.isna(val) else 50.0
    except:
        return 50.0

def run_monitor():
    print(f"🚀 Scanning for Signals on Table: '{TABLE_NAME}'")
    
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
    signal_count = 0
    error_count = 0
    deleted_count = 0 # เพิ่มตัวนับจำนวนหุ้นที่ถูกลบ

    print("-" * 50)
    
    for item in stocks:
        ticker = item['ticker']
        status = item.get('status', 'watching')
        m_type = item.get('market_type', 'UNKNOWN')
        
        if status in ['sold', 'signal_buy', 'signal_sell']: 
            continue

        print(f"🔍 Scanning: {ticker} ({status})", end=" ")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            
            # --- 🗑️ AUTO-DELETE LOGIC (ลบหุ้นที่ตายแล้ว) ---
            if hist.empty:
                print("❌ No price data (Delisted or Not Found) -> 🗑️ Auto-Deleting...")
                supabase.table(TABLE_NAME).delete().eq("ticker", ticker).execute()
                error_count += 1
                deleted_count += 1
                continue
            # -----------------------------------------------
            
            current_price = float(hist['Close'].iloc[-1])
            full_hist = stock.history(period="1mo")
            rsi_val = calculate_rsi(full_hist['Close'])
            
            update_payload = {
                "last_price": current_price,
                "last_update": datetime.datetime.now().isoformat()
            }
            
            base_high = float(item.get('base_high') or 0)
            if base_high == 0:
                y_hist = stock.history(period="1y")
                base_high = float(y_hist['High'].max()) if not y_hist.empty else current_price
                update_payload['base_high'] = base_high
                update_payload['highest_price'] = current_price

            is_thai = '.BK' in ticker
            tp_pct = 0.05 if is_thai else 0.10  
            sl_pct = 0.03 if is_thai else 0.05  
            
            signal_triggered = False

            if status == 'watching':
                # --- 🧹 DATA CLEANUP (ล้างราคาค้าง) ---
                if float(item.get('buy_price') or 0) > 0:
                    update_payload['buy_price'] = 0
                    update_payload['highest_price'] = 0
                # --------------------------------------

                # 1.1 Breakout Strategy (Long/Base/Moonshot)
                if any(x in m_type for x in ['LONG', 'BASE', 'MOONSHOT', 'FAVOURITE']):
                    if base_high > 0 and current_price > base_high:
                        
                        # 1. คำนวณเปอร์เซ็นต์ที่ราคาทะลุ Base ขึ้นมา
                        increase_pct = ((current_price - base_high) / base_high) * 100
                        
                        # 2. กำหนด Status ความแรงของ Breakout (ปรับตัวเลข % ได้ตามต้องการ)
                        if increase_pct >= 3.0:
                            strength_status = "🔥 High"    # ทะลุแรงมาก (> 3%)
                        elif increase_pct >= 1.0:
                            strength_status = "⚡ Medium" # ทะลุปานกลาง (1% - 3%)
                        else:
                            strength_status = "🟢 Low"    # เพิ่งเริ่มทะลุ (< 1%)

                        update_payload['status'] = 'signal_buy'
                        
                        # 3. สร้างข้อความส่งเข้า Discord แบบใหม่
                        alert_msg = f"🚀 **BREAKOUT**: {ticker} Price {current_price:.2f} > Base {base_high:.2f} | 📈 +{increase_pct:.2f}% [{strength_status}]"
                        notify(alert_msg)
                        
                        signal_triggered = True

                elif 'SHORT' in m_type:
                    if rsi_val < 30:
                        update_payload['status'] = 'signal_buy'
                        notify(f"📉 **OVERSOLD FOUND**: {ticker} RSI {rsi_val:.1f} < 30")
                        signal_triggered = True

            elif status == 'holding':
                buy_price = float(item.get('buy_price') or 0)
                if buy_price > 0:
                    if current_price >= buy_price * (1 + tp_pct):
                        update_payload['status'] = 'signal_sell'
                        notify(f"💰 **TP TARGET REACHED**: {ticker} @ {current_price:.2f} (+{tp_pct*100}%)")
                        signal_triggered = True
                    elif current_price <= buy_price * (1 - sl_pct):
                        update_payload['status'] = 'signal_sell'
                        notify(f"❌ **SL TRIGGERED**: {ticker} @ {current_price:.2f} (-{sl_pct*100}%)")
                        signal_triggered = True

            supabase.table(TABLE_NAME).update(update_payload).eq("ticker", ticker).execute()
            
            updates_count += 1
            if signal_triggered: signal_count += 1
            
            print(f"✅ Price: {current_price:.2f} | RSI: {rsi_val:.1f}" + (" [SIGNAL!!]" if signal_triggered else ""))

            time.sleep(0.1)

        except Exception as e:
            print(f"❌ Error: {e} -> 🗑️ Auto-Deleting...")
            # ดักจับ Error อื่นๆ ที่อาจทำให้ดึงราคาไม่ได้ ก็สั่งลบทิ้งเช่นกัน
            try:
                supabase.table(TABLE_NAME).delete().eq("ticker", ticker).execute()
                deleted_count += 1
            except: pass
            error_count += 1

    summary = f"📊 **Scan Complete**: Checked {updates_count}, Signals {signal_count}, Auto-Deleted {deleted_count} Invalid Stocks."
    print("-" * 50 + f"\n{summary}")
    if IS_TEST_MODE and signal_count > 0:
        notify(summary)

if __name__ == "__main__":
    run_monitor()
