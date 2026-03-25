import yfinance as yf
import pandas as pd
import requests
import time
import os

# แนะนำให้ใช้ GitHub Secrets ในการเก็บ URL เพื่อความปลอดภัย
# โดยตั้งชื่อ Secret ว่า DISCORD_WEBHOOK
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_TOPGAINER')

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    df = pd.read_html(response.text)[0]
    # แปลง . เป็น - สำหรับหุ้นที่มีคลาส (เช่น BRK.B -> BRK-B)
    return df['Symbol'].str.replace('.', '-', regex=False).tolist()

def send_to_discord_chunks(df, title):
    """แบ่งส่งข้อมูลเข้า Discord กลุ่มละ 10-15 ตัว เพื่อไม่ให้ข้อความยาวเกินกำหนด"""
    if not DISCORD_WEBHOOK_URL:
        print("Error: Discord Webhook URL not found.")
        return

    # ส่งหัวข้อ
    requests.post(DISCORD_WEBHOOK_URL, json={"content": f"🔥 **{title}** 🔥"})
    
    # แบ่งส่งทีละ 10 ตัวเพื่อให้แสดงผลสวยงามบนมือถือ
    chunks = [df[i:i + 10] for i in range(0, len(df), 10)]
    
    for chunk in chunks:
        message = "```\n"
        message += f"{'Ticker':<7} | {'Change%':<8} | {'Price':<8} | {'Prev 3 Days'}\n"
        message += "-" * 50 + "\n"
        
        for _, row in chunk.iterrows():
            # ดึงประวัติ 3 วันล่าสุดมาโชว์คู่กัน
            history = f"{row['Day-1 (Prev)']}, {row['Day-2']}, {row['Day-3']}"
            line = f"{row['Ticker']:<7} | {row['Change %']:>7}% | {row['Current Price']:>8} | {history}\n"
            message += line
        
        message += "```"
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        time.sleep(1) # ป้องกัน Discord Rate Limit (429)

def main():
    print("🚀 Starting Stock Analysis...")
    tickers = get_sp500_tickers()
    
    # ดึงข้อมูลรวดเดียว (Batch Download)
    # period="10d" เพื่อให้มั่นใจว่าได้วันทำการครบ แม้ติดเสาร์-อาทิตย์
    data = yf.download(tickers, period="10d", interval="1d", group_by='ticker', threads=True)
    
    all_results = []
    for ticker in tickers:
        try:
            # ดึงราคาปิด 6 แถว (วันนี้ + ย้อนหลัง 5 วันทำการ)
            history = data[ticker]['Close'].dropna().tail(6)
            if len(history) < 6: continue
            
            curr = history.iloc[-1]
            prev = history.iloc[-2]
            pct_change = ((curr - prev) / prev) * 100
            
            # เก็บข้อมูลลง List
            all_results.append({
                'Ticker': ticker,
                'Current Price': round(curr, 2),
                'Change %': round(pct_change, 2),
                'Day-1 (Prev)': round(history.iloc[-2], 2),
                'Day-2': round(history.iloc[-3], 2),
                'Day-3': round(history.iloc[-4], 2)
            })
        except:
            continue

    # แปลงเป็น DataFrame และดึง Top 50 Gainers
    df = pd.DataFrame(all_results)
    top_50 = df.sort_values(by='Change %', ascending=False).head(50)
    
    # ส่งข้อมูลเข้า Discord
    send_to_discord_chunks(top_50, "TOP 50 US GAINERS TODAY (S&P 500)")
    print("✅ Analysis sent to Discord successfully.")

if __name__ == "__main__":
    main()
