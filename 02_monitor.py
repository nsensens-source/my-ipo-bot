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
    """ส่งข้อความธรรมดา สำหรับแจ้งเตือนทั่วไป"""
    prefix = "🔭 **[MONITOR]** " if IS_TEST_MODE else "📡 **[SIGNAL]** "
    try:
        requests.post(DISCORD_URL, json={"content": prefix + msg})
    except: pass

def send_signal_embeds(baskets, is_test_mode):
    """ส่งตะกร้าสัญญาณเป็นกล่องสี โดยทำการ Sort ตามราคา (ถูกไปแพง) ก่อนส่ง"""
    embeds = []
    
    # ฟังก์ชันช่วยเรียงลำดับจากราคาน้อยไปมาก และดึงเฉพาะข้อความ (text) ออกมา
    def sort_and_extract(basket_list):
        sorted_list = sorted(basket_list, key=lambda x: x['price'])
        return "\n".join([item['text'] for item in sorted_list])

    # --- 1. กลุ่ม Breakout ---
    if baskets["breakout_high"]:
        embeds.append({
            "title": "🔥 HIGH Breakout (> 3%)",
            "description": sort_and_extract(baskets["breakout_high"]),
            "color": 5763719 # สีเขียวสว่าง
        })
    if baskets["breakout_medium"]:
        embeds.append({
            "title": "⚡ MEDIUM Breakout (1% - 3%)",
            "description": sort_and_extract(baskets["breakout_medium"]),
            "color": 16705372 # สีเหลือง/ส้ม
        })
    if baskets["breakout_low"]:
        embeds.append({
            "title": "🟢 LOW Breakout (< 1%)",
            "description": sort_and_extract(baskets["breakout_low"]),
            "color": 3447003 # สีฟ้า
        })

    # --- 2. กลุ่ม Oversold ---
    if baskets["oversold"]:
        embeds.append({
            "title": "📉 OVERSOLD FOUND (RSI < 30)",
            "description": sort_and_extract(baskets["oversold"]),
            "color": 10181046 # สีม่วง
        })

    # --- 3. กลุ่ม ทำกำไร (TP) และ ตัดขาดทุน (SL) ---
    if baskets["tp"]:
        embeds.append({
            "title": "💰 TP TARGET REACHED (Take Profit)",
            "description": sort_and_extract(baskets["tp"]),
            "color": 3066993 # สีเขียวเข้ม
        })
    if baskets["sl"]:
        embeds.append({
            "title": "❌ SL TRIGGERED (Stop Loss)",
            "description": sort_and_extract(baskets["sl"]),
            "color": 15158332 # สีแดง
        })

    # ถ้ามีข้อมูลในตะกร้าอย่างน้อย 1 ใบ ให้ส่งออกไปที่ Discord
    if embeds:
        prefix = "🔭 **[MONITOR SUMMARY]**" if is_test_mode else "📡 **[SIGNAL SUMMARY]**"
        payload = {
            "content": prefix,
            "embeds": embeds
        }
        try:
            requests.post(DISCORD_URL, json=payload)
        except Exception as e:
            print(f"❌ Failed to send Discord Embed: {e}")

def calculate_rsi(data, window=14):
    """คำนวณ RSI"""
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
    deleted_count = 0 

    # --- 🛒 เตรียมตะกร้าไว้เก็บข้อมูลแบบ Dict {"price": ..., "text": ...} ---
    signal_baskets = {
        "breakout_high": [],
        "breakout_medium": [],
        "breakout_low": [],
        "oversold": [],
        "tp": [],
        "sl": []
    }

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
            
            if hist.empty:
                print("❌ No price data (Delisted or Not Found) -> 🗑️ Auto-Deleting...")
                supabase.table(TABLE_NAME).delete().eq("ticker", ticker).execute()
                error_count += 1
                deleted_count += 1
                continue
            
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
                # DATA CLEANUP
                if float(item.get('buy_price') or 0) > 0:
                    update_payload['buy_price'] = 0
                    update_payload['highest_price'] = 0

                # 1.1 Breakout Strategy
                if any(x in m_type for x in ['LONG', 'BASE', 'MOONSHOT', 'FAVOURITE']):
                    if base_high > 0 and current_price > base_high:
                        
                        increase_pct = ((current_price - base_high) / base_high) * 100
                        diff_price = current_price - base_high # คำนวณส่วนต่างเป็นจำนวนเงิน
                        
                        update_payload['status'] = 'signal_buy'
                        
                        # สร้างข้อความแบบใหม่ มีจำนวนเหรียญ/บาท ต่อท้าย
                        stock_info_text = f"**{ticker}** | Price {current_price:.2f} > Base {base_high:.2f} (+{increase_pct:.2f}%) | + {diff_price:.2f}$"
                        item_data = {"price": current_price, "text": stock_info_text}
                        
                        if increase_pct >= 3.0:
                            signal_baskets["breakout_high"].append(item_data)
                        elif increase_pct >= 1.0:
                            signal_baskets["breakout_medium"].append(item_data)
                        else:
                            signal_baskets["breakout_low"].append(item_data)
                        
                        signal_triggered = True

                # 1.2 Oversold Strategy
                elif 'SHORT' in m_type:
                    if rsi_val < 30:
                        update_payload['status'] = 'signal_buy'
                        item_data = {"price": current_price, "text": f"**{ticker}** | Price {current_price:.2f} | RSI: {rsi_val:.1f}"}
                        signal_baskets["oversold"].append(item_data)
                        signal_triggered = True

            elif status == 'holding':
                buy_price = float(item.get('buy_price') or 0)
                if buy_price > 0:
                    if current_price >= buy_price * (1 + tp_pct):
                        update_payload['status'] = 'signal_sell'
                        
                        profit_pct = ((current_price - buy_price) / buy_price) * 100
                        profit_amt = current_price - buy_price # กำไรเป็นจำนวนเงิน
                        
                        stock_info_text = f"**{ticker}** | Buy {buy_price:.2f} ➔ Sell {current_price:.2f} (💰 +{profit_pct:.2f}% | + {profit_amt:.2f}$)"
                        signal_baskets["tp"].append({"price": current_price, "text": stock_info_text})
                        signal_triggered = True
                        
                    elif current_price <= buy_price * (1 - sl_pct):
                        update_payload['status'] = 'signal_sell'
                        
                        loss_pct = ((buy_price - current_price) / buy_price) * 100
                        loss_amt = buy_price - current_price # ขาดทุนเป็นจำนวนเงิน
                        
                        stock_info_text = f"**{ticker}** | Buy {buy_price:.2f} ➔ Sell {current_price:.2f} (❌ -{loss_pct:.2f}% | - {loss_amt:.2f}$)"
                        signal_baskets["sl"].append({"price": current_price, "text": stock_info_text})
                        signal_triggered = True

            supabase.table(TABLE_NAME).update(update_payload).eq("ticker", ticker).execute()
            
            updates_count += 1
            if signal_triggered: signal_count += 1
            
            print(f"✅ Price: {current_price:.2f} | RSI: {rsi_val:.1f}" + (" [SIGNAL!!]" if signal_triggered else ""))

            time.sleep(0.1)

        except Exception as e:
            print(f"❌ Error analyzing {ticker}: {e} (Skipping...)")
            error_count += 1

    # --- 📤 เมื่อสแกนจบ เทข้อมูลจากตะกร้าส่งเข้า Discord รวดเดียว ---
    send_signal_embeds(signal_baskets, IS_TEST_MODE)

    summary = f"📊 **Scan Complete**: Checked {updates_count}, Signals {signal_count}, Auto-Deleted {deleted_count} Invalid Stocks."
    print("-" * 50 + f"\n{summary}")
    if IS_TEST_MODE and signal_count > 0:
        notify(summary)

if __name__ == "__main__":
    run_monitor()
