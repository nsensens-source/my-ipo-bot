import yfinance as yf
import pandas as pd
import requests
import os
import time

# ดึงค่าจาก GitHub Secrets
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_TOPGAINER')

def get_sp500_tickers():
    url = '[https://en.wikipedia.org/wiki/List_of_S%26P_500_companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        df = pd.read_html(response.text)[0]
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return []

def format_pct(current, previous):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def main():
    print("🚀 กำลังดึงข้อมูลและคำนวณเทรนด์ 5 วันล่าสุด...")
    tickers = get_sp500_tickers()
    if not tickers: 
        print("ไม่สามารถดึงรายชื่อหุ้นได้")
        return

    # ดึงข้อมูลย้อนหลัง 12 วันเพื่อเผื่อวันหยุด
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
            
            # คำนวณประวัติ 4 วันก่อนหน้า (Day-1 ถึง Day-4) เรียงจากใหม่ไปเก่า
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
        except Exception as e:
            continue

    # จัดอันดับ Top 50
    if not results:
        print("ไม่มีข้อมูลหุ้นให้แสดงผล")
        return
        
    top_50 = pd.DataFrame(results).sort_values(by='SortVal', ascending=False).head(50)

    # ตรวจสอบ Webhook ก่อนส่ง
    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ DISCORD_WEBHOOK_TOPGAINER ใน Environment Variables")
        print(top_50.head())
        return

    # --- ส่วนของการส่งเข้า Discord ---
    header = "🚀 **TOP 50 US GAINERS (5-DAY TREND %)** 🚀\n"
    
    # ใช้ตัวแปรแทนเพื่อป้องกันปัญหาระบบตัดข้อความ
    cb = "```" 
    table_header = f"{cb}text\n{'Ticker':<6} | {'Price':<7} | {'Today':<8} | D-1 to D-4 Trend\n"
    table_header += "-" * 60 + "\n"
    
    current_msg = header + table_header
    messages_to_send = []

    for _, row in top_50.iterrows():
        line = f"{row['Ticker']:<6} | {row['Price']:>7.2f} | {row['Today']:<8} | {row['History']}\n"
        
        # เช็คความยาวข้อความไม่ให้เกิน Limit 2000 ตัวอักษรของ Discord
        if len(current_msg) + len(line) > 1900:
            current_msg += f"{cb}" # ปิดโค้ดบล็อกก้อนปัจจุบัน
            messages_to_send.append(current_msg)
            # เริ่มก้อนใหม่
            current_msg = f"{cb}text\n" + line 
        else:
            current_msg += line

    # เก็บข้อความก้อนสุดท้าย
    if not current_msg.endswith(f"{cb}"):
        current_msg += f"{cb}"
        messages_to_send.append(current_msg)

    # ยิงข้อความเข้า Discord ทีละก้อน
    for msg in messages_to_send:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        if response.status_code not in (200, 204):
            print(f"Error sending to Discord: {response.status_code} - {response.text}")
        time.sleep(1) # หน่วงเวลา 1 วินาทีกันบอทโดนบล็อก
        
    print("✅ ส่งข้อมูล 50 อันดับเข้า Discord เรียบร้อย!")

if __name__ == "__main__":
    main()
