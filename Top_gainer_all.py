import yfinance as yf
import pandas as pd
import requests
import os
import time
import logging
import io

# ปิดการแจ้งเตือนขยะจาก yfinance
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ดึงค่า Webhook
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1476755678931456062/LpfG3Eq5jgnOmW8-q2BhfGPAEK3Jd-YEbiaH2oJiEHis0B51mvkYILkKuIKbu3Y3yKc5'

# --- ตั้งค่าตัวกรองหุ้น (Filters) ---
MIN_PRICE = 3.0           # ราคาขั้นต่ำ 3 ดอลลาร์
MIN_DOLLAR_VOLUME = 15_000_000  # มูลค่าซื้อขายเฉลี่ยขั้นต่ำ 15 ล้านดอลลาร์/วัน
# ใส่ชื่อหุ้นที่อยากบังคับให้ระบบเช็คเสมอ การันตีไม่ให้ตกหล่น
CUSTOM_WATCHLIST = ['SPY', 'QQQ', 'DIA', 'AAOI', 'LITE', 'PLTR', 'SOFI', 'ARM'] 

def get_all_us_tickers():
    """ดึงรายชื่อหุ้นจาก SEC + S&P 500 + Watchlist เพื่อให้ครบถ้วนที่สุด"""
    valid_tickers = set(CUSTOM_WATCHLIST)
    
    # 1. ดึงจาก SEC (ครอบคลุมทั้งตลาด)
    headers = {'User-Agent': 'US_Stock_Scanner user@example.com'}
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        response = requests.get(url, headers=headers)
        for item in response.json().values():
            ticker = item['ticker'].replace('.', '-')
            if len(ticker) <= 4 or '-' in ticker:
                valid_tickers.add(ticker)
    except Exception as e:
        print(f"SEC Fetch Error: {e}")

    # 2. ดึงจาก S&P 500 (กันเหนียวเผื่อ SEC ตกหล่น)
    try:
        wiki_url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        html_content = requests.get(wiki_url, headers={'User-Agent': 'Mozilla/5.0'}).text
        # ใช้ io.StringIO ครอบข้อความ html เพื่อแก้ FutureWarning ของ pandas
        df = pd.read_html(io.StringIO(html_content))[0]
        sp500 = df['Symbol'].str.replace('.', '-', regex=False).tolist()
        valid_tickers.update(sp500)
    except Exception as e:
        print(f"S&P 500 Fetch Error: {e}")
        
    return list(valid_tickers)

def format_pct(current, previous):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def main():
    print("🚀 เริ่มสแกนหุ้นทั้งตลาดสหรัฐฯ (Batch Processing)...")
    tickers = get_all_us_tickers()
    
    if not tickers:
        print("ไม่สามารถดึงรายชื่อหุ้นได้")
        return
        
    print(f"พบรายชื่อหุ้นทั้งหมด {len(tickers)} ตัว")
    print("กำลังดาวน์โหลดข้อมูล (แบ่งเป็นรอบๆ เพื่อป้องกันข้อมูลตกหล่น)...")

    results = []
    # ลดขนาดรอบการดาวน์โหลดเหลือ 200 ตัว เพื่อป้องกัน yfinance แอบตัดหุ้นทิ้งเวลาโหลดเยอะๆ
    chunk_size = 200 
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        
        # ป้องกันบั๊กของ yfinance เมื่อดาวน์โหลดหุ้นแค่ตัวเดียว
        if len(chunk) == 1: chunk.append('AAPL')

        # ดาวน์โหลดข้อมูลทีละกลุ่ม
        data = yf.download(chunk, period="12d", interval="1d", threads=True, progress=False)
        
        if 'Close' not in data: continue
            
        close_data = data['Close']
        volume_data = data['Volume']
        
        for ticker in chunk:
            try:
                if ticker not in close_data: continue
                
                h_close = close_data[ticker].dropna()
                h_vol = volume_data[ticker].dropna()
                
                if len(h_close) < 6 or len(h_vol) < 5: continue
                    
                curr_price = h_close.iloc[-1]
                prev_price = h_close.iloc[-2]
                
                # ใช้ Volume เฉลี่ย 5 วันย้อนหลัง ป้องกันบั๊กวอลุ่มหายในวันล่าสุด
                avg_vol_5d = h_vol.tail(5).mean()
                
                # --- 🛡️ FILTER LOGIC ---
                if curr_price < MIN_PRICE: continue
                    
                # คำนวณ Liquidity ด้วย Average Volume แทน
                dollar_vol = curr_price * avg_vol_5d
                if dollar_vol < MIN_DOLLAR_VOLUME: continue
                # ------------------------
                
                today_pct_val = ((curr_price - prev_price) / prev_price) * 100
                
                d1 = format_pct(h_close.iloc[-2], h_close.iloc[-3])
                d2 = format_pct(h_close.iloc[-3], h_close.iloc[-4])
                d3 = format_pct(h_close.iloc[-4], h_close.iloc[-5])
                d4 = format_pct(h_close.iloc[-5], h_close.iloc[-6])
                
                results.append({
                    'Ticker': ticker,
                    'Price': curr_price,
                    'Today': format_pct(curr_price, prev_price),
                    'SortVal': today_pct_val,
                    'History': f"{d1} {d2} {d3} {d4}"
                })
            except Exception:
                continue
                
        # หยุดพัก 1.5 วินาที เพื่อถนอมการยิง Request
        time.sleep(1.5)

    if not results:
        print("ไม่พบหุ้นที่ผ่านเกณฑ์")
        return
        
    # จัดอันดับ Top 50 
    top_50 = pd.DataFrame(results).sort_values(by='SortVal', ascending=False).head(50)

    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ Webhook URL")
        return

    # --- ส่วนของการส่งเข้า Discord ---
    header = "🎯 **TOP 50 GAINERS (FULL MARKET SCAN)** 🎯\n"
    header += f"*Filter: Price > ${MIN_PRICE}, Avg 5D Vol > ${MIN_DOLLAR_VOLUME/1_000_000}M*\n"
    
    cb = "```" 
    table_header = f"{cb}text\n{'Ticker':<6} | {'Price':<7} | {'Today':<8} | D-1 to D-4 Trend\n"
    table_header += "-" * 60 + "\n"
    
    current_msg = header + table_header
    messages_to_send = []

    for _, row in top_50.iterrows():
        line = f"{row['Ticker']:<6} | {row['Price']:>7.2f} | {row['Today']:<8} | {row['History']}\n"
        
        if len(current_msg) + len(line) > 1900:
            current_msg += f"{cb}" 
            messages_to_send.append(current_msg)
            current_msg = f"{cb}text\n" + line 
        else:
            current_msg += line

    if not current_msg.endswith(f"{cb}"):
        current_msg += f"{cb}"
        messages_to_send.append(current_msg)

    # ยิงข้อความเข้า Discord
    for msg in messages_to_send:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        time.sleep(1)
        
    print("✅ สแกนทั้งตลาดและส่ง Top 50 เข้า Discord เรียบร้อย!")

if __name__ == "__main__":
    main()
