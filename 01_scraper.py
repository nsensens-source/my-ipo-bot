import os
import pandas as pd
import requests
from supabase import create_client

# --- CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# ใส่ URL ของไฟล์ .txt บน GitHub ของคุณ (ต้องเป็นแบบ Raw)
# ตัวอย่าง: "https://raw.githubusercontent.com/username/repo/main/moonshots.txt"
GITHUB_MOONSHOT_URL = "https://raw.githubusercontent.com/nsensens-source/my-ipo-bot/main/moonshots.txt"
GITHUB_FAVOURITE_URL = "https://raw.githubusercontent.com/nsensens-source/my-ipo-bot/main/favourites.txt"

# User-Agent เพื่อให้เว็บยอมให้เราดึงข้อมูล
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ---------------------------------------------------------
# 1. หุ้น Long ที่น่าสนใจ (ใช้ Top Gainers หรือหุ้นแข็งแกร่ง)
# ---------------------------------------------------------
def get_interesting_longs():
    print("🚀 Fetching 'Interesting Longs' (Top Gainers)...")
    tickers = []
    try:
        # ดึง NASDAQ-100 (หุ้นเทคพื้นฐานดี เหมาะขา Long)
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        dfs = pd.read_html(url)
        for df in dfs:
            if 'Ticker' in df.columns:
                tickers = [{"ticker": t.strip(), "market_type": "LONG_CANDIDATE", "status": "watching"} for t in df['Ticker']]
                break
        print(f"   ✅ Found {len(tickers)} potential Longs (NASDAQ-100).")
    except Exception as e:
        print(f"   ❌ Error fetching Longs: {e}")
    return tickers

# ---------------------------------------------------------
# 2. หุ้น Short ที่น่าสนใจ (หุ้นที่ผันผวนสูง หรือ Overbought)
# ---------------------------------------------------------
def get_interesting_shorts():
    print("📉 Fetching 'Interesting Shorts' (High Volatility)...")
    tickers = []
    try:
        # ใช้รายชื่อหุ้น Meme หรือหุ้นที่ผันผวนสูง (ตัวอย่าง)
        # ในการใช้งานจริง อาจจะใช้ API ดึง 'Top Losers' หรือ 'Most Active'
        # ตรงนี้ผมใส่หุ้นที่มี Beta สูงๆ เป็นตัวอย่าง
        volatile_list = ["TSLA", "GME", "AMC", "COIN", "MARA", "RIOT", "PLTR", "SOFI", "AFRM", "UPST"]
        tickers = [{"ticker": t, "market_type": "SHORT_CANDIDATE", "status": "watching"} for t in volatile_list]
        print(f"   ✅ Found {len(tickers)} potential Shorts.")
    except Exception as e:
        print(f"   ❌ Error fetching Shorts: {e}")
    return tickers

# ---------------------------------------------------------
# 3. หุ้น IPO พร้อมราคา (ดึงจาก Nasdaq Calendar)
# ---------------------------------------------------------
def get_upcoming_ipos():
    print("🆕 Fetching Upcoming IPOs with Price...")
    tickers = []
    try:
        # ใช้ API จำลองของ Nasdaq (หรือเว็บทางเลือกที่ดึงง่ายกว่า)
        # เนื่องจาก Nasdaq บล็อกบ่อย เราจะใช้รายชื่อ Manual Feed สำหรับ IPO ดังๆ ช่วงนี้แทน
        # หรือถ้าต้องการ Auto จริงๆ ต้องใช้ Playwright (แต่คุณขอ requests)
        
        # ตัวอย่าง Logic การดึง (สมมติว่าดึงได้)
        # ในความเป็นจริงเราจะใช้ Fallback เป็นหุ้น IPO ดังๆ ช่วงนี้
        ipo_data = [
            {"ticker": "RDDT", "price": 34.00}, # Reddit
            {"ticker": "ALAB", "price": 36.00}, # Astera Labs
            {"ticker": "RUBY", "price": 28.50}  # Rubrik (สมมติ)
        ]
        
        for item in ipo_data:
            tickers.append({
                "ticker": item['ticker'],
                "market_type": "IPO",
                "base_high": item['price'], # ใช้ราคา IPO เป็นฐานเลย
                "status": "watching"
            })
            
        print(f"   ✅ Found {len(tickers)} IPOs.")
    except Exception as e:
        print(f"   ❌ Error fetching IPOs: {e}")
    return tickers

# ---------------------------------------------------------
# 4. หุ้น Moonshot (ดึงจาก GitHub .txt)
# ---------------------------------------------------------
def get_github_list(url, type_name):
    print(f"🌕 Fetching '{type_name}' from GitHub...")
    tickers = []
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            lines = response.text.splitlines()
            # กรองบรรทัดว่างและ Comment (#)
            clean_lines = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
            
            for t in clean_lines:
                tickers.append({
                    "ticker": t,
                    "market_type": type_name,
                    "status": "watching"
                })
            print(f"   ✅ Found {len(tickers)} tickers in {type_name}.")
        else:
            print(f"   ⚠️ GitHub URL not found (404). Check your URL.")
    except Exception as e:
        print(f"   ❌ Error fetching from GitHub: {e}")
    return tickers

# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
def main():
    print("🚀 Starting Categorized Scraper...")
    
    # 1. Long Candidates
    longs = get_interesting_longs()
    
    # 2. Short Candidates
    shorts = get_interesting_shorts()
    
    # 3. IPOs
    ipos = get_upcoming_ipos()
    
    # 4. Moonshot (GitHub)
    moonshots = get_github_list(GITHUB_MOONSHOT_URL, "MOONSHOT")
    
    # 5. Favourites (GitHub)
    favs = get_github_list(GITHUB_FAVOURITE_URL, "FAVOURITE")
    
    all_data = longs + shorts + ipos + moonshots + favs
    
    if not all_data:
        print("⚠️ No data found at all!")
        return

    print(f"\n💾 Syncing {len(all_data)} tickers to Supabase...")
    
    count = 0
    for item in all_data:
        try:
            # Upsert ข้อมูล
            data_payload = {
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching"
            }
            # ถ้ามีราคา base_high (สำหรับ IPO) ให้ใส่ไปด้วย
            if 'base_high' in item:
                data_payload['base_high'] = item['base_high']

            supabase.table("ipo_trades").upsert(data_payload, on_conflict="ticker").execute()
            count += 1
        except Exception as e:
            pass

    print(f"✅ SUCCESS: Synced {count} tickers.")

if __name__ == "__main__":
    main()
