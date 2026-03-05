import os
import pandas as pd
import requests
import yfinance as yf  # เพิ่ม yfinance สำหรับดึงราคาหุ้นไทย
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
# 1. ฐานข้อมูลตลาดหลัก
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
# 2. นักล่าหุ้นซิ่ง US (กวาดจากเว็บ)
# ---------------------------------------------------------
def get_us_market_movers():
    print("🚀 Scanning US Market Movers...")
    tickers = []
    targets = [
        ("https://finance.yahoo.com/gainers?count=100", "AUTO_LONG_US", 100),
        ("https://finance.yahoo.com/losers?count=100", "AUTO_SHORT_US", 100)
    ]
    for url, m_type, limit in targets:
        print(f"   👉 Scraping {m_type}...")
        try:
            response = requests.get(url, headers=HEADERS)
            dfs = pd.read_html(StringIO(response.text))
            if not dfs: continue 

            df = dfs[0]
            symbol_col = next((col for col in df.columns if col in ['Symbol', 'Ticker', 'ชื่อย่อ']), df.columns[0])
            
            count = 0
            for raw_symbol in df[symbol_col]:
                if count >= limit: break
                final_ticker = str(raw_symbol).strip()
                if ".BK" in final_ticker or "^" in final_ticker or "USD" in final_ticker: continue
                tickers.append({"ticker": final_ticker, "market_type": m_type})
                count += 1
        except Exception as e:
            print(f"      ⚠️ Error US: {e}")
    return tickers

# ---------------------------------------------------------
# 3. นักล่าหุ้นซิ่ง TH (คำนวณเองจาก SET100 แบบแม่นยำ) ⚖️
# ---------------------------------------------------------
def get_thai_market_movers(limit=20):
    print("🇹🇭 Scanning Thai Market Movers (Self-Calculated from SET100)...")
    tickers_data = []
    try:
        # ใช้รายชื่อจาก SET100 ที่เรามี
        set100_list = [item['ticker'] for item in get_external_thai_set100()]
        if not set100_list: return []

        print(f"   👉 Downloading data for {len(set100_list)} Thai stocks...")
        # โหลดราคาล่าสุดรวดเดียวเพื่อความไว
        data = yf.download(set100_list, period="5d", progress=False)
        
        if 'Close' in data:
            close_data = data['Close']
            for ticker in set100_list:
                if ticker in close_data.columns:
                    col = close_data[ticker].dropna()
                    if len(col) >= 2:
                        prev_price = float(col.iloc[-2])
                        curr_price = float(col.iloc[-1])
                        if prev_price > 0:
                            pct = ((curr_price - prev_price) / prev_price) * 100
                            tickers_data.append({"ticker": ticker, "pct_change": pct})
                            
        # จัดเรียงหาตัวท็อป
        tickers_data.sort(key=lambda x: x['pct_change'], reverse=True)
        results = []
        
        # 20 อันดับแรก (บวกเยอะสุด) -> AUTO_LONG_TH
        for item in tickers_data[:limit]:
            results.append({"ticker": item["ticker"], "market_type": "AUTO_LONG_TH"})
            
        # 20 อันดับสุดท้าย (ลบเยอะสุด) -> AUTO_SHORT_TH
        for item in tickers_data[-limit:]:
            results.append({"ticker": item["ticker"], "market_type": "AUTO_SHORT_TH"})
            
        print(f"   ✅ Found {limit} Thai Gainers and {limit} Thai Losers.")
        return results
    except Exception as e:
        print(f"      ⚠️ Error Thai Movers: {e}")
        return []

# ---------------------------------------------------------
# 4. User Manual
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
# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    print("🤖 Starting Balanced Scraper...")
    
    base_data = get_external_sp500() + get_external_thai_set100()
    hunter_data = get_us_market_movers() + get_thai_market_movers(limit=20)
    manual_data = get_user_manual_list("moonshots.txt", "MOONSHOT") + \
                  get_user_manual_list("favourites.txt", "FAVOURITE")
    
    all_data = base_data + hunter_data + manual_data
    
    # --- 🛡️ ระบบกรองหุ้นซ้ำ (Deduplication) ---
    unique_data = {}
    for item in all_data:
        # ถ้ารายชื่อซ้ำ มันจะถูกเขียนทับด้วยข้อมูลล่าสุดเสมอ 
        # (เช่น ถ้าเจอใน SET100 แล้วมาเจอใน FAVOURITE อีก จะนับเป็น FAVOURITE)
        unique_data[item['ticker']] = item
    
    # แปลงกลับเป็น List เพื่อเตรียมนำไปใช้งาน
    final_clean_data = list(unique_data.values())
    # -----------------------------------------

    if not final_clean_data:
        print("⚠️ No data found!")
        return

    print(f"\n💾 Syncing {len(final_clean_data)} unique tickers to Supabase...")
    
    count = 0
    for item in final_clean_data:
        try:
            supabase.table(TABLE_NAME).upsert({
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching"
            }, on_conflict="ticker").execute()
            count += 1
            if count % 100 == 0: print(f"   ...synced {count}")
        except: pass

    print(f"✅ SUCCESS: Synced {count} unique tickers.")

if __name__ == "__main__":
    main()
