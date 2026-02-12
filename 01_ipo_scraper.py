import os
import asyncio
from playwright.async_api import async_playwright
from supabase import create_client

# Config จาก GitHub Secrets
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

async def scrape_nasdaq_ipo():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        
        print("🌐 Scraping Nasdaq IPO Calendar...")
        try:
            await page.goto("https://www.nasdaq.com/market-activity/ipos", wait_until="networkidle", timeout=60000)
            await page.wait_for_selector(".market-calendar-table__table")
            tickers = await page.locator(".market-calendar-table__column--symbol").all_inner_texts()
            clean_tickers = [t.strip() for t in tickers if t.strip() and t != "Symbol"]
            return clean_tickers
        except Exception as e:
            print(f"❌ Scrape Error: {e}")
            return []
        finally:
            await browser.close()

def update_db(tickers):
    for ticker in tickers:
        # ป้องกันข้อมูลซ้ำด้วยการเช็คก่อน insert
        check = supabase.table("ipo_trades").select("ticker").eq("ticker", ticker).execute()
        if not check.data:
            supabase.table("ipo_trades").insert({
                "ticker": ticker,
                "status": "watching",
                "base_high": 0, # รอไฟล์ 02 มาหาค่าให้
                "highest_price": 0,
                "buy_price": 0
            }).execute()
            print(f"✅ Added new ticker: {ticker}")

if __name__ == "__main__":
    found = asyncio.run(scrape_nasdaq_ipo())
    if found:
        update_db(found)
