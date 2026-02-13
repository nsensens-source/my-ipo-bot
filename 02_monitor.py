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
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

# Settings
CRASH_THRESHOLD = -1.5 

def notify(msg):
    prefix = "🧪 [TEST] " if IS_TEST_MODE else ""
    requests.post(DISCORD_URL, json={"content": prefix + msg})

def get_market_sentiment():
    if IS_TEST_MODE: return {'TH': True, 'US': True} 
    
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
        except: status[region] = True
    return status

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_monitor():
    print(f"🚀 Starting Dual-Strategy Monitor [{TABLE_NAME}]...")
    market_health = get_market_sentiment()
    
    res = supabase.table(TABLE_NAME).select("*").neq("status", "sold").execute()
    stocks = res.data
    
    print(f"🔍 Scanning {len(stocks)} stocks...")
    updates_count = 0
    
    for item in stocks:
        ticker = item['ticker']
        m_type = item.get('market_type', 'UNKNOWN') # ดูประเภทหุ้น
        region = 'TH' if '.BK' in ticker else 'US'
        
        if not market_health.get(region, True): continue

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            
            if len(hist) < 20: continue # ข้อมูลน้อยเกินข้ามไปก่อน
            
            current_price = hist['Close'].iloc[-1]
            high_52w = hist['High'].max()
            low_52w = hist['Low'].min()
            
            # คำนวณ RSI
            hist['RSI'] = calculate_rsi(hist['Close'])
            rsi_now = hist['RSI'].iloc[-1]
            
            # --- 🧠 STRATEGY SELECTION (แยกสมองตรงนี้) ---
            
            signal_msg = ""
            
            # 🟢 กลยุทธ์ 1: สำหรับหุ้นขาขึ้น (AUTO_LONG, MOONSHOT, FAVOURITE, SP500)
            # เน้นดู Breakout หรือ Momentum
            if "LONG" in m_type or "MOONSHOT" in m_type or "BASE" in m_type or "FAVOURITE" in m_type:
                
                # Logic: ราคาทำ New High หรือ RSI แรง (Bullish)
                base_high = item.get('base_high') or high_52w
                
                if current_price > base_high:
                    signal_msg = f"🚀 **BREAKOUT (Long)**: New High {current_price:.2f} > {base_high:.2f}"
                elif rsi_now > 70:
                    # บางคนชอบ RSI > 70 คือแรง (Super Bullish) บางคนกลัวดอย อันนี้แล้วแต่สูตร
                    pass 

            # 🔴 กลยุทธ์ 2: สำหรับหุ้นขาลง (AUTO_SHORT)
            # เน้นดู Rebound (เด้งทำกำไรสั้นๆ) หรือ Breakdown
            elif "SHORT" in m_type:
                
                # Logic A: Rebound (เล่นเด้ง) - RSI ต่ำจัดๆ
                if rsi_now < 30:
                    signal_msg = f"📉 **REBOUND (Short)**: Oversold RSI {rsi_now:.2f} - Potential Bounce!"
                
                # Logic B: Breakdown (หลุดโลว์ เดิม) - ถ้าคุณเล่น Short Sell จริงๆ
                # if current_price < low_52w:
                #    signal_msg = f"🩸 **BREAKDOWN**: New Low {current_price:.2f}"

            # --- UPDATE & NOTIFY ---
            
            # อัปเดตราคาล่าสุดเสมอ
            update_payload = {
                "last_price": current_price,
                "last_update": datetime.datetime.now().isoformat()
            }
            
            # ถ้ายังไม่มี base_high ให้ตั้งค่า
            if not item.get('base_high'):
                update_payload['base_high'] = high_52w
                update_payload['highest_price'] = current_price

            # อัปเดต DB
            supabase.table(TABLE_NAME).update(update_payload).eq("id", item['id']).execute()
            updates_count += 1
            
            # ถ้าเจอสัญญาณซื้อ/ขาย และสถานะยังแค่ watching อยู่
            if signal_msg and item['status'] == 'watching':
                full_msg = f"⚡ **{m_type} ALERT**: {ticker}\n{signal_msg}\nPrice: {current_price:.2f}"
                notify(full_msg)
                # supabase.table(TABLE_NAME).update({"status": "signal_found"}).eq("id", item['id']).execute()

        except Exception as e:
            continue
            
    print(f"✅ Updated {updates_count} tickers.")

if __name__ == "__main__":
    run_monitor()
