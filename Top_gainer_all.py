import yfinance as yf
import pandas as pd
import requests
import os
import time

# 1. ดึงค่า Webhook
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_TOPGAINER')

# --- ตั้งค่าตัวกรองหุ้น (Filters) ---
MIN_PRICE = 3.0           # ราคาขั้นต่ำ 3 ดอลลาร์ (ตัดหุ้นปั่น/Penny Stocks)
MIN_DOLLAR_VOLUME = 15_000_000  # มูลค่าซื้อขายขั้นต่ำ 15 ล้านดอลลาร์/วัน (ตัดหุ้นไร้สภาพคล่อง)

def get_all_us_tickers():
    """ดึงรายชื่อหุ้นทั้งหมดที่จดทะเบียนใน ก.ล.ต. สหรัฐฯ (SEC)"""
    # SEC บังคับให้ใส่ User-Agent เป็นรูปแบบ ชื่อ/อีเมล
    headers = {'User-Agent': 'US_Stock_Scanner user@example.com'}
    url = "https://www.sec.gov/files/company_tickers.json"
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        # ดึงแค่สัญลักษณ์หุ้น และแปลง . เป็น - สำหรับ yfinance (เช่น BRK.B -> BRK-B)
        tickers = [item['ticker'].replace('.', '-') for item in data.values()]
        # ตัดตัวซ้ำ
        return list(set(tickers))
    except Exception as e:
        print(f"Error fetching from SEC: {e}")
        return []

def format_pct(current, previous):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def main():
    print("🚀 เริ่มสแกนหุ้นทั้งตลาดสหรัฐฯ (Market-Wide Scan)...")
    tickers = get_all_us_tickers()
    
    if not tickers:
        print("ไม่สามารถดึงรายชื่อหุ้นจาก SEC ได้")
        return
        
    print(f"พบรายชื่อหุ้นในระบบทั้งหมด {len(tickers)} ตัว")
    print("กำลังดาวน์โหลดข้อมูลราคาย้อนหลัง (อาจใช้เวลา 1-3 นาที)...")

    # ดาวน์โหลดแบบ Batch ทีเดียวทั้งตลาด (เร็วที่สุด)
    data = yf.download(tickers, period="12d", interval="1d", threads=True)
    
    # แยก DataFrame ของราคาปิดและ Volume เพื่อง่ายต่อการคำนวณ
    close_data = data['Close']
    volume_data = data['Volume']

    results = []
    
    # วนลูปเช็คหุ้นทุกตัว
    for ticker in close_data.columns:
        try:
            h_close = close_data[ticker].dropna()
            h_vol = volume_data[ticker].dropna()
            
            if len(h_close) < 6 or len(h_vol) < 1: 
                continue
                
            curr_price = h_close.iloc[-1]
            prev_price = h_close.iloc[-2]
            curr_vol = h_vol.iloc[-1]
            
            # --- 🛡️ FILTER LOGIC (ระบบคัดกรอง) 🛡️ ---
            # 1. ถ้าราคาต่ำกว่าที่เราตั้งไว้ ให้ข้ามไปเลย
            if curr_price < MIN_PRICE:
                continue
                
            # 2. คำนวณมูลค่าการซื้อขาย (Dollar Volume)
            dollar_vol = curr_price * curr_vol
            if dollar_vol < MIN_DOLLAR_VOLUME:
                continue
            # ----------------------------------------
            
            today_pct_val = ((curr_price - prev_price) / prev_price) * 100
            
            # คำนวณประวัติ 4 วันก่อนหน้า (Day-1 ถึง Day-4) เรียงจากใหม่ไปเก่า
            d1 = format_pct(h_close.iloc[-2], h_close.iloc[-3])
            d2 = format_pct(h_close.iloc[-3], h_close.iloc[-4])
            d3 = format_pct(h_close.iloc[-4], h_close.iloc[-5])
            d4 = format_pct(h_close.iloc[-5], h_close.iloc[-6])
            
            results.append({
                'Ticker': ticker,
                'Price': curr_price,
                'Today': format_pct(curr_price, prev_price),
                'SortVal': today_pct_val,
                'History': f"{d1} {d2} {d3} {d4}",
                'Vol_M': f"${dollar_vol / 1_000_000:.1f}M" # เก็บค่า Volume ไว้ดูเผื่อวิเคราะห์
            })
        except Exception:
            continue

    if not results:
        print("ไม่พบหุ้นที่ผ่านเกณฑ์การคัดกรอง")
        return
        
    # จัดอันดับ Top 50 จากหุ้นที่ผ่านการคัดกรองทั้งหมด
    top_50 = pd.DataFrame(results).sort_values(by='SortVal', ascending=False).head(50)

    # ตรวจสอบ Webhook ก่อนส่ง
    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ DISCORD_WEBHOOK_TOPGAINER ใน Environment Variables")
        return

    # --- ส่วนของการส่งเข้า Discord ---
    header = "🎯 **TOP 50 GAINERS (LIQUIDITY FILTERED)** 🎯\n"
    header += f"*Filter: Price > ${MIN_PRICE}, Vol > ${MIN_DOLLAR_VOLUME/1_000_000}M*\n"
    
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
