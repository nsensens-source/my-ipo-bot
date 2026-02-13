import os
import pandas as pd
import requests
from supabase import create_client
from io import StringIO

# --- ⚙️ CONFIG & ENVIRONMENT ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"
    
IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

if IS_TEST_MODE:
    print(f"\n🧪 TEST MODE: ON -> Using table '{TABLE_NAME}'")
else:
    print(f"\n🟢 PROD MODE -> Using table '{TABLE_NAME}'")

REPO_BASE_URL = "https://raw.githubusercontent.com/nsensens-source/my-ipo-bot/main"

# ---------------------------------------------------------
# 1. ฐานข้อมูลตลาดหลัก (เก็บไว้เป็นฐานข้อมูลอ้างอิง)
# ---------------------------------------------------------
def get_external_sp500():
    print("🇺🇸 Fetching S&P 500 (Base)...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        return [{"ticker": s.replace('.', '-').strip(), "market_type": "SP500_BASE"} for s in df['Symbol']]
    except: return []

def get_external_thai_set100():
    print("🇹🇭 Fetching SET100 (Base)...")
    try:
        url = "https://en.wikipedia.org/wiki/SET100_Index"
        response = requests.get(url, headers=HEADERS)
        dfs = pd.read_html(StringIO(response.text))
        tickers = []
        for df in dfs:
            if 'Symbol' in df.columns:
                for s in df['Symbol']:
                    clean_s = str(s).strip()
                    if not clean_s.endswith(".BK"): clean_s += ".BK"
                    tickers.append({"ticker": clean_s, "market_type": "SET_BASE"})
                break
        return tickers
    except: return []

# ---------------------------------------------------------
# 2. นักล่าหุ้นซิ่ง (สูตรใหม่: 50 US / 40 TH) ⚖️
# ---------------------------------------------------------
def get_market_movers():
    print("🚀 Scanning Market Movers (Balanced Strategy)...")
    tickers = []
    
    # กำหนดเป้าหมายและจำนวนที่จะดึง (Limit)
    targets = [
        # --- 🇺🇸 US MARKET (Total 50) ---
        # 1. US Gainers (25 ตัว) -> ขาขึ้น
        ("https://finance.yahoo.com/gainers", "AUTO_LONG_US", 25),
        # 2. US Losers (25 ตัว) -> ขาลง (Short/Rebound)
        ("https://finance.yahoo.com/losers", "AUTO_SHORT_US", 25),
        
        # --- 🇹🇭 THAI MARKET (Total 40) ---
        # 3. TH Gainers (20 ตัว) -> ขาขึ้น
        ("https://finance.yahoo.com/gainers?region=TH", "AUTO_LONG_TH", 20),
        # 4. TH Losers (20 ตัว) -> ขาลง
        ("https://finance.yahoo.com/losers?region=TH", "AUTO_SHORT_TH", 20)
    ]
    
    for url, m_type, limit in targets:
        print(f"   👉 Scraping {m_type} (Limit: {limit})...")
        try:
            response = requests.get(url, headers=HEADERS)
            dfs = pd.read_html(StringIO(response.text))
            if not dfs: continue 

            df = dfs[0]
            
            # หา Column ชื่อหุ้น
            symbol_col = None
            possible_names = ['Symbol', 'Ticker', 'ชื่อย่อ', 'สัญลักษณ์']
            for col in df.columns:
                if col in possible_names:
                    symbol_col = col
                    break
            if not symbol_col: symbol_col = df.columns[0]
            
            # วนลูปตามจำนวน Limit ที่ตั้งไว้ (25 หรือ 20)
            count_found = 0
            for raw_symbol in df[symbol_col]:
                if count_found >= limit: break # ครบจำนวนแล้วหยุด
                
                symbol_str = str(raw_symbol).strip()
                
                # --- LOGIC แยกสัญชาติ ---
                
                # ถ้าเป็นโหมดไทย (URL มี region=TH)
                if "_TH" in m_type:
                    # ต้องมี .BK (ถ้าไม่มีเติมให้)
                    if ".BK" not in symbol_str:
                        final_ticker = f"{symbol_str}.BK"
                    else:
                        final_ticker = symbol_str
                    
                    # กรองหุ้นต่างด้าว (.F) หรือ Warrant (.W) ที่ไม่อยากเล่น
                    if ".F.BK" in final_ticker: continue 
                    
                # ถ้าเป็นโหมด US
                else:
                    final_ticker = symbol_str
                    # ถ้าชื่อมี .BK หลุดมาในโหมด US (เป็นไปได้ยากแต่กันไว้) ให้ข้าม
                    if ".BK" in final_ticker: continue

                # กรองขยะทั่วไป
                if "^" in final_ticker or "USD" in final_ticker: continue

                tickers.append({"ticker": final_ticker, "market_type": m_type})
                count_found += 1
                
        except Exception as e:
            print(f"      ⚠️ Error: {e}")
            pass
        
    return tickers

# ---------------------------------------------------------
# 3. User Manual
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
    print("🤖 Starting Balanced Scraper...")
    
    # 1. Base (เก็บไว้ดูภาพรวม)
    base_data = get_external_sp500() + get_external_thai_set100()
    
    # 2. Hunters (พระเอกของเรา: 90 ตัว)
    hunter_data = get_market_movers()
    
    # 3. Manual
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
    print(f"   - Base Markets: {len(base_data)}")
    print(f"   - Hunters (Active): {len(hunter_data)}")
    print(f"   - User Manual: {len(manual_data)}")

if __name__ == "__main__":
    main()
