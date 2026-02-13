import os
import yfinance as yf
import pandas as pd
import requests
from supabase import create_client

# --- CONFIG ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_FEVOURITE")

# เกณฑ์ความแรง (ปรับได้)
PRICE_JUMP_THRESHOLD = 5.0  # ราคาบวกเกิน 5%
VOLUME_SPIKE_THRESHOLD = 2.5 # วอลุ่มเข้า 2.5 เท่าของปกติ

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def run_rocket_radar():
    print("🚀 Starting Moonshot Radar...")
    
    # 1. ดึงหุ้น Moonshot จาก Database
    try:
        res = supabase.table("ipo_trades").select("*").eq("market_type", "MOONSHOT").execute()
        moon_stocks = res.data
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return

    if not moon_stocks:
        print("⚠️ No Moonshot stocks found. (Add them to moonshots.txt in GitHub)")
        return

    print(f"📡 Scanning {len(moon_stocks)} moonshots for activity...")

    for item in moon_stocks:
        ticker = item['ticker']
        
        try:
            # ดึงข้อมูลย้อนหลัง 1 เดือน (เพื่อเทียบ Volume)
            stock = yf.Ticker(ticker)
            df = stock.history(period="1mo")
            
            if len(df) < 5: continue # ข้อมูลน้อยไปข้าม

            # ข้อมูลปัจจุบัน
            last_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            last_vol = df['Volume'].iloc[-1]
            
            # คำนวณค่าเฉลี่ย Volume 20 วัน
            avg_vol = df['Volume'].mean()

            # --- CALCULATE SIGNALS ---
            
            # 1. Price Surge (% Change)
            pct_change = ((last_close - prev_close) / prev_close) * 100
            
            # 2. Volume Spike (Relative Volume)
            # ป้องกันการหารด้วย 0
            rvol = last_vol / avg_vol if avg_vol > 0 else 0
            
            # 3. Bollinger Band Breakout (Upper)
            # (สูตร: Mean + 2*StdDev)
            rolling_mean = df['Close'].rolling(window=20).mean()
            rolling_std = df['Close'].rolling(window=20).std()
            upper_band = rolling_mean.iloc[-1] + (2 * rolling_std.iloc[-1])
            is_breakout = last_close > upper_band

            # --- DECISION LOGIC (Trigger Alert) ---
            
            alerts = []
            
            # เงื่อนไข A: ราคาพุ่งแรง
            if pct_change >= PRICE_JUMP_THRESHOLD:
                alerts.append(f"🔥 **PRICE EXPLOSION**: +{pct_change:.2f}% today!")
                
            # เงื่อนไข B: วอลุ่มเข้าผิดปกติ (เจ้าเข้า)
            if rvol >= VOLUME_SPIKE_THRESHOLD:
                alerts.append(f"🌊 **VOLUME SPIKE**: {rvol:.1f}x average volume!")
                
            # เงื่อนไข C: ทะลุกรอบบน (ไปต่อ)
            if is_breakout:
                alerts.append(f"⚡ **BOLLINGER BREAKOUT**: Price smashed upper band!")

            # ถ้าเจอความผิดปกติแม้แต่อย่างเดียว -> แจ้งเตือนทันที!
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
