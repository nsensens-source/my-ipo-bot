import yfinance as yf
import pandas as pd
import requests
import time
import os

# แนะนำให้ใช้ GitHub Secrets ในการเก็บ URL เพื่อความปลอดภัย
# โดยตั้งชื่อ Secret ว่า DISCORD_WEBHOOK
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1476755678931456062/LpfG3Eq5jgnOmW8-q2BhfGPAEK3Jd-YEbiaH2oJiEHis0B51mvkYILkKuIKbu3Y3yKc5'

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers)
        df = pd.read_html(response.text)[0]
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return []

def format_stat(current, previous):
    """คำนวณ % และคืนค่าพร้อม Emoji วงกลม สีเขียว/แดง"""
    if previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def main():
    print("🚀 เริ่มวิเคราะห์หุ้น US Top Gainers และประวัติ 5 วัน...")
    tickers = get_sp500_tickers()
    if not tickers: return

    # ดึงข้อมูลย้อนหลัง 12 วันเพื่อให้ได้วันทำการครบถ้วน
    data = yf.download(tickers, period="12d", interval="1d", group_by='ticker', threads=True)
    
    all_results = []
    for ticker in tickers:
        try:
            # ดึงราคาปิดและลบค่าที่เป็น NaN
            history = data[ticker]['Close'].dropna()
            if len(history) < 6: continue 
            
            # ดึง 6 วันล่าสุดเพื่อคำนวณการเปลี่ยนแปลงของ 5 วันล่าสุด
            # [Day-5, Day-4, Day-3, Day-2, Day-1, Today]
            h = history.tail(6)
            
            current_price = h.iloc[-1]
            # คำนวณ % Change ของวันนี้เทียบกับเมื่อวานเพื่อจัดอันดับ
            today_pct = ((current_price - h.iloc[-2]) / h.iloc[-2]) * 100
            
            # เก็บข้อมูล List ของ % Change ย้อนหลัง 5 วัน (รวมวันนี้)
            stats = []
            for i in range(1, 6):
                # i=1 คือ Today vs Day-1, i=2 คือ Day-1 vs Day-2 ...
                stats.append(format_stat(h.iloc[-i], h.iloc[-(i+1)]))

            all_results.append({
                'Ticker': ticker,
                'Price': current_price,
                'Change': today_pct,
                'DisplayStats': stats # [Today, Day-1, Day-2, Day-3, Day-4]
            })
        except: continue

    # เลือก Top 50 ที่ขึ้นแรงที่สุดวันนี้
    df = pd.DataFrame(all_results)
    top_50 = df.sort_values(by='Change', ascending=False).head(50)

    # เตรียมส่ง Discord
    header_text = "🚀 **TOP 50 US GAINERS (5-DAY TREND)** 🚀\n"
    table_header = f"{'Ticker':<7} | {'Price':<7} | {'Today':<7} | {'History (D-1 to D-4)':<25}\n"
    sep = "-" * 62 + "\n"
    
    current_batch = ""
    for _, row in top_50.iterrows():
        # รูปแบบ: Today | Day-1 Day-2 Day-3 Day-4
        history_line = " ".join(row['DisplayStats'][1:]) 
        line = f"{row['Ticker']:<7} | {row['Price']:>7.2f} | {row['DisplayStats'][0]:<7} | {history_line}\n"
        
        # ตรวจสอบความยาวไม่ให้เกิน 2000 ตัวอักษรต่อหนึ่งข้อความ Discord
        if len(header_text + "```\n" + current_batch + line + "```") > 1900:
            full_msg = header_text + "```\n" + table_header + sep + current_batch + "```"
            requests.post(DISCORD_WEBHOOK_URL, json={"content": full_msg})
            current_batch = line
            header_text = "" # หัวข้อส่งแค่ครั้งแรก
        else:
            current_batch += line

    if current_batch:
        full_msg = header_text + "```\n" + (table_header if header_text else "") + sep + current_batch + "```"
        requests.post(DISCORD_WEBHOOK_URL, json={"content": full_msg})

    print("✅ วิเคราะห์เสร็จสิ้นและส่งข้อมูลเข้า Discord เรียบร้อยแล้ว")

if __name__ == "__main__":
    main()
