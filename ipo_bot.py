import os
import requests
import yfinance as yf
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright

# --- Settings (ดึงจาก GitHub Secrets) ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
FINNHUB_API_KEY = os.getenv("FINNHUB_TOKEN")

def get_open_price(symbol, market="US"):
    """ดึงราคาเปิดและราคาล่าสุด"""
    ticker_sym = symbol if market == "US" else f"{symbol}.BK"
    try:
        ticker = yf.Ticker(ticker_sym)
        df = ticker.history(period="1d")
        if not df.empty:
            open_p = df['Open'].iloc[0]
            current_p = df['Close'].iloc[0]
            diff = ((current_p - open_p) / open_p) * 100
            return round(open_p, 2), round(current_p, 2), round(diff, 2)
    except:
        pass
    return None, None, None

def get_thai_ipo_list():
    """ใช้ Playwright ขูดข้อมูลหุ้นไทยจากเว็บ SET"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("https://www.set.or.th/th/listing/ipo/upcoming-ipo/set", wait_until="networkidle", timeout=60000)
            today_th = datetime.now(pytz.timezone('Asia/Bangkok'))
            thai_year = today_th.year + 543
            today_str = today_th.strftime(f"%d %b {thai_year}") # เช่น 11 ก.พ. 2569
            
            rows = page.locator("tr").all_inner_texts()
            symbols = []
            for row in rows:
                if today_str in row:
                    # ปกติชื่อย่อหุ้นจะอยู่เป็นคำแรกในแถวของตาราง SET
                    symbols.append(row.split()[0])
            browser.close()
            return list(set(symbols))
        except Exception as e:
            print(f"Thai Scrape Error: {e}")
            browser.close()
            return []

def get_us_ipo_list():
    """ดึงรายชื่อหุ้น IPO สหรัฐฯ จาก API"""
    today = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d')
    url = f"https://finnhub.io/api/v1/calendar/ipo?from={today}&to={today}&token={FINNHUB_API_KEY}"
    try:
        res = requests.get(url).json()
        return res.get('ipoCalendar', [])
    except:
        return []

if __name__ == "__main__":
    tz_th = pytz.timezone('Asia/Bangkok')
    now_th = datetime.now(tz_th)
    
    report = f"📊 **รายงานหุ้น IPO ประจำวันที่ {now_th.strftime('%d/%m/%Y')}** 📊\n"
    report += "—"*15 + "\n"

    # --- ส่วนที่ 1: ตลาดหุ้นไทย ---
    report += "🇹🇭 **ตลาดหุ้นไทย (SET/mai):**\n"
    thai_stocks = get_thai_ipo_list()
    if thai_stocks:
        for s in thai_stocks:
            op, cp, diff = get_open_price(s, "TH")
            if op:
                emoji = "🚀" if diff > 0 else "📉" if diff < 0 else "➖"
                report += f"🔹 **{s}** | เปิด: {op} | ล่าสุด: {cp} ({diff}%) {emoji}\n"
            else:
                report += f"🔹 **{s}** | ⏳ รอราคาเปิด (ตลาดอาจยังไม่เปิด/ข้อมูลยังไม่เข้า)\n"
    else:
        report += "➖ วันนี้ไม่มีหุ้น IPO ไทยเข้าใหม่\n"

    report += "\n" + "—"*15 + "\n"

    # --- ส่วนที่ 2: ตลาดหุ้นสหรัฐฯ ---
    report += "🇺🇸 **ตลาดหุ้นสหรัฐฯ (US):**\n"
    us_stocks = get_us_ipo_list()
    if us_stocks:
        for s in us_stocks:
            sym = s['symbol']
            op, cp, diff = get_open_price(sym, "US")
            if op:
                emoji = "🚀" if diff > 0 else "📉" if diff < 0 else "➖"
                report += f"🔹 **{sym}** | เปิด: ${op} | ล่าสุด: ${cp} ({diff}%) {emoji}\n"
            else:
                # กรณี US IPO มักจะเปิดเทรดช่วงดึก
                report += f"🔹 **{sym}** | ⏳ รอราคาเปิด (ระดมทุนที่ ${s.get('price')})\n"
    else:
        report += "➖ วันนี้ไม่มีหุ้น IPO สหรัฐฯ เข้าใหม่\n"

    # ส่งเข้า Discord
    if DISCORD_WEBHOOK_URL:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": report})
