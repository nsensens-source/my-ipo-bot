import os
import yfinance as yf
from supabase import create_client
import requests


# --- ⚙️ CONFIG & ENVIRONMENT ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")
# รับค่า TEST_MODE (On/Off)
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"

# เลือกตารางอัตโนมัติ
if IS_TEST_MODE:
    TABLE_NAME = "ipo_trades_uat"
    print(f"\n🧪 TEST MODE: ON -> Using table '{TABLE_NAME}'")
else:
    TABLE_NAME = "ipo_trades"
    print(f"\n🟢 PROD MODE -> Using table '{TABLE_NAME}'")

# -------------------------------

# รับค่าจาก Secrets (ถ้าไม่ตั้งค่ามา จะถือว่าเป็น 'Off' โดยอัตโนมัติ)
# แปลงเป็นตัวพิมพ์เล็กเพื่อให้ 'On', 'ON', 'on' ใช้ได้หมด
TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower()

# Setting
STOP_LOSS_IPO = 0.08
STOP_LOSS_SP500 = 0.04
CRASH_THRESHOLD = -1.5 

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def get_market_sentiment():
    """เช็คสุขภาพตลาด (Circuit Breaker)"""
    
    # --- 🧪 TEST MODE LOGIC ---
    # ถ้า TEST_MODE เป็น 'on' ให้ข้ามการเช็คตลาดทั้งหมด
    if TEST_MODE == "on":
        print("\n🧪 =========================================")
        print("🧪 TEST MODE: ACTIVATED (On)")
        print("🧪 Bypassing Market Health & Time Checks...")
        print("🧪 =========================================\n")
        # ส่งค่ากลับไปว่า ตลาดปกติ 100% (Green Light)
        return {'TH': True, 'US': True} 
    # ---------------------------

    # ... (Logic ปกติสำหรับการเช็คตลาด) ...
    print("🛡️ Checking Market Health (Normal Mode)...")
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
            
            is_safe = change > CRASH_THRESHOLD
            status[region] = is_safe
            
            if not is_safe:
                notify(f"⛔ **CIRCUIT BREAKER ({region})**\nMarket dropped {change:.2f}%. Buying disabled.")
        except:
            status[region] = True
            
    return status

def run_monitor():
    # 1. เช็คตลาด
    market_health = get_market_sentiment()
    
    # 2. ดึงหุ้นในพอร์ต
    res = supabase.table(TABLE_NAME).select("*").neq("status", "sold").execute()
    
    for item in res.data:
        ticker = item['ticker']
        m_type = item['market_type']
        
        # ระบุโซนตลาด
        region = 'TH' if 'BK' in ticker else 'US'
        
        # ดึงข้อมูลกราฟ
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        if len(df) < 20: continue

        curr_p = df['Close'].iloc[-1]
        hi_p = df['High'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        avg_vol = df['Volume'].tail(20).mean()
        rvol = curr_vol / avg_vol if avg_vol > 0 else 0

        # --- A. ตั้งราคาฐาน (Base) ---
        if not item['base_high'] or item['base_high'] == 0:
            # IPO ใช้ High วันแรก | SP500 ใช้ High 52 สัปดาห์
            base = df['High'].iloc[0] if 'IPO' in m_type else df['High'].max()
            supabase.table(TABLE_NAME).update({"base_high": base}).eq("ticker", ticker).execute()
            continue

        # --- B. สัญญาณซื้อ (Buy Logic) ---
        is_safe = market_health.get(region, True)
        breakout = curr_p > item['base_high']
        vol_spike = rvol > 2.0 if m_type == "SP500" else True # SP500 ต้องมี Volume เข้า
        
        if item['status'] == 'watching':
            if not is_safe:
                print(f"Skipping BUY {ticker}: Market Risk")
                continue
                
            if breakout and vol_spike:
                msg = f"🚀 **BUY SIGNAL! {ticker} ({m_type})**\nPrice: {curr_p:.2f} | Base: {item['base_high']:.2f}"
                notify(msg)
                supabase.table(TABLE_NAME).update({
                    "status": "bought", "buy_price": curr_p, "highest_price": hi_p
                }).eq("ticker", ticker).execute()

        # --- C. สัญญาณขาย (Dynamic Trailing Stop) ---
        elif item['status'] == 'bought':
            # เลือก % Stop Loss ตามประเภทหุ้น
            stop_pct = STOP_LOSS_IPO if 'IPO' in m_type else STOP_LOSS_SP500
            
            # คำนวณจุดหนีตาย
            highest = max(item['highest_price'] or 0, hi_p)
            stop_price = highest * (1 - stop_pct)
            
            if curr_p < stop_price:
                pl = ((curr_p - item['buy_price']) / item['buy_price']) * 100
                notify(f"⚠️ **SELL! {ticker}**\nExit: {curr_p:.2f} (P/L: {pl:+.2f}%)")
                supabase.table(TABLE_NAME).update({"status": "sold"}).eq("ticker", ticker).execute()
                
            elif hi_p > (item['highest_price'] or 0):
                # New High -> เลื่อนจุด Stop ตามขึ้นไป
                supabase.table(TABLE_NAME).update({"highest_price": hi_p}).eq("ticker", ticker).execute()

def daily_summary():
    """สรุปกำไรรายวัน (รันเฉพาะตอนจบวัน)"""
    res = supabase.table(TABLE_NAME).select("*").eq("status", "bought").execute()
    if not res.data: return
    msg = "📊 **Portfolio Snapshot**\n"
    for i in res.data:
        try:
            p = yf.Ticker(i['ticker']).history(period="1d")['Close'].iloc[-1]
            pl = ((p - i['buy_price']) / i['buy_price']) * 100
            emoji = "🟢" if pl > 0 else "🔴"
            msg += f"{emoji} {i['ticker']}: {pl:+.2f}%\n"
        except: pass
    notify(msg)

if __name__ == "__main__":
    run_monitor()
