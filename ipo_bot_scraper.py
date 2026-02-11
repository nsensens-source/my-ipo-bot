import os
import asyncio
from playwright.async_api import async_playwright
from supabase import create_client

# 1. เชื่อมต่อกับ Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

async def scrape_nasdaq_ipo():
    async with async_playwright() as p:
        # เปิด Browser แบบ Headless (ไม่แสดงหน้าจอ)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("🌐 กำลังเปิดหน้า Nasdaq IPO Calendar...")
        try:
            # ไปที่หน้า IPO Calendar ของ Nasdaq
            await page.goto("https://www.nasdaq.com/market-activity/ipos", wait_until="networkidle", timeout=60000)
            
            # รอให้ตารางข้อมูลโหลดเสร็จ
            await page.wait_for_selector(".market-calendar-table__table")

            # ดึงข้อมูล Ticker จากตาราง
            # หมายเหตุ: Selector อาจมีการเปลี่ยนแปลงตามโครงสร้างเว็บ Nasdaq
            tickers = await page.locator(".market-calendar-table__column--symbol").all_inner_texts()
            
            # กรองค่าว่างหรือ Header ออก
            clean_tickers = [t.strip() for t in tickers if t.strip() and t != "Symbol"]
            
            print(f"✅ พบหุ้น IPO ทั้งหมด {len(clean_tickers)} ตัว: {clean_tickers}")
            return clean_tickers

        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการ Scrape: {e}")
            return []
        finally:
            await browser.close()

def update_database(tickers):
    for ticker in tickers:
        # เช็คว่ามีหุ้นนี้ใน Database หรือยัง เพื่อไม่ให้ข้อมูลซ้ำ
        check = supabase.table("ipo_trades").select("ticker").eq("ticker", ticker).execute()
        
        if not check.data:
            # เพิ่มหุ้นใหม่เข้าไปในสถานะ 'watching'
            # เราจะตั้งค่า base_high เป็น 0 ไว้ก่อนเพื่อให้คุณไปกรอกเอง หรือบอทตัวที่สองช่วยหาให้
            new_data = {
                "ticker": ticker,
                "status": "watching",
                "base_high": 0,  
                "highest_price": 0,
                "buy_price": 0
            }
            supabase.table("ipo_trades").insert(new_data).execute()
            print(f"🆕 เพิ่ม {ticker} เข้า Watchlist เรียบร้อย")
        else:
            print(f"➖ {ticker} มีอยู่ในระบบแล้ว")

async def main():
    found_tickers = await scrape_nasdaq_ipo()
    if found_tickers:
        update_database(found_tickers)

if __name__ == "__main__":
    asyncio.run(main())
