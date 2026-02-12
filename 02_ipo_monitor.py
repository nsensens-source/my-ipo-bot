import os
import yfinance as yf
from supabase import create_client
import requests

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def process_stocks():
    res = supabase.table("ipo_trades").select("*").neq("status", "sold").execute()
    for item in res.data:
        ticker = item['ticker']
        m_type = item['market_type']
        df = yf.Ticker(ticker).history(period="1y")
        if df.empty: continue

        curr_p = df['Close'].iloc[-1]
        hi_p = df['High'].iloc[-1]

        # 1. Logic การหาฐาน (Base Discovery)
        if not item['base_high'] or item['base_high'] == 0:
            # ถ้าเป็น IPO ใช้ราคาวันแรก | ถ้าเป็น SP500 ใช้ราคาสูงสุดรอบ 52 สัปดาห์
            base = df['High'].iloc[0] if m_type.startswith('IPO') else df['High'].max()
            supabase.table("ipo_trades").update({"base_high": base}).eq("ticker", ticker).execute()
            notify(f"🎯 **Set Base:** {ticker} ({m_type}) @ {base:.2f}")
            continue

        # 2. Check Buy Signal (Breakout)
        if item['status'] == 'watching' and curr_p > item['base_high']:
            notify(f"🚀 **BUY SIGNAL! {ticker}**\nPrice: {curr_p:.2f} (Base: {item['base_high']:.2f})")
            supabase.table("ipo_trades").update({
                "status": "bought", "buy_price": curr_p, "highest_price": hi_p
            }).eq("ticker", ticker).execute()

        # 3. Trailing Stop Logic (5%)
        # $$StopPrice = HighestPrice \times 0.95$$
        elif item['status'] == 'bought':
            new_hi = max(item['highest_price'] or 0, hi_p)
            stop_p = new_hi * 0.95
            if curr_p < stop_p:
                pl = ((curr_p - item['buy_price']) / item['buy_price']) * 100
                notify(f"⚠️ **SELL! {ticker}**\nExit: {curr_p:.2f} (P/L: {pl:+.2f}%)")
                supabase.table("ipo_trades").update({"status": "sold"}).eq("ticker", ticker).execute()
            elif hi_p > (item['highest_price'] or 0):
                supabase.table("ipo_trades").update({"highest_price": hi_p}).eq("ticker", ticker).execute()

def daily_summary():
    res = supabase.table("ipo_trades").select("*").eq("status", "bought").execute()
    if not res.data: return
    msg = "📊 **Global Portfolio Summary**\n"
    for i in res.data:
        p = yf.Ticker(i['ticker']).history(period="1d")['Close'].iloc[-1]
        pl = ((p - i['buy_price']) / i['buy_price']) * 100
        msg += f"{'🟢' if pl>=0 else '🔴'} {i['ticker']}: {p:.2f} ({pl:+.2f}%)\n"
    notify(msg)

if __name__ == "__main__":
    process_stocks()
