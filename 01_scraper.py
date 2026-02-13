import os
import pandas as pd
import requests
from supabase import create_client

# --- ⚙️ CONFIG & ENVIRONMENT ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"
    
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"

if IS_TEST_MODE:
    TABLE_NAME = "ipo_trades_uat"
    print(f"\n🧪 TEST MODE: ON -> Using table '{TABLE_NAME}'")
else:
    TABLE_NAME = "ipo_trades"
    print(f"\n🟢 PROD MODE -> Using table '{TABLE_NAME}'")

# URL Repo ของคุณ
REPO_BASE_URL = "https://raw.githubusercontent.com/nsensens-source/my-ipo-bot/main"

# ---------------------------------------------------------
# 1. ฐานข้อมูลตลาดหลัก
# ---------------------------------------------------------
def get_external_sp500():
    print("🇺🇸 Fetching S&P 500 from External CSV...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        return [{"ticker": s.replace('.', '-').strip(), "market_type": "SP500_BASE"} for s in df['Symbol']]
    except: return []

def get_external_nasdaq100():
    print("💻 Fetching NASDAQ-100 from Wikipedia...")
    try:
        dfs = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')
        for df in dfs:
            if 'Ticker' in df.columns:
                return [{"ticker": s.strip(), "market_type": "NASDAQ_BASE"} for s in df['Ticker']]
    except: return []

# ---------------------------------------------------------
# 2. นักล่าหุ้นซิ่ง (แก้ไข Logic ตรงนี้ครับ) 🛠️
# ---------------------------------------------------------
def get_market_movers():
    print("🚀 Scanning Market Movers (Smart Region Detection)...")
    tickers = []
    
    targets = [
        ("https://finance.yahoo.com/gainers", "AUTO_LONG_US"),
        ("https://finance.yahoo.com/losers", "AUTO_SHORT_US"),
        ("https://finance.yahoo.com/most-active", "AUTO_ACTIVE_US"),
        # แม้จะดึงจากหน้าไทย แต่เราจะเช็ครายตัวว่าใช่ไทยจริงไหม
        ("https://finance.yahoo.com/most-active?region=TH", "AUTO_ACTIVE_TH"),
        ("https://finance.yahoo.com/gainers?region=TH", "AUTO_LONG_TH")
    ]
    
    for url, default_m_type in targets:
        try:
            response = requests.get(url, headers=HEADERS)
            dfs = pd.read_html(response.text)
            if not dfs: continue 

            df = dfs[0]
            
            # หา Column Symbol
            symbol_col = None
            possible_names = ['Symbol', 'Ticker', 'ชื่อย่อ', 'สัญลักษณ์']
            for col in df.columns:
                if col in possible_names:
                    symbol_col = col
                    break
            if not symbol_col: symbol_col = df.columns[0]
            
            # ลูปดึงหุ้น 15 ตัวแรก (เผื่อตัวที่ผิดพลาด)
            for raw_symbol in df[symbol_col].head(15):
                symbol_str = str(raw_symbol).strip()
                
                # 🛠️ FIXED LOGIC: แยกแยะสัญชาติหุ้นให้ถูกต้อง
                
                if ".BK" in symbol_str:
                    # ถ้ามี .BK ติดมา -> หุ้นไทยแน่นอน
                    final_ticker = symbol_str
                    final_m_type = "AUTO_ACTIVE_TH" # บังคับเป็นไทย
                    
                elif ".F" in symbol_str:
                    # หุ้น Foreign Board ของไทย -> ข้ามไปก่อน (เล่นยาก)
                    continue
                    
                else:
                    # ถ้าไม่มี .BK (เช่น NVDA, AMZN) -> ถือเป็นหุ้น US ทั้งหมด
                    # แม้จะเจอในหน้าเว็บไทย ก็ต้องปฏิบัติเหมือนหุ้น US
                    final_ticker = symbol_str
                    
                    # ถ้า URL ต้นทางเป็น TH ให้เปลี่ยน Type เป็น US เพราะมันคือหุ้นนอกที่คนไทยนิยม
                    if "_TH" in default_m_type:
                        final_m_type = "AUTO_ACTIVE_US"
                    else:
                        final_m_type = default_m_type

                # กรองพวก Index หรือตัวแปลกๆ ออก
                if "^" in final_ticker or "USD" in final_ticker:
                    continue

                tickers.append({"ticker": final_ticker, "market_type": final_m_type})
                
        except Exception:
            pass
        
    return tickers

# ---------------------------------------------------------
# 3. User Manual (GitHub)
# ---------------------------------------------------------
def get_user_manual_list(filename, type_name):
    print(f"🌕 Fetching '{filename}' from User GitHub...")
    tickers = []
    try:
        url = f"{REPO_BASE_URL}/{filename}"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            lines = response.text.splitlines()
            clean_lines = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
            tickers = [{"ticker": t, "market_type": type_name} for t in clean_lines]
            print(f"   ✅ Found {len(tickers)} items in {filename}")
    except: pass
    return tickers

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    print("🤖 Starting Smart Scraper (Fixed Region Bug)...")
    
    base_data = get_external_sp500() + get_external_nasdaq100()
    hunter_data = get_market_movers()
    manual_data = get_user_manual_list("moonshots.txt", "MOONSHOT") + \
                  get_user_manual_list("favourites.txt", "FAVOURITE")
    
    all_data = base_data + hunter_data + manual_data
    
    if not all_data:
        print("⚠️ No data found!")
        return

    print(f"\n💾 Syncing {len(all_data)} tickers to Supabase...")
    
    count = 0
    for item in all_data:
        try:
            supabase.table(TABLE_NAME).upsert({
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching"
            }, on_conflict="ticker").execute()
            count += 1
            if count % 100 == 0: print(f"   ...synced {count}")
        except: pass

    print(f"✅ SUCCESS: Synced {count} tickers.")

if __name__ == "__main__":
    main()
