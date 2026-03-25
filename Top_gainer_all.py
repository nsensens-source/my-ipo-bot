import yfinance as yf
import pandas as pd
import requests
import os
import time
import logging

# ปิดการแจ้งเตือนขยะจาก yfinance
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ดึงค่า Webhook
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1476755678931456062/LpfG3Eq5jgnOmW8-q2BhfGPAEK3Jd-YEbiaH2oJiEHis0B51mvkYILkKuIKbu3Y3yKc5'
# --- ตั้งค่าตัวกรองหุ้น (Filters) ---
MIN_PRICE = 3.0                 # ราคาขั้นต่ำ 3 ดอลลาร์
MIN_DOLLAR_VOLUME = 15_000_000  # มูลค่าซื้อขายเฉลี่ยขั้นต่ำ 15 ล้านดอลลาร์/วัน

def get_all_us_tickers():
    """ดึงรายชื่อหุ้นทั้งหมดจาก SEC (ก.ล.ต. สหรัฐฯ) เพื่อสแกนทั้งตลาด 100%"""
    valid_tickers = set()
    headers = {'User-Agent': 'US_Stock_Scanner user@example.com'}
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        response = requests.get(url, headers=headers)
        for item in response.json().values():
            ticker = item['ticker'].replace('.', '-')
            # กรองเฉพาะหุ้นกระดานหลักที่มีสัญลักษณ์ไม่เกิน 4 ตัวอักษร
            if len(ticker) <= 4 or '-' in ticker:
                valid_tickers.add(ticker)
    except Exception as e:
        print(f"SEC Fetch Error: {e}")
        
    return list(valid_tickers)

def format_pct(current, previous):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def send_to_discord(df, title, webhook_url):
    """ฟังก์ชันจัดการส่งข้อความเข้า Discord แบบตัดก้อนอัตโนมัติ"""
    if df.empty: return
    
    header = f"🎯 **{title}** 🎯\n"
    cb = "```" 
    table_header = f"{cb}text\n{'Ticker':<6} | {'Price':<7} | {'Today':<8} | D-1 to D-4 Trend\n"
    table_header += "-" * 60 + "\n"
    
    current_msg = header + table_header
    messages_to_send = []

    for _, row in df.iterrows():
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

    for msg in messages_to_send:
        requests.post(webhook_url, json={"content": msg})
        time.sleep(1)

def main():
    print("🚀 เริ่มสแกนหุ้นทั้งตลาดสหรัฐฯ (Fully Automatic)...")
    tickers = get_all_us_tickers()
    
    if not tickers:
        print("ไม่สามารถดึงรายชื่อหุ้นได้")
        return
        
    print(f"พบรายชื่อหุ้นในระบบทั้งหมด {len(tickers)} ตัว")
    print("กำลังดาวน์โหลดข้อมูล (แบ่งเป็นรอบๆ เพื่อป้องกัน Yahoo บล็อก)...")

    results = []
    # ลด Chunk ลงมาเหลือ 100 เพื่อการันตีไม่ให้ Yahoo ทำข้อมูลหาย
    chunk_size = 100 
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        if len(chunk) == 1: chunk.append('AAPL')

        # โหลดข้อมูล
        data = yf.download(chunk, period="12d", interval="1d", threads=True, progress=False)
        
        if 'Close' not in data or len(data['Close']) < 6: continue
            
        close_data = data['Close']
        volume_data = data['Volume']
        
        # 🛡️ ล็อกวันที่จากแกนเวลา (Index) โดยตรง 
        # วิธีนี้แก้ปัญหา yfinance แอบลบแถวที่ข้อมูลไม่ครบจนทำให้การคำนวณ % เพี้ยนไปเป็นของเมื่อวาน
        try:
            d0 = close_data.index[-1] # วันล่าสุด
            d1 = close_data.index[-2] # 1 วันก่อน
            d2 = close_data.index[-3] # 2 วันก่อน
            d3 = close_data.index[-4]
            d4 = close_data.index[-5]
            d5 = close_data.index[-6]
        except IndexError:
            continue
        
        for ticker in chunk:
            try:
                if ticker not in close_data.columns: continue
                
                # ดึงราคาจากวันที่ถูกล็อกไว้เท่านั้น
                curr_price = close_data.loc[d0, ticker]
                prev_price = close_data.loc[d1, ticker]
                
                # ถ้าวันล่าสุดยังไม่มีราคา ให้ข้ามไปก่อน
                if pd.isna(curr_price) or pd.isna(prev_price): continue
                    
                # คำนวณ Volume เฉลี่ย 5 วัน
                avg_vol_5d = volume_data[ticker].tail(5).mean()
                if pd.isna(avg_vol_5d): continue
                
                # --- 🛡️ FILTER LOGIC ---
                if curr_price < MIN_PRICE: continue
                dollar_vol = curr_price * avg_vol_5d
                if dollar_vol < MIN_DOLLAR_VOLUME: continue
                # ------------------------
                
                today_pct_val = ((curr_price - prev_price) / prev_price) * 100
                
                # ดึง % ย้อนหลังด้วยวันที่ล็อกไว้เป๊ะๆ
                hist_1 = format_pct(close_data.loc[d1, ticker], close_data.loc[d2, ticker])
                hist_2 = format_pct(close_data.loc[d2, ticker], close_data.loc[d3, ticker])
                hist_3 = format_pct(close_data.loc[d3, ticker], close_data.loc[d4, ticker])
                hist_4 = format_pct(close_data.loc[d4, ticker], close_data.loc[d5, ticker])
                
                results.append({
                    'Ticker': ticker,
                    'Price': curr_price,
                    'Today': format_pct(curr_price, prev_price),
                    'SortVal': today_pct_val,
                    'History': f"{hist_1} {hist_2} {hist_3} {hist_4}"
                })
            except Exception:
                continue
                
        # พักให้ Yahoo หายใจ
        time.sleep(1)

    if not results:
        print("ไม่พบหุ้นที่ผ่านเกณฑ์")
        return
        
    all_df = pd.DataFrame(results)

    # จัดอันดับ Top 50 จากทั้งตลาด 100%
    top_50 = all_df.sort_values(by='SortVal', ascending=False).head(50)
    
    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ Webhook URL กรุณาตั้งค่า DISCORD_WEBHOOK_TOPGAINER")
        print(top_50.head())
        return

    # --- ส่งเข้า Discord ---
    print("ส่งข้อมูล Top 50 Gainers (Automatic)...")
    title_top50 = f"TOP 50 GAINERS (Price > ${MIN_PRICE}, Avg Vol > ${MIN_DOLLAR_VOLUME/1_000_000}M)"
    send_to_discord(top_50, title_top50, DISCORD_WEBHOOK_URL)
        
    print("✅ สแกนทั้งตลาดและส่งเข้า Discord เรียบร้อย!")

if __name__ == "__main__":
    main()
