import os
import yfinance as yf
import pandas as pd
import requests
from supabase import create_client

# --- ⚙️ CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

# รับค่า TEST_MODE
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"

# เลือกตารางอัตโนมัติ
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

# เกณฑ์ความแรง
PRICE_JUMP_THRESHOLD = 5.0
VOLUME_SPIKE_THRESHOLD = 2.5

def notify(msg):
    prefix = "🧪 [TEST] " if IS_TEST_MODE else ""
    requests.post(DISCORD_URL, json={"content": prefix + msg})

def run_rocket_radar():
    mode_text = "🧪 TEST MODE (UAT Table)" if IS_TEST_MODE else "🟢 PROD MODE (Real Table)"
    print(f"🚀 Starting Moonshot Radar... [{mode_text}]")
    
    # 1. ดึงหุ้น Moonshot จากตารางที่ถูกต้อง
    try:
        res = supabase.table(TABLE_NAME).select("*").eq("market_type", "MOONSHOT").execute()
        moon_stocks = res.data
    except Exception as e:
        print(f"❌ DB Error ({TABLE_NAME}): {e}")
        return

    if not moon_stocks:
        print(f"⚠️ No Moonshot stocks found in '{TABLE_NAME}'.")
        return

    print(f"📡 Scanning {len(moon_stocks)} moonshots for activity...")

    for item in moon_stocks:
        ticker = item['ticker']
        
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1mo")
            
            if len(df) < 5: continue

            last_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            last_vol = df['Volume'].iloc[-1]
            avg_vol = df['Volume'].mean()

            # --- CALCULATE SIGNALS ---
            pct_change = ((last_close - prev_close) / prev_close) * 100
            rvol = last_vol / avg_vol if avg_vol > 0 else 0
            
            rolling_mean = df['Close'].rolling(window=20).mean()
            rolling_std = df['Close'].rolling(window=20).std()
            upper_band = rolling_mean.iloc[-1] + (2 * rolling_std.iloc[-1])
            is_breakout = last_close > upper_band

            # --- TRIGGER ALERT ---
            alerts = []
            
            if pct_change >= PRICE_JUMP_THRESHOLD:
                alerts.append(f"🔥 **PRICE EXPLOSION**: +{pct_change:.2f}% today!")
                
            if rvol >= VOLUME_SPIKE_THRESHOLD:
                alerts.append(f"🌊 **VOLUME SPIKE**: {rvol:.1f}x average volume!")
                
            if is_breakout:
                alerts.append(f"⚡ **BOLLINGER BREAKOUT**: Price smashed upper band!")

            if alerts:
                msg = f"🚀 **MOONSHOT ALERT: {ticker}** 🚀\n"
                msg += f"Price: ${last_close:.2f}\n"
                msg += "\n".join(alerts)
                msg += f"\n-----------------------"
                notify(msg)
                print(f"✅ Alert sent for {ticker}")
            else:
                print(f"   {ticker}: Quiet ({pct_change:+.2f}%, Vol {rvol:.1f}x)")

        except Exception as e:
            print(f"❌ Error scanning {ticker}: {e}")

if __name__ == "__main__":
    run_rocket_radar()
