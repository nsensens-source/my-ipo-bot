import os
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from supabase import create_client

# การตั้งค่าเชื่อมต่อผ่าน Environment Variables เพื่อความปลอดภัยตามหลัก Security
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

async def get_us_ipos(page):
    try:
        await page.goto("https://www.nasdaq.com/market-activity/ipos", wait_until="networkidle", timeout=60000)
        tickers = await page.locator(".market-calendar-table__column--symbol").all_inner_texts()
        return [{"ticker": t.strip(), "type": "IPO_US"} for t in tickers if t.strip() and t != "Symbol"]
    except: return []

async def get_thai_ipos(page):
    try:
        await page.goto("https://www.settrade.com/th/ipo", wait_until="networkidle")
        tickers = await page.locator(".symbol").all_inner_texts()
        return [{"ticker": f"{t.strip()}.BK", "type": "IPO_TH"} for t in tickers if t.strip()]
    except: return []

def get_sp500_list():
    try:
        # ดึงรายชื่อหุ้น S&P 500 จาก Wikipedia
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        df = table[0]
        return [{"ticker": t.replace('.', '-').strip(), "type": "SP500"} for t in df['Symbol'].tolist()]
    except: return []

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # รวบรวมข้อมูลทั้งหมด
        all_data = await get_us_ipos(page) + await get_thai_ipos(page) + get_sp500_list()
        
        for item in all_data:
            # ใช้ Upsert เพื่อป้องกันข้อมูลซ้ำและอัปเดตประเภทตลาด
            supabase.table("ipo_trades").upsert({
                "ticker": item['ticker'],
                "market_type": item['type'],
                "status": "watching"
            }, on_conflict="ticker").execute()
            
        await browser.close()
        print(f"✅ Scraper completed: {len(all_data)} tickers synced.")

if __name__ == "__main__":
    asyncio.run(main())
