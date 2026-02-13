import os
import yfinance as yf
import pandas as pd
import requests
from supabase import create_client

# --- CONFIG ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_sniper_bot():
    print("⭐ Starting Favourite Sniper Bot...")
    
    # 1. ดึงเฉพาะหุ้น "ลูกรัก" (FAVOURITE)
    try:
        res = supabase.table("ipo_trades").select("*").eq("market_type", "FAVOURITE").execute()
        fav_stocks = res.data
    except Exception as e:
        print(f"❌ Error fetching DB: {e}")
        return

    if not fav_stocks:
        print("⚠️ No Favourite stocks found in Database.")
        return

    print(f"🎯 Tracking {len(fav_stocks)} favourites...")

    for item in fav_stocks:
        ticker = item['ticker']
        
        # 2. ดึงกราฟย้อนหลัง 1 ปี (เพื่อคำนวณ SMA 200)
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y")
            
            if len(df) < 200: 
                print(f"   Skip {ticker}: Not enough data.")
                continue

            # 3. คำนวณ Indicators
            close_price = df['Close'].iloc[-1]
            
            # RSI (14)
            df['RSI'] = calculate_rsi(df['Close'])
            rsi_now = df['RSI'].iloc[-1]
            
            # SMA (50, 200)
            df['SMA50'] = df['Close'].rolling(window=50).mean()
            df['SMA200'] = df['Close'].rolling(window=200).mean()
            
            sma50_now = df['SMA50'].iloc[-1]
            sma200_now = df['SMA200'].iloc[-1]
            sma50_prev = df['SMA50'].iloc[-2]
            sma200_prev = df['SMA200'].iloc[-2]

            # --- 4. SIGNALS (สัญญาณเข้าซื้อ) ---
            
            signals = []
            
            # Signal A: RSI Oversold (ของถูก)
            if rsi_now < 30:
                signals.append(f"📉 **RSI Oversold ({rsi_now:.2f})** - Buy the Dip!")
            
            # Signal B: Golden Cross (SMA50 ตัดขึ้น SMA200)
            if sma50_prev < sma200_prev and sma50_now > sma200_now:
                signals.append(f"🌟 **GOLDEN CROSS** - Bullish Trend Started!")
                
            # Signal C: Price Breakout 20 Days High (เบรคไฮเดือน)
            high_20d = df['High'][-21:-1].max() # High ของ 20 วันก่อนหน้า (ไม่รวมวันนี้)
            if close_price > high_20d:
                 signals.append(f"🚀 **Breakout 20-Day High** (Price > {high_20d:.2f})")

            # ถ้าเจอสัญญาณใดสัญญาณหนึ่ง ให้แจ้งเตือนทันที!
            if signals:
                msg = f"⭐ **FAVOURITE ALERT: {ticker}** ⭐\n"
                msg += f"Price: ${close_price:.2f}\n"
                msg += "\n".join(signals)
                msg += f"\n-----------------------"
                notify(msg)
                print(f"✅ Alert sent for {ticker}")
            else:
                print(f"   {ticker}: No signal (RSI={rsi_now:.1f})")

        except Exception as e:
            print(f"❌ Error analyzing {ticker}: {e}")

if __name__ == "__main__":
    run_sniper_bot()
