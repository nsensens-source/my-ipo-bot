import os
import requests
import yfinance as yf
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright

# ตั้งค่า Environment
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
FINNHUB_API_KEY = os.getenv("FINNHUB_TOKEN")

def get_open_price(symbol, market="US"):
    ticker_sym = symbol if market == "US" else f"{symbol}.BK"
    try:
        ticker = yf.Ticker(ticker_sym)
        # ดึงข้อมูลย้อนหลัง 1 วัน เพื่อหาค่า Open
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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("https://www.set.or.th/th/listing/ipo/upcoming-ipo/set", wait_until="networkidle")
            # ดึงเฉพาะชื่อหุ้นที่มีสถานะเริ่มซื้อขายวันนี้
            today_thai = datetime.now(pytz.timezone('Asia/Bangkok')).year + 543
            today_str = datetime.now(pytz.timezone('Asia/Bangkok')).strftime(f"%d %b {today_thai}")
            
            content = page.content()
            # Logic: ค้นหาอักษรย่อหุ้นในแถวที่มีวันที่ปัจจุบัน
            # (ปรับปรุงจาก Selector จริงของ SET)
            rows = page.locator("tr").all_inner_texts()
            symbols = []
            for row in rows:
                if today_str in row:
                    # สมมติว่าชื่อหุ้นอยู่คำแรกของบรรทัด
                    symbols.append(row.split()[0])
            browser.close()
            return list(set(symbols))
        except:
            browser.close()
            return []

def get_us_ipo_list():
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
    hour = now_th.hour
    
    report = f"📊 **รายงานหุ้น IPO ประจำวันที่ {now_th.strftime('%d/%m/%Y')}** 📊\n"
    report += "Status: ตลาดเปิดทำการแล้ว\n" + "—"*15 + "\n"

    # ช่วงเช้า (เน้นไทย)
    if 9 <= hour <= 12:
        stocks = get_thai_ipo_list()
        report += "🇹🇭 **หุ้นไทยเข้าใหม่ (SET/mai):**\n"
        if stocks:
            for s in stocks:
                op, cp, diff = get_open_price(s, "TH")
                if op:
                    emoji = "🚀" if diff > 0 else "📉" if diff < 0 else "➖"
                    report += f"🔹 **{s}** | ราคาเปิด: {op} | ล่าสุด: {cp} ({diff}%) {emoji}\n"
                else:
                    report += f"🔹 **{s}** | ⏳ กำลังรอราคาเปิดจากระบบ...\n"
        else:
            report += "วันนี้ไม่มีหุ้น IPO ไทยครับ\n"

    # ช่วงดึก (เน้น US)
    else:
        stocks = get_us_ipo_list()
        report += "🇺🇸 **หุ้นสหรัฐฯ เข้าใหม่ (US):**\n"
        if stocks:
            for s in stocks:
                sym = s['symbol']
                op, cp, diff = get_open_price(sym, "US")
                if op:
                    emoji = "🚀" if diff > 0 else "📉" if diff < 0 else "➖"
                    report += f"🔹 **{sym}** | ราคาเปิด: ${op} | ล่าสุด: ${cp} ({diff}%) {emoji}\n"
                else:
                    report += f"🔹 **{sym}** | ⏳ หุ้นกำลังรอเข้ากระดานเทรด (ระดมทุนที่ ${s.get('price')})\n"
        else:
            report += "วันนี้ไม่มีหุ้น IPO สหรัฐฯ ครับ\n"

    if DISCORD_WEBHOOK_URL:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": report})
