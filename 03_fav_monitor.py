import os
import yfinance as yf
import pandas as pd
import requests
from supabase import create_client

# --- ⚙️ CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_FEVOURITE")

# รับค่า TEST_MODE
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"

# เลือกตารางอัตโนมัติ
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

def notify(msg):
    # เติม [TEST] ข้างหน้าถ้าอยู่ในโหมดทดสอบ
    prefix = "🧪 [TEST] " if IS_TEST_MODE else ""
    requests.post(DISCORD_URL, json={"content": prefix + msg})

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_sniper_bot():
    mode_text = "🧪 TEST MODE (UAT Table)" if IS_TEST_MODE else "🟢 PROD MODE (Real Table)"
    print(f"⭐ Starting Favourite Sniper Bot... [{mode_text}]")
    
    # 1. ดึงข้อมูลจากตารางที่ถูกต้อง (TABLE_NAME)
    try:
        res = supabase.table(TABLE_NAME).select("*").eq("market_type", "FAVOURITE").execute()
        fav_stocks = res.data
    except Exception as e:
        print(f"❌ Error fetching DB ({TABLE_NAME}): {e}")
        return

    if not fav_stocks:
        print(f"⚠️ No Favourite stocks found in '{TABLE_NAME}'.")
        return

    print(f"🎯 Tracking {len(fav_stocks)} favourites...")

    for item in fav_stocks:
        ticker = item['ticker']
        
        # 2. ดึงกราฟย้อนหลัง
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

            # --- 4. SIGNALS ---
            signals = []
            
            if rsi_now < 30:
                signals.append(f"📉 **RSI Oversold ({rsi_now:.2f})** - Buy the Dip!")
            
            if sma50_prev < sma200_prev and sma50_now > sma200_now:
                signals.append(f"🌟 **GOLDEN CROSS** - Bullish Trend Started!")
                
            high_20d = df['High'][-21:-1].max()
            if close_price > high_20d:
                 signals.append(f"🚀 **Breakout 20-Day High** (Price > {high_20d:.2f})")

            # แจ้งเตือน
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
