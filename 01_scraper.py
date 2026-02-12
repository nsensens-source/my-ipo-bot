import os
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from supabase import create_client

# Config
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

async def get_us_ipos(page):
    print("🇺🇸 Scraping Nasdaq...")
    try:
        # Nasdaq มักจะบล็อก Headless Mode เราจะลองดึง ถ้าไม่ได้จะคืนค่าว่าง
        await page.goto("https://www.nasdaq.com/market-activity/ipos", wait_until="domcontentloaded", timeout=30000)
        # รอให้ตารางโหลด (ถ้าโดนบล็อก Element นี้จะไม่โผล่มา)
        try:
            await page.wait_for_selector(".market-calendar-table__table", timeout=5000)
            tickers = await page.locator(".market-calendar-table__column--symbol").all_inner_texts()
            clean = [{"ticker": t.strip(), "market_type": "IPO_US"} for t in tickers if t.strip() and t != "Symbol"]
            print(f"   ✅ Found {len(clean)} US IPOs")
            return clean
        except:
            print("   ⚠️ Nasdaq Anti-Bot active (Table not found).")
            return []
    except Exception as e:
        print(f"   ❌ US Scrape Error: {e}")
        return []

async def get_thai_ipos(page):
    print("🇹🇭 Scraping Settrade...")
    try:
        await page.goto("https://www.settrade.com/th/ipo", wait_until="domcontentloaded", timeout=30000)
        # ลองดึงจาก Class ทั่วไปของ Settrade
        tickers = await page.locator(".symbol").all_inner_texts()
        clean = [{"ticker": f"{t.strip()}.BK", "market_type": "IPO_TH"} for t in tickers if t.strip()]
        print(f"   ✅ Found {len(clean)} Thai IPOs")
        return clean
    except Exception as e:
        print(f"   ❌ Thai Scrape Error: {e}")
        return []

def get_sp500_list():
    print("📈 Fetching S&P 500 list...")
    try:
        # เปลี่ยนวิธี: ดึงจาก GitHub CSV ที่เสถียรกว่า Wikipedia มาก
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        # เปลี่ยน . เป็น - สำหรับ ticker เช่น BRK.B -> BRK-B
        clean = [{"ticker": t.replace('.', '-').strip(), "market_type": "SP500"} for t in df['Symbol'].tolist()]
        print(f"   ✅ Found {len(clean)} S&P 500 companies")
        return clean
    except Exception as e:
        print(f"   ❌ S&P 500 Error: {e}")
        return []

def inject_fallback_data():
    """ใส่ข้อมูลตัวอย่างถ้าระบบ Scrape ไม่เจออะไรเลย เพื่อให้ Monitor ทำงานได้"""
    print("⚠️ Scraping returned 0 results. Injecting SAMPLE data for testing...")
    return [
        {"ticker": "NVDA", "market_type": "SP500"},  # Nvidia (Test Volatility)
        {"ticker": "AAPL", "market_type": "SP500"},  # Apple (Test Base)
        {"ticker": "RDDT", "market_type": "IPO_US"}, # Reddit (Test IPO)
        {"ticker": "CPALL.BK", "market_type": "IPO_TH"}, # CPALL (Test Thai)
        {"ticker": "PTT.BK", "market_type": "IPO_TH"}    # PTT (Test Thai)
    ]

async def main():
    async with async_playwright() as p:
        # Launch Browser with arguments to avoid detection
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # 1. รวบรวมข้อมูล
        us_data = await get_us_ipos(page)
        thai_data = await get_thai_ipos(page)
        
        await browser.close()

    # ดึง S&P 500 (ไม่ต้องใช้ Browser)
    sp500_data = get_sp500_list()
    
    all_data = us_data + thai_data + sp500_data

    # 2. ถ้าไม่เจออะไรเลย ให้ใส่ข้อมูลจำลอง (Fallback)
    if not all_data:
        all_data = inject_fallback_data()

    # 3. บันทึกลง Supabase
    print(f"💾 Syncing {len(all_data)} tickers to Database...")
    count = 0
    for item in all_data:
        try:
            # ใช้ upsert เพื่อไม่ให้ error ถ้ามี key ซ้ำ
            supabase.table("ipo_trades").upsert({
                "ticker": item['ticker'],
                "market_type": item['market_type'],
                "status": "watching"
            }, on_conflict="ticker").execute()
            count += 1
        except Exception as e:
            print(f"   Error inserting {item['ticker']}: {e}")
            
    print(f"✅ Successfully synced {count} tickers.")

if __name__ == "__main__":
    asyncio.run(main())
