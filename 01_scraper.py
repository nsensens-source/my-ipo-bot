import os
import asyncio
import pandas as pd
from supabase import create_client

# Config
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def get_sp500_data():
    print("📈 Fetching S&P 500 from Database...")
    try:
        # ดึงรายชื่อหุ้น S&P 500 จาก GitHub Dataset (เสถียร 100%)
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        
        # แปลงข้อมูลให้ตรงกับ Format ของเรา
        # เปลี่ยน Symbol เช่น "BRK.B" เป็น "BRK-B" ตามแบบ yfinance
        tickers = []
        for sym in df['Symbol']:
            tickers.append({
                "ticker": sym.replace('.', '-').strip(),
                "market_type": "SP500",
                "status": "watching"
            })
            
        print(f"   ✅ Loaded {len(tickers)} S&P 500 companies.")
        return tickers
    except Exception as e:
        print(f"   ❌ Error fetching S&P 500: {e}")
        return []

def get_manual_ipos():
    print("📝 Loading Watchlist IPOs...")
    # ใส่รายชื่อหุ้นที่เราสนใจตรงนี้ (Manual Feed) เพื่อความชัวร์
    return [
        {"ticker": "RDDT", "market_type": "IPO_US", "status": "watching"},  # Reddit
        {"ticker": "ARM", "market_type": "IPO_US", "status": "watching"},   # Arm Holdings
        {"ticker": "ALAB", "market_type": "IPO_US", "status": "watching"},  # Astera Labs
        {"ticker": "PTT.BK", "market_type": "IPO_TH", "status": "watching"}, # ปตท. (Test SET)
        {"ticker": "CPALL.BK", "market_type": "IPO_TH", "status": "watching"}, # CPALL (Test SET)
        {"ticker": "DELTA.BK", "market_type": "IPO_TH", "status": "watching"}  # DELTA (Test SET)
    ]

def main():
    # 1. รวบรวมข้อมูล
    sp500 = get_sp500_data()
    ipos = get_manual_ipos()
    
    all_data = sp500 + ipos
    
    if not all_data:
        print("⚠️ No data found! Something is wrong with the network.")
        return

    print(f"💾 Syncing {len(all_data)} tickers to Supabase...")
    
    # 2. บันทึกลง Supabase
    count = 0
    for item in all_data:
        try:
            # ใช้ upsert: ถ้ามีอยู่แล้วให้ข้าม/อัปเดต ไม่ error
            supabase.table("ipo_trades").upsert({
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching" 
                # หมายเหตุ: เราไม่ส่ง base_high ไป เพื่อให้ monitor.py เป็นคนคำนวณเอง
            }, on_conflict="ticker").execute()
            count += 1
            
            # Print ทุก 50 ตัวเพื่อไม่ให้รก
            if count % 50 == 0:
                print(f"   ...synced {count} items")
                
        except Exception as e:
            print(f"   ⚠️ Error inserting {item['ticker']}: {e}")

    print(f"✅ Successfully synced {count} tickers to database.")

if __name__ == "__main__":
    main()
