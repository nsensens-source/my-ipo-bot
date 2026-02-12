import os
import pandas as pd
import requests
from supabase import create_client

# --- CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Headers จำเป็นมาก เพื่อไม่ให้ Yahoo มองว่าเป็นบอท
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ---------------------------------------------------------
# 1. สูตรหาหุ้น Short (High Volatility & Losers) - *แก้ใหม่*
# ---------------------------------------------------------
def get_dynamic_shorts():
    print("📉 Scanning for High Volatility Shorts (Yahoo Finance)...")
    tickers = []
    urls = [
        "https://finance.yahoo.com/losers",      # หุ้นร่วงหนัก (Top Losers)
        "https://finance.yahoo.com/most-active"  # หุ้นวอลุ่มเข้า (Most Active)
    ]
    
    for url in urls:
        try:
            # ใช้ pandas อ่านตารางจากหน้าเว็บโดยตรง (สูตรเด็ด)
            response = requests.get(url, headers=HEADERS)
            dfs = pd.read_html(response.text)
            
            # ตารางหุ้นมักจะเป็นตารางแรก (index 0)
            df = dfs[0]
            
            # กรองเอาเฉพาะ Symbol
            for symbol in df['Symbol'].head(15): # เอาแค่ 15 ตัวแรกของแต่ละ list
                clean_sym = symbol.split('.')[0] # ตัด . ออกถ้ามี
                tickers.append({
                    "ticker": clean_sym,
                    "market_type": "SHORT_CANDIDATE", # ติดป้ายไว้ว่าเป็นสาย Short
                    "status": "watching"
                })
        except Exception as e:
            print(f"   ⚠️ Error scraping {url}: {e}")
            
    # ลบตัวซ้ำ
    unique_tickers = list({v['ticker']:v for v in tickers}.values())
    print(f"   ✅ Auto-discovered {len(unique_tickers)} volatile stocks.")
    return unique_tickers

# ---------------------------------------------------------
# 2. สูตรหาหุ้น Long (Top Gainers) - *แก้ใหม่*
# ---------------------------------------------------------
def get_dynamic_longs():
    print("🚀 Scanning for Momentum Longs (Top Gainers)...")
    tickers = []
    try:
        url = "https://finance.yahoo.com/gainers"
        response = requests.get(url, headers=HEADERS)
        dfs = pd.read_html(response.text)
        df = dfs[0]
        
        for symbol in df['Symbol'].head(15):
            clean_sym = symbol.split('.')[0]
            tickers.append({
                "ticker": clean_sym,
                "market_type": "LONG_CANDIDATE",
                "status": "watching"
            })
        print(f"   ✅ Auto-discovered {len(tickers)} momentum stocks.")
    except Exception as e:
        print(f"   ❌ Error fetching Gainers: {e}")
    return tickers

# ---------------------------------------------------------
# 3. S&P 500 (ใช้ CSV เสถียรๆ เหมือนเดิม)
# ---------------------------------------------------------
def get_sp500():
    print("🇺🇸 Fetching S&P 500...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        data = [{"ticker": s.replace('.', '-').strip(), "market_type": "SP500", "status": "watching"} for s in df['Symbol']]
        return data
    except Exception as e:
        print(f"   ❌ S&P 500 Error: {e}")
        return []

# ---------------------------------------------------------
# 4. GitHub Lists (Moonshot & Favourites) - *คงเดิม*
# ---------------------------------------------------------
def get_github_list(url, type_name):
    print(f"🌕 Fetching '{type_name}' from GitHub...")
    tickers = []
    try:
        if not url or "YOUR_GITHUB_USER" in url: # เช็คว่า user ใส่ link หรือยัง
            return []
            
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            lines = response.text.splitlines()
            clean_lines = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
            tickers = [{"ticker": t, "market_type": type_name, "status": "watching"} for t in clean_lines]
            print(f"   ✅ Found {len(tickers)} tickers in {type_name}.")
    except Exception as e:
        print(f"   ❌ Error fetching GitHub list: {e}")
    return tickers

# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
def main():
    print("🤖 Starting Auto-Discovery Scraper...")
    
    # 1. Auto-Discovery (หาเองตามสูตร)
    shorts = get_dynamic_shorts() # แทน volatile_list เดิม
    longs = get_dynamic_longs()
    
    # 2. Market Index
    sp500 = get_sp500()
    
    # 3. Manual Control (จากไฟล์ GitHub)
    # อย่าลืมแก้ URL ตรงนี้เป็นไฟล์ของคุณนะครับ
    repo_url = "https://raw.githubusercontent.com/nsensens-source/my-ipo-bot/main" 
    moonshots = get_github_list(f"{repo_url}/moonshots.txt", "MOONSHOT")
    favs = get_github_list(f"{repo_url}/favourites.txt", "FAVOURITE")
    
    # รวมข้อมูลทั้งหมด
    all_data = shorts + longs + sp500 + moonshots + favs
    
    if not all_data:
        print("⚠️ No data found! Check internet connection.")
        return

    print(f"\n💾 Syncing {len(all_data)} tickers to Supabase...")
    
    count = 0
    for item in all_data:
        try:
            # Upsert ลง Database
            supabase.table("ipo_trades").upsert({
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching"
            }, on_conflict="ticker").execute()
            count += 1
            if count % 100 == 0: print(f"   ...synced {count}")
        except Exception:
            pass

    print(f"\n✅ SUCCESS: Synced {count} tickers.")
    print(f"   - Volatile Shorts: {len(shorts)}")
    print(f"   - Momentum Longs: {len(longs)}")

if __name__ == "__main__":
    main()
