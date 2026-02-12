import os
import yfinance as yf
from supabase import create_client
import requests

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def run_monitor():
    res = supabase.table("ipo_trades").select("*").neq("status", "sold").execute()
    for item in res.data:
        ticker = item['ticker']
        df = yf.Ticker(ticker).history(period="1mo")
        if df.empty: continue

        current_price = df['Close'].iloc[-1]
        day_high = df['High'].iloc[-1]

        # 1. Auto-Base Discovery (หา High วันแรกถ้ายังไม่มี)
        if not item.get('base_high') or item['base_high'] == 0:
            first_high = df['High'].iloc[0]
            supabase.table("ipo_trades").update({"base_high": first_high}).eq("ticker", ticker).execute()
            notify(f"🎯 **Base Found:** {ticker} ตั้งราคาฐานที่ ${first_high:.2f}")
            continue

        # 2. Check Breakout (Buy Signal)
        if item['status'] == 'watching' and current_price > item['base_high']:
            notify(f"🚀 **BUY! {ticker}** ทะลุ ${item['base_high']:.2f} ไปที่ ${current_price:.2f}")
            supabase.table("ipo_trades").update({
                "status": "bought", "buy_price": current_price, "highest_price": day_high
            }).eq("ticker", ticker).execute()

        # 3. Trailing Stop (Sell Signal)
        elif item['status'] == 'bought':
            highest = max(item['highest_price'] or 0, day_high)
            stop_price = highest * 0.95 # คัดทิ้งที่ 5%
            
            if current_price < stop_price:
                notify(f"⚠️ **SELL! {ticker}** หลุดจุดคัด ${stop_price:.2f} (กำไร/ขาดทุน: {((current_price-item['buy_price'])/item['buy_price'])*100:.2f}%)")
                supabase.table("ipo_trades").update({"status": "sold"}).eq("ticker", ticker).execute()
            elif day_high > (item['highest_price'] or 0):
                supabase.table("ipo_trades").update({"highest_price": day_high}).eq("ticker", ticker).execute()

def send_summary():
    res = supabase.table("ipo_trades").select("*").eq("status", "bought").execute()
    if not res.data: return
    msg = "📊 **Daily Portfolio Summary**\n"
    for i in res.data:
        p = yf.Ticker(i['ticker']).history(period="1d")['Close'].iloc[-1]
        pl = ((p - i['buy_price']) / i['buy_price']) * 100
        msg += f"{'🟢' if pl>=0 else '🔴'} {i['ticker']}: ${p:.2f} ({pl:+.2f}%)\n"
    notify(msg)

if __name__ == "__main__":
    run_monitor()
