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

    print("-" * 50)
    
    for item in stocks:
        ticker = item['ticker']
        status = item.get('status', 'watching')
        m_type = item.get('market_type', 'UNKNOWN')
        
        # ข้ามตัวที่ขายจบไปแล้ว หรือตัวที่ส่งสัญญาณไปแล้วรอ Trader มาเก็บงาน
        if status in ['sold', 'signal_buy', 'signal_sell']: 
            continue

        print(f"🔍 Scanning: {ticker} ({status})", end=" ")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            
            if hist.empty:
                print("❌ No price data")
                error_count += 1
                continue
            
            current_price = float(hist['Close'].iloc[-1])

            # คำนวณ RSI
            full_hist = stock.history(period="1mo")
            rsi_val = calculate_rsi(full_hist['Close'])
            
            # --- เตรียมข้อมูลอัปเดต ---
            update_payload = {
                "last_price": current_price,
                "last_update": datetime.datetime.now().isoformat()
            }
            
            # Update Base High (ถ้ายังไม่มี)
            base_high = float(item.get('base_high') or 0)
            if base_high == 0:
                y_hist = stock.history(period="1y")
                base_high = float(y_hist['High'].max()) if not y_hist.empty else current_price
                update_payload['base_high'] = base_high
                update_payload['highest_price'] = current_price

            # --- 🚦 SIGNAL LOGIC (หัวใจสำคัญ) ---
            is_thai = '.BK' in ticker
            tp_pct = 0.05 if is_thai else 0.10  # TP: TH=5%, US=10%
            sl_pct = 0.03 if is_thai else 0.05  # SL: TH=3%, US=5%
            
            signal_triggered = False

            # Case 1: เฝ้าซื้อ (WATCHING -> SIGNAL_BUY)
            if status == 'watching':
                
                # --- 🧹 ระบบทำความสะอาด: ล้างราคาที่ค้างจากรอบเทรดก่อนหน้า ---
                if float(item.get('buy_price') or 0) > 0:
                    update_payload['buy_price'] = 0
                    update_payload['highest_price'] = 0
                # --------------------------------------------------------

                # 1.1 Breakout Strategy (Long/Base/Moonshot)
                if any(x in m_type for x in ['LONG', 'BASE', 'MOONSHOT', 'FAVOURITE']):
                    if base_high > 0 and current_price > base_high:
                        update_payload['status'] = 'signal_buy'
                        notify(f"🚀 **BREAKOUT FOUND**: {ticker} Price {current_price:.2f} > Base {base_high:.2f}")
                        signal_triggered = True

                # 1.2 Rebound Strategy (Short)
                elif 'SHORT' in m_type:
                    if rsi_val < 30:
                        update_payload['status'] = 'signal_buy'
                        notify(f"📉 **OVERSOLD FOUND**: {ticker} RSI {rsi_val:.1f} < 30")
                        signal_triggered = True

            # Case 2: เฝ้าขาย (HOLDING -> SIGNAL_SELL)
            elif status == 'holding':
                buy_price = float(item.get('buy_price') or 0)
                if buy_price > 0:
                    # 2.1 Take Profit
                    if current_price >= buy_price * (1 + tp_pct):
                        update_payload['status'] = 'signal_sell'
                        notify(f"💰 **TP TARGET REACHED**: {ticker} @ {current_price:.2f} (+{tp_pct*100}%)")
                        signal_triggered = True
                    # 2.2 Stop Loss
                    elif current_price <= buy_price * (1 - sl_pct):
                        update_payload['status'] = 'signal_sell'
                        notify(f"❌ **SL TRIGGERED**: {ticker} @ {current_price:.2f} (-{sl_pct*100}%)")
                        signal_triggered = True

            # บันทึกลง Database
            supabase.table(TABLE_NAME).update(update_payload).eq("ticker", ticker).execute()
            
            updates_count += 1
            if signal_triggered: signal_count += 1
            
            print(f"✅ Price: {current_price:.2f} | RSI: {rsi_val:.1f}" + (" [SIGNAL!!]" if signal_triggered else ""))

            time.sleep(0.1)

        except Exception as e:
            print(f"❌ Error: {e}")
            error_count += 1

    summary = f"📊 **Scan Complete**: Checked {updates_count}, Signals Found {signal_count}, Errors {error_count}"
    print("-" * 50 + f"\n{summary}")
    if IS_TEST_MODE and signal_count > 0:
        notify(summary)

if __name__ == "__main__":
    run_monitor()
