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
    prefix = "🔭 **[MONITOR]** " if IS_TEST_MODE else "📡 **[SIGNAL]** "
    try:
        requests.post(DISCORD_URL, json={"content": prefix + msg})
    except: pass

def send_signal_embeds(baskets, is_test_mode):
    embeds = []
    
    def chunk_list(lst, chunk_size):
        return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

    def add_embeds(basket_list, title, color):
        if not basket_list: return
        sorted_list = sorted(basket_list, key=lambda x: x['price'])
        text_list = [item['text'] for item in sorted_list]
        
        # 🛠️ แก้ไข 1: หั่นข้อมูลเหลือแค่ 20 บรรทัดต่อ 1 กล่อง ป้องกันกล่องบวมเกินไป
        for chunk in chunk_list(text_list, 20):
            embeds.append({
                "title": title,
                "description": "\n".join(chunk),
                "color": color
            })

    add_embeds(baskets["breakout_high"], "🔥 HIGH Breakout (> 3%)", 5763719)
    add_embeds(baskets["breakout_medium"], "⚡ MEDIUM Breakout (1% - 3%)", 16705372)
    add_embeds(baskets["breakout_low"], "🟢 LOW Breakout (< 1%)", 3447003)
    
    add_embeds(baskets["continuing_up"], "🚀🔥 CONTINUING / REBOUND (นิวไฮ หรือ ฟื้นตัวแรง)", 16738740) 
    add_embeds(baskets["momentum"], "🚀 STRONG MOMENTUM (Daily > +4%)", 15277667)
    add_embeds(baskets["oversold"], "📉 OVERSOLD FOUND (RSI < 30)", 10181046)
    add_embeds(baskets["tp"], "💰 TP TARGET REACHED (Take Profit)", 3066993)
    add_embeds(baskets["sl"], "❌ SL TRIGGERED (Stop Loss)", 15158332)

    # 🛠️ แก้ไข 2: ทยอยส่งทีละ 3 กล่อง ป้องกันข้อความรวมเกิน 6,000 ตัวอักษรของ Discord
    for chunked_embeds in chunk_list(embeds, 3):
        prefix = "🔭 **[MONITOR SUMMARY]**" if is_test_mode else "📡 **[SIGNAL SUMMARY]**"
        payload = {
            "content": prefix,
            "embeds": chunked_embeds
        }
        try:
            res = requests.post(DISCORD_URL, json=payload)
            if res.status_code >= 400:
                print(f"❌ Discord API Error: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Failed to send Discord Embed: {e}")
        
        # หยุดพัก 1.5 วินาที เพื่อให้ Discord ไม่มองว่าเรากำลังสแปมเซิร์ฟเวอร์
        time.sleep(1.5)

def calculate_rsi(data, window=14):
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

    signal_baskets = {
        "breakout_high": [],
        "breakout_medium": [],
        "breakout_low": [],
        "continuing_up": [], 
        "momentum": [],
        "oversold": [],
        "tp": [],
        "sl": []
    }

    print("-" * 50)
    
    for item in stocks:
        ticker = item['ticker']
        status = item.get('status', 'watching')
        m_type = item.get('market_type', 'UNKNOWN')
        
        if status in ['sold', 'signal_sell']: 
            continue

        print(f"🔍 Scanning: {ticker} ({status})", end=" ")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            
            if hist.empty:
                print("❌ No price data (Delisted or Not Found) -> 🗑️ Auto-Deleting...")
                supabase.table(TABLE_NAME).delete().eq("ticker", ticker).execute()
                error_count += 1
                deleted_count += 1
                continue
            
            current_price = float(hist['Close'].iloc[-1])
            rsi_val = calculate_rsi(hist['Close'])
            
            daily_pct = 0.0
            diff_daily = 0.0
            if len(hist) >= 2:
                prev_close = float(hist['Close'].iloc[-2])
                daily_pct = ((current_price - prev_close) / prev_close) * 100
                diff_daily = current_price - prev_close
            
            if len(hist) > 5:
                base_high = float(hist['High'].iloc[:-5].max())
            elif len(hist) > 1:
                base_high = float(hist['High'].iloc[:-1].max())
            else:
                base_high = float(hist['High'].max())
            
            highest_price_db = float(item.get('highest_price') or 0)
            last_price_db = float(item.get('last_price') or current_price)
            
            update_payload = {
                "last_price": current_price,
                "base_high": base_high,
                "highest_price": max(current_price, highest_price_db),
                "last_update": datetime.datetime.now().isoformat()
            }

            is_thai = '.BK' in ticker
            tp_pct = 0.05 if is_thai else 0.10  
            sl_pct = 0.03 if is_thai else 0.05  
            
            signal_triggered = False

            if status == 'watching':
                if float(item.get('buy_price') or 0) > 0:
                    update_payload['buy_price'] = 0
                    update_payload['highest_price'] = 0

                if any(x in m_type for x in ['LONG', 'BASE', 'MOONSHOT', 'FAVOURITE']):
                    is_breakout = False
                    
                    if base_high > 0 and current_price > base_high:
                        is_breakout = True
                        increase_pct = ((current_price - base_high) / base_high) * 100
                        diff_price = current_price - base_high
                        
                        update_payload['status'] = 'signal_buy'
                        stock_info_text = f"**{ticker}** | Price {current_price:.2f} > Base {base_high:.2f} (+{increase_pct:.2f}%) | + {diff_price:.2f}$"
                        item_data = {"price": current_price, "text": stock_info_text}
                        
                        if increase_pct >= 3.0:
                            signal_baskets["breakout_high"].append(item_data)
                        elif increase_pct >= 1.0:
                            signal_baskets["breakout_medium"].append(item_data)
                        else:
                            signal_baskets["breakout_low"].append(item_data)
                        
                        signal_triggered = True

                    if not is_breakout and daily_pct >= 4.0:
                        update_payload['status'] = 'signal_buy'
                        stock_info_text = f"**{ticker}** | Price {current_price:.2f} (🚀 Today +{daily_pct:.2f}%) | + {diff_daily:.2f}$"
                        item_data = {"price": current_price, "text": stock_info_text}
                        signal_baskets["momentum"].append(item_data)
                        signal_triggered = True

                elif 'SHORT' in m_type:
                    if rsi_val < 30:
                        update_payload['status'] = 'signal_buy'
                        item_data = {"price": current_price, "text": f"**{ticker}** | Price {current_price:.2f} | RSI: {rsi_val:.1f}"}
                        signal_baskets["oversold"].append(item_data)
                        signal_triggered = True

            elif status == 'signal_buy':
                is_new_high = highest_price_db > 0 and current_price >= (highest_price_db * 1.03)
                is_strong_rebound = last_price_db > 0 and current_price >= (last_price_db * 1.05)
                
                if is_new_high or is_strong_rebound:
                    trigger_reason = "🚀 ทำนิวไฮใหม่!" if is_new_high else "🔥 ฟื้นตัวเด้งแรง!"
                    total_increase_pct = ((current_price - base_high) / base_high) * 100
                    diff_from_base = current_price - base_high
                    
                    stock_info_text = f"**{ticker}** | Price {current_price:.2f} ({trigger_reason}) | ห่างจากฐาน +{total_increase_pct:.2f}% | + {diff_from_base:.2f}$"
                    
                    signal_baskets["continuing_up"].append({"price": current_price, "text": stock_info_text})
                    signal_triggered = True

            elif status == 'holding':
                buy_price = float(item.get('buy_price') or 0)
                if buy_price > 0:
                    if current_price >= buy_price * (1 + tp_pct):
                        update_payload['status'] = 'signal_sell'
                        
                        profit_pct = ((current_price - buy_price) / buy_price) * 100
                        profit_amt = current_price - buy_price
                        
                        stock_info_text = f"**{ticker}** | Buy {buy_price:.2f} ➔ Sell {current_price:.2f} (💰 +{profit_pct:.2f}% | + {profit_amt:.2f}$)"
                        signal_baskets["tp"].append({"price": current_price, "text": stock_info_text})
                        signal_triggered = True
                        
                    elif current_price <= buy_price * (1 - sl_pct):
                        update_payload['status'] = 'signal_sell'
                        
                        loss_pct = ((buy_price - current_price) / buy_price) * 100
                        loss_amt = buy_price - current_price
                        
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

    send_signal_embeds(signal_baskets, IS_TEST_MODE)

    summary = f"📊 **Scan Complete**: Checked {updates_count}, Signals {signal_count}, Auto-Deleted {deleted_count} Invalid Stocks."
    print("-" * 50 + f"\n{summary}")
    if IS_TEST_MODE and signal_count > 0:
        notify(summary)

if __name__ == "__main__":
    run_monitor()
