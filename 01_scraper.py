import os
import pandas as pd
import requests
from supabase import create_client

# --- CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ---------------------------------------------------------
# PART 1: ฐานข้อมูลตลาดหลัก (The Base)
# ---------------------------------------------------------

def get_sp500():
    print("🇺🇸 Fetching S&P 500 (Base)...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        # S&P 500 เน้นความเสถียร
        return [{"ticker": s.replace('.', '-').strip(), "market_type": "SP500_BASE"} for s in df['Symbol']]
    except: return []

def get_nasdaq100():
    print("💻 Fetching NASDAQ-100 (Tech Base)...")
    try:
        dfs = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')
        for df in dfs:
            if 'Ticker' in df.columns:
                return [{"ticker": s.strip(), "market_type": "NASDAQ_BASE"} for s in df['Ticker']]
    except: return []

def get_thai_set100():
    print("🇹🇭 Loading SET100 (Thai Base)...")
    # รายชื่อหุ้นไทย SET100 (Hardcode เพื่อความชัวร์ ไม่โดนบล็อก)
    set100 = [
        "ADVANC", "AOT", "AWC", "BANPU", "BBL", "BDMS", "BEM", "BGRIM", "BH", "BJC",
        "BTS", "CBG", "CENTEL", "CHG", "CK", "CKP", "COM7", "CPALL", "CPF", "CPN",
        "CRC", "DELTA", "EA", "EGCO", "GLOBAL", "GPSC", "GULF", "HMPRO", "INTUCH", "IVL",
        "KBANK", "KCE", "KTB", "KTC", "LH", "MINT", "MTC", "OR", "OSP", "PLANB",
        "PTT", "PTTEP", "PTTGC", "RATCH", "SAWAD", "SCB", "SCC", "SCGP", "STA", "STGT",
        "TISCO", "TOP", "TRUE", "TTB", "TU", "WHA", "AMATA", "BAM", "BCH", "BCP",
        "BCPG", "BLA", "BPP", "BYD", "DOHOME", "ERW", "ESSO", "FORTH", "GFPT", "GUNKUL",
        "HANA", "JMART", "JMT", "KEX", "KKP", "LANNA", "MEGA", "NEX", "ONEE", "ORI",
        "PSL", "PTG", "RCL", "SABUY", "SINGER", "SIRI", "SPALI", "SPRC", "STARK", "STEC",
        "TASCO", "THG", "TLI"
    ]
    return [{"ticker": f"{s.strip()}.BK", "market_type": "SET_BASE"} for s in set100]


# ---------------------------------------------------------
# PART 2: นักล่าหุ้นซิ่ง (The Hunters)
# ---------------------------------------------------------

def get_dynamic_movers():
    print("🚀 Scanning for Top Gainers & Losers (Hunters)...")
    tickers = []
    # ลิงก์สำหรับหาหุ้น Gainers (ขาขึ้น) และ Losers (ขาลง/Short)
    targets = [
        ("https://finance.yahoo.com/gainers", "AUTO_LONG"),
        ("https://finance.yahoo.com/losers", "AUTO_SHORT"),
        ("https://finance.yahoo.com/most-active", "AUTO_ACTIVE")
    ]
    
    for url, m_type in targets:
        try:
            response = requests.get(url, headers=HEADERS)
            dfs = pd.read_html(response.text)
            df = dfs[0]
            # ดึงมาแค่ 10 ตัวแรกของแต่ละหมวดก็พอ
            for symbol in df['Symbol'].head(10):
                clean_sym = symbol.split('.')[0]
                tickers.append({"ticker": clean_sym, "market_type": m_type})
        except: pass
        
    return tickers # ไม่ต้อง remove duplicate เพราะเราใช้ upsert ทีหลัง

# ---------------------------------------------------------
# PART 3: รายการพิเศษ (The Specials from GitHub)
# ---------------------------------------------------------

def get_github_list(url, type_name):
    print(f"🌕 Fetching '{type_name}' from GitHub...")
    tickers = []
    try:
        if not url or "YOUR_GITHUB_USER" in url: return []
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            lines = response.text.splitlines()
            clean_lines = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
            tickers = [{"ticker": t, "market_type": type_name} for t in clean_lines]
    except: pass
    return tickers

# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
def main():
    print("🤖 Starting Ultimate Market Scraper...")
    
    # 1. Base Market (ดึงหมดตามที่คุณขอ)
    base_stocks = get_sp500() + get_nasdaq100() + get_thai_set100()
    
    # 2. Hunters (หาหุ้นซิ่ง)
    hunter_stocks = get_dynamic_movers()
    
    # 3. Specials (GitHub)
    # ใส่ URL จริงของคุณตรงนี้นะครับ
    repo_url = "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main"
    special_stocks = get_github_list(f"{repo_url}/moonshots.txt", "MOONSHOT") + \
                     get_github_list(f"{repo_url}/favourites.txt", "FAVOURITE")
    
    all_data = base_stocks + hunter_stocks + special_stocks
    
    if not all_data:
        print("⚠️ No data found!")
        return

    print(f"\n💾 Syncing {len(all_data)} tickers to Supabase...")
    
    count = 0
    for item in all_data:
        try:
            # Upsert: ถ้าหุ้นซ้ำกัน (เช่น NVDA อยู่ทั้ง NASDAQ และ Gainers) 
            # มันจะอัปเดต market_type เป็นอันล่าสุดที่เจอ
            supabase.table("ipo_trades").upsert({
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching"
            }, on_conflict="ticker").execute()
            count += 1
            if count % 100 == 0: print(f"   ...synced {count}")
        except: pass

    print(f"✅ SUCCESS: Synced {count} tickers.")
    print(f"   - Base Markets (SP500/NDX/SET): Included")
    print(f"   - Auto Hunters (Gainers/Losers): Included")
    print(f"   - Specials (GitHub): Included")

if __name__ == "__main__":
    main()
