import os
import pandas as pd
import requests
from supabase import create_client

# --- CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Headers จำเป็นมาก เพื่อไม่ให้ Yahoo/Wiki บล็อก
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ใส่ URL ของไฟล์ GitHub ของคุณที่นี่ (ต้องเป็น Raw Link)
REPO_BASE_URL = "https://raw.githubusercontent.com/YOUR_GITHUB_USER/YOUR_REPO/main"

# ---------------------------------------------------------
# 1. ฐานข้อมูลตลาดหลัก (External Sources Only)
# ---------------------------------------------------------

def get_external_sp500():
    """ดึง S&P 500 จาก GitHub CSV (ไม่ใช่ Hardcode)"""
    print("🇺🇸 Fetching S&P 500 from External CSV...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        return [{"ticker": s.replace('.', '-').strip(), "market_type": "SP500_BASE"} for s in df['Symbol']]
    except: return []

def get_external_nasdaq100():
    """ดึง NASDAQ-100 จาก Wikipedia (Dynamic Parsing)"""
    print("💻 Fetching NASDAQ-100 from Wikipedia...")
    try:
        dfs = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')
        for df in dfs:
            if 'Ticker' in df.columns:
                return [{"ticker": s.strip(), "market_type": "NASDAQ_BASE"} for s in df['Ticker']]
    except: return []

# ---------------------------------------------------------
# 2. นักล่าหุ้นซิ่ง (Dynamic Hunters - Yahoo Finance)
# ---------------------------------------------------------

def get_market_movers():
    """
    ดึงหุ้นซิ่ง (Gainers/Losers/Active) จาก Yahoo Finance
    โดยแยกตาม Region (US และ TH) แบบอัตโนมัติ
    """
    print("🚀 Scanning Market Movers (US & Thai)...")
    tickers = []
    
    # รายการ URL ที่จะไปดูดข้อมูล (ไม่ต้องพิมพ์ชื่อหุ้นเอง)
    targets = [
        # ตลาด US
        ("https://finance.yahoo.com/gainers", "AUTO_LONG_US"),
        ("https://finance.yahoo.com/losers", "AUTO_SHORT_US"),
        ("https://finance.yahoo.com/most-active", "AUTO_ACTIVE_US"),
        # ตลาดไทย (ใช้ region=TH เพื่อดึงหุ้นไทยอัตโนมัติ)
        ("https://finance.yahoo.com/most-active?region=TH", "AUTO_ACTIVE_TH"),
        ("https://finance.yahoo.com/gainers?region=TH", "AUTO_LONG_TH")
    ]
    
    for url, m_type in targets:
        try:
            response = requests.get(url, headers=HEADERS)
            dfs = pd.read_html(response.text)
            df = dfs[0]
            
            # ดึง 10 ตัวแรกของแต่ละหมวด
            for symbol in df['Symbol'].head(10):
                clean_sym = symbol.split('.')[0] # ตัดนามสกุลออกก่อน
                
                # ถ้าเป็นโหมดไทย ต้องเติม .BK กลับเข้าไปเพื่อให้ yfinance อ่านออก
                if "_TH" in m_type and ".BK" not in symbol:
                    final_ticker = f"{clean_sym}.BK"
                elif "_TH" in m_type and ".BK" in symbol:
                    final_ticker = symbol # ถ้ามีอยู่แล้วก็ใช้เลย
                else:
                    final_ticker = clean_sym # ตลาด US ไม่ต้องมีนามสกุล

                tickers.append({"ticker": final_ticker, "market_type": m_type})
        except Exception as e:
            print(f"   ⚠️ Error scraping {url}: {e}")
            pass
        
    return tickers

# ---------------------------------------------------------
# 3. หุ้นที่คุณเลือกเอง (Manual Control via GitHub)
# ---------------------------------------------------------

def get_user_manual_list(filename, type_name):
    """อ่านไฟล์ .txt จาก GitHub ของคุณ"""
    print(f"🌕 Fetching '{filename}' from User GitHub...")
    tickers = []
    try:
        url = f"{REPO_BASE_URL}/{filename}"
        if "YOUR_GITHUB_USER" in url: return [] # กัน User ลืมแก้ URL
        
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            lines = response.text.splitlines()
            # กรองบรรทัดว่างและ Comment
            clean_lines = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
            tickers = [{"ticker": t, "market_type": type_name} for t in clean_lines]
            print(f"   ✅ Found {len(tickers)} items in {filename}")
    except: pass
    return tickers

# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
def main():
    print("🤖 Starting Zero-Hardcode Scraper...")
    
    # 1. External Base (CSV/Wiki)
    base_data = get_external_sp500() + get_external_nasdaq100()
    
    # 2. Auto Hunters (Yahoo Live)
    hunter_data = get_market_movers()
    
    # 3. User Manual (GitHub Files)
    # ใส่ชื่อไฟล์ให้ตรงกับใน GitHub ของคุณ
    manual_data = get_user_manual_list("moonshots.txt", "MOONSHOT") + \
                  get_user_manual_list("favourites.txt", "FAVOURITE")
    
    all_data = base_data + hunter_data + manual_data
    
    if not all_data:
        print("⚠️ No data found! Check network or URLs.")
        return

    print(f"\n💾 Syncing {len(all_data)} tickers to Supabase...")
    
    count = 0
    for item in all_data:
        try:
            # Upsert ลง DB
            supabase.table("ipo_trades").upsert({
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching"
            }, on_conflict="ticker").execute()
            count += 1
            if count % 100 == 0: print(f"   ...synced {count}")
        except: pass

    print(f"✅ SUCCESS: Synced {count} tickers.")
    print(f"   - External Base: {len(base_data)}")
    print(f"   - Auto Hunters: {len(hunter_data)}")
    print(f"   - User Manual: {len(manual_data)}")

if __name__ == "__main__":
    main()
