import os
import yfinance as yf
from supabase import create_client
import requests

# 1. Setup Connections
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def run_bot():
    # ดึงหุ้นทั้งหมดที่มีสถานะ 'watching' หรือ 'bought'
    res = supabase.table("ipo_trades").select("*").neq("status", "sold").execute()
    stocks = res.data

    for item in stocks:
        ticker = item['ticker']
        status = item['status']
        base_high = item['base_high']
        
        # ดึงราคาปัจจุบัน
        df = yf.Ticker(ticker).history(period="1d")
        if df.empty: continue
        
        current_price = df['Close'].iloc[-1]
        day_high = df['High'].iloc[-1]

        # LOGIC 1: ถ้ากำลังเฝ้าดู (Watching) -> ตรวจหา Breakout
        if status == 'watching' and current_price > base_high:
            notify(f"🚀 **{ticker} BREAKOUT!** ราคา ${current_price:.2f} ทะลุฐาน ${base_high:.2f} แล้ว!")
            # อัปเดตสถานะเป็นซื้อแล้ว
            supabase.table("ipo_trades").update({
                "status": "bought",
                "buy_price": current_price,
                "highest_price": day_high
            }).eq("ticker", ticker).execute()

        # LOGIC 2: ถ้าซื้อแล้ว (Bought) -> รัน Trailing Stop
        elif status == 'bought':
            highest = max(item['highest_price'] or 0, day_high)
            # คำนวณจุดคัดทิ้ง: $StopPrice = highest \times (1 - 0.05)$
            stop_price = highest * 0.95 

            if current_price < stop_price:
                notify(f"⚠️ **{ticker} HIT STOP LOSS!** ขายที่ ${current_price:.2f} (ทุน ${item['buy_price']:.2f})")
                supabase.table("ipo_trades").update({"status": "sold"}).eq("ticker", ticker).execute()
            elif day_high > item['highest_price']:
                # อัปเดตจุดสูงสุดใหม่เพื่อเลื่อน Stop Loss ขึ้นตาม
                supabase.table("ipo_trades").update({"highest_price": day_high}).eq("ticker", ticker).execute()

if __name__ == "__main__":
    run_bot()
