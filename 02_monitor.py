import os
import yfinance as yf
from supabase import create_client
import requests

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def run_monitor():
    # ดึงหุ้นที่ยังไม่ขาย
    res = supabase.table("ipo_trades").select("*").neq("status", "sold").execute()
    
    for item in res.data:
        ticker = item['ticker']
        m_type = item['market_type']
        
        # ดึงข้อมูลย้อนหลัง 1 ปีเพื่อคำนวณค่าเฉลี่ย
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        if len(df) < 20: continue

        curr_p = df['Close'].iloc[-1]
        hi_p = df['High'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        avg_vol = df['Volume'].tail(20).mean() # ค่าเฉลี่ย Volume 20 วันล่าสุด
        
        # คำนวณ Relative Volume (RVOL)
        # $$RVOL = \frac{Volume_{Current}}{Volume_{Average}}$$
        rvol = curr_vol / avg_vol if avg_vol > 0 else 0

        # 1. จัดการราคาฐาน (Base Discovery)
        if not item['base_high'] or item['base_high'] == 0:
            base = df['High'].iloc[0] if m_type.startswith('IPO') else df['High'].max()
            supabase.table("ipo_trades").update({"base_high": base}).eq("ticker", ticker).execute()
            continue

        # 2. เงื่อนไขการซื้อ (Buy Signal + Volume Filter)
        # ซื้อเมื่อ: ราคาทะลุฐาน AND (เป็นหุ้น IPO OR หุ้น SP500 ที่มี RVOL > 2.0)
        price_breakout = curr_p > item['base_high']
        volume_spike = rvol > 2.0 if m_type == "SP500" else True
        
        if item['status'] == 'watching' and price_breakout and volume_spike:
            msg = f"🚀 **BUY SIGNAL! {ticker} ({m_type})**\n"
            msg += f"Price: ${curr_p:.2f} | RVOL: {rvol:.2f}x\n"
            msg += f"Base: ${item['base_high']:.2f}"
            notify(msg)
            supabase.table("ipo_trades").update({
                "status": "bought", "buy_price": curr_p, "highest_price": hi_p
            }).eq("ticker", ticker).execute()

        # 3. Trailing Stop (5% จากจุดสูงสุด)
        elif item['status'] == 'bought':
            new_hi = max(item['highest_price'] or 0, hi_p)
            stop_p = new_hi * 0.95
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
        p = yf.Ticker(i['ticker']).history(period="1d")['Close'].iloc[-1]
        pl = ((p - i['buy_price']) / i['buy_price']) * 100
        msg += f"{'🟢' if pl>=0 else '🔴'} {i['ticker']}: ${p:.2f} ({pl:+.2f}%)\n"
    notify(msg)

if __name__ == "__main__":
    run_monitor()
