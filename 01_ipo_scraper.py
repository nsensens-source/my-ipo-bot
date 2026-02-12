import os
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from supabase import create_client

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
        # ดึงลิสต์ S&P 500 จาก Wikipedia (แหล่งข้อมูลที่เสถียรที่สุดสำหรับบอทฟรี)
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        df = table[0]
        return [{"ticker": t.strip(), "type": "SP500"} for t in df['Symbol'].tolist()]
    except: return []

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # รวบรวมข้อมูลทุกตลาด
        all_data = await get_us_ipos(page) + await get_thai_ipos(page) + get_sp500_list()
        
        for item in all_data:
            check = supabase.table("ipo_trades").select("ticker").eq("ticker", item['ticker']).execute()
            if not check.data:
                supabase.table("ipo_trades").insert({
                    "ticker": item['ticker'],
                    "market_type": item['type'],
                    "status": "watching"
                }).execute()
        await browser.close()
        print("✅ Global Scraper Finished.")

if __name__ == "__main__":
    asyncio.run(main())
