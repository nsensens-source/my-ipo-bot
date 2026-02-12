import os
import yfinance as yf
from supabase import create_client
import requests

# Config
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")
CRASH_THRESHOLD = -1.5  # ถ้าตลาดลบเยอะกว่า -1.5% ให้หยุดซื้อ

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def get_market_sentiment():
    """
    เช็คสุขภาพตลาดหลัก (SET และ S&P 500)
    Return: Dictionary บอกสถานะว่า 'ปลอดภัย' หรือไม่
    """
    markets = {
        'TH': '^SET.BK',  # SET Index
        'US': '^GSPC'     # S&P 500
    }
    status = {}
    
    print("🛡️ Checking Market Health (Circuit Breaker)...")
    for region, ticker in markets.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if len(df) < 2:
                status[region] = True # ข้อมูลไม่พอ ให้ถือว่าปกติไปก่อน
                continue

            # คำนวณ % การเปลี่ยนแปลงเทียบกับราคาปิดเมื่อวาน
            prev_close = df['Close'].iloc[-2]
            curr_price = df['Close'].iloc[-1]
            pct_change = ((curr_price - prev_close) / prev_close) * 100
            
            # Logic: ถ้าลบเยอะกว่าเกณฑ์ -> ไม่ปลอดภัย (False)
            is_safe = pct_change > CRASH_THRESHOLD
            status[region] = is_safe
            
            icon = "✅" if is_safe else "⛔"
            print(f"{icon} {region} Market: {pct_change:.2f}% (Threshold: {CRASH_THRESHOLD}%)")
            
            if not is_safe:
                notify(f"⛔ **CIRCUIT BREAKER ACTIVATED! ({region})**\nMarket dropped {pct_change:.2f}%. Buying disabled.")

        except Exception as e:
            print(f"⚠️ Error checking {region} market: {e}")
            status[region] = True # กรณี Error ให้ปล่อยผ่าน (Fail-Open)
            
    return status

def run_monitor():
    # 1. เช็คสภาพตลาดก่อนเริ่มงาน
    market_health = get_market_sentiment()
    
    # 2. ดึงหุ้นที่ยังไม่ขาย
    res = supabase.table("ipo_trades").select("*").neq("status", "sold").execute()
    
    for item in res.data:
        ticker = item['ticker']
        m_type = item['market_type']
        
        # กำหนดโซนตลาดของหุ้นตัวนี้
        region = 'TH' if 'BK' in ticker else 'US'
        
        # ดึงข้อมูลหุ้นรายตัว
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        if len(df) < 20: continue

        curr_p = df['Close'].iloc[-1]
        hi_p = df['High'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        avg_vol = df['Volume'].tail(20).mean()
        
        # Relative Volume (RVOL)
        rvol = curr_vol / avg_vol if avg_vol > 0 else 0

        # --- A. จัดการราคาฐาน (Base Discovery) ---
        if not item['base_high'] or item['base_high'] == 0:
            base = df['High'].iloc[0] if m_type.startswith('IPO') else df['High'].max()
            supabase.table("ipo_trades").update({"base_high": base}).eq("ticker", ticker).execute()
            continue

        # --- B. เงื่อนไขการซื้อ (Buy Logic) ---
        # ต้องผ่าน 3 ด่าน: 
        # 1. ตลาดรวมต้องไม่พัง (Circuit Breaker)
        # 2. ราคาต้อง Breakout
        # 3. Volume ต้องเข้า (เฉพาะ S&P500)
        
        is_market_safe = market_health.get(region, True)
        price_breakout = curr_p > item['base_high']
        volume_spike = rvol > 2.0 if m_type == "SP500" else True
        
        if item['status'] == 'watching':
            if not is_market_safe:
                # ถ้าตลาดแดงเดือด ให้ข้ามการซื้อไปเลย (แต่ยัง Log ไว้ดูได้)
                print(f"Skipping BUY for {ticker} due to Market Risk.")
                continue
                
            if price_breakout and volume_spike:
                msg = f"🚀 **BUY SIGNAL! {ticker} ({m_type})**\n"
                msg += f"Price: ${curr_p:.2f} | RVOL: {rvol:.2f}x\n"
                msg += f"Base: ${item['base_high']:.2f}"
                notify(msg)
                supabase.table("ipo_trades").update({
                    "status": "bought", "buy_price": curr_p, "highest_price": hi_p
                }).eq("ticker", ticker).execute()

        # --- C. เงื่อนไขการขาย (Sell/Trailing Stop) ---
        # *สำคัญ* ถึงตลาดพัง เราก็ต้องทำงานส่วนนี้เพื่อหนีตาย (Cut Loss)
        elif item['status'] == 'bought':
            new_hi = max(item['highest_price'] or 0, hi_p)
            stop_p = new_hi * 0.95 # Trailing Stop 5%
            
            if curr_p < stop_p:
                pl = ((curr_p - item['buy_price']) / item['buy_price']) * 100
                notify(f"⚠️ **SELL! {ticker}**\nExit: ${curr_p:.2f} (P/L: {pl:+.2f}%)")
                supabase.table("ipo_trades").update({"status": "sold"}).eq("ticker", ticker).execute()
            elif hi_p > (item['highest_price'] or 0):
                supabase.table("ipo_trades").update({"highest_price": hi_p}).eq("ticker", ticker).execute()

def send_summary():
    res = supabase.table("ipo_trades").select("*").eq("status", "bought").execute()
    if not res.data: return
    msg = "📊 **Global Portfolio Summary**\n"
    for i in res.data:
        try:
            p = yf.Ticker(i['ticker']).history(period="1d")['Close'].iloc[-1]
            pl = ((p - i['buy_price']) / i['buy_price']) * 100
            msg += f"{'🟢' if pl>=0 else '🔴'} {i['ticker']}: {p:.2f} ({pl:+.2f}%)\n"
        except: pass
    notify(msg)

if __name__ == "__
