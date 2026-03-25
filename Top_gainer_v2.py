import yfinance as yf
import pandas as pd
import requests
import os

# ดึงค่าจาก GitHub Secrets
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_TOPGAINER')

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        df = pd.read_html(response.text)[0]
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        print(f"Error: {e}")
        return []

def format_pct(current, previous):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def main():
    print("🚀 กำลังดึงข้อมูลและคำนวณเทรนด์ 5 วันล่าสุด...")
    tickers = get_sp500_tickers()
    if not tickers: return

    # ดึงข้อมูลย้อนหลัง
    data = yf.download(tickers, period="12d", interval="1d", group_by='ticker', threads=True)
    
    results = []
    for ticker in tickers:
        try:
            h = data[ticker]['Close'].dropna()
            if len(h) < 6: continue
            
            # ดึงราคาปิดปัจจุบันและเมื่อวาน
            curr = h.iloc[-1]
            prev = h.iloc[-2]
            today_pct_val = ((curr - prev) / prev) * 100
            
            # คำนวณประวัติ 4 วันก่อนหน้า (Day-1 ถึง Day-4)
            d1 = format_pct(h.iloc[-2], h.iloc[-3])
            d2 = format_pct(h.iloc[-3], h.iloc[-4])
            d3 = format_pct(h.iloc[-4], h.iloc[-5])
            d4 = format_pct(h.iloc[-5], h.iloc[-6])
            
            results.append({
                'Ticker': ticker,
                'Price': curr,
                'Today': format_pct(curr, prev),
                'SortVal': today_pct_val,
                'History': f"{d1} {d2} {d3} {d4}"
            })
        except: continue

    # จัดอันดับ Top 50
    top_50 = pd.DataFrame(results).sort_values(by='SortVal', ascending=False).head(50)

    # --- ส่วนของการส่งเข้า Discord ---
    header = "🚀 **TOP 50 US GAINERS (5-DAY TREND %)** 🚀\n"
    table_header = f"
http://googleusercontent.com/immersive_entry_chip/0

---

### โค้ดนี้จะทำงานอย่างไรใน Discord:
* คุณจะได้เห็นตัวเลขเป็น **% Change ล้วนๆ** ในช่อง History แบบนี้ครับ: `🟢1.2% 🔴0.5% 🟢3.4% 🔴1.1%` 
* บล็อกข้อความจะถูกต่อกันยาวๆ ไม่ถูกหั่นทีละ 10 บรรทัดอีกต่อไป (มันจะตัดขึ้นก้อนใหม่แค่ตอนที่ข้อความใกล้จะทะลุ 2,000 ตัวอักษร เพื่อไม่ให้บอทพังครับ)

ลองอัปเดตไฟล์ใน GitHub แล้วรันใหม่อีกครั้งดูนะครับ ได้ผลลัพธ์เป็นลูกศรสีเขียวแดงตามที่ตั้งใจไว้หรือยังครับ?
