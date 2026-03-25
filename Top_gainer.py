import yfinance as yf
import pandas as pd
import requests
import json
import requests

# --- ตั้งค่า Webhook ของคุณที่นี่ ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1476755678931456062/LpfG3Eq5jgnOmW8-q2BhfGPAEK3Jd-YEbiaH2oJiEHis0B51mvkYILkKuIKbu3Y3yKc5"

def send_to_discord(df):
    """ส่งข้อมูล Top 10 Gainers เข้า Discord ในรูปแบบตารางที่อ่านง่าย"""
    if not DISCORD_WEBHOOK_URL or "YOUR_DISCORD" in DISCORD_WEBHOOK_URL:
        print("\n[!] กรุณาใส่ Discord Webhook URL ก่อนครับ")
        return

    # เลือกมาแค่ Top 10 เพื่อไม่ให้ข้อความยาวเกิน Limit ของ Discord (2000 ตัวอักษร)
    top_10 = df.head(10)
    
    # สร้างหัวข้อและตารางแบบ Text-based
    message = "🚀 **Top 10 US Stock Gainers Today (S&P 500)** 🚀\n"
    message += "```\n"
    message += f"{'Ticker':<7} | {'Change%':<8} | {'Price':<8} | {'5-Day History (Last to Oldest)':<30}\n"
    message += "-" * 70 + "\n"

    for _, row in top_10.iterrows():
        history_str = f"{row['Day-1 (Prev)']}, {row['Day-2']}, {row['Day-3']}, {row['Day-4']}, {row['Day-5']}"
        line = f"{row['Ticker']:<7} | {row['Change %']:>7}% | {row['Current Price']:>8} | {history_str}\n"
        message += line
    
    message += "```"

    payload = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    
    if response.status_code == 204:
        print("\n[Success] ส่งข้อมูลเข้า Discord เรียบร้อยแล้ว!")
    else:
        print(f"\n[Error] ไม่สามารถส่งข้อมูลได้: {response.status_code}, {response.text}")

def get_top_50_gainers_with_history():
    print("กำลังดึงข้อมูลและวิเคราะห์หุ้น US...")
    
    # --- ส่วนที่แก้ไข: เพิ่ม User-Agent เพื่อแก้ Error 403 ---
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        # ใช้ pd.read_html อ่านจาก text ของ response แทนการใส่ URL ตรงๆ
        payload = pd.read_html(response.text)
        df_sp500 = payload[0]
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงรายชื่อหุ้น: {e}")
        return pd.DataFrame() # ส่ง DataFrame ว่างกลับไปถ้าดึงไม่ได้
    # --------------------------------------------------

    tickers = df_sp500['Symbol'].str.replace('.', '-', regex=False).tolist()

    # ดึงข้อมูลราคาย้อนหลัง
    data = yf.download(tickers, period="10d", interval="1d", group_by='ticker', threads=True)

    gainer_list = []
    for ticker in tickers:
        try:
            history = data[ticker]['Close'].dropna().tail(6)
            if len(history) < 6: continue

            current_close = history.iloc[-1]
            prev_close = history.iloc[-2]
            percent_change = ((current_close - prev_close) / prev_close) * 100
            last_5_days = history.tail(5).round(2).tolist()

            gainer_list.append({
                'Ticker': ticker,
                'Current Price': round(current_close, 2),
                'Change %': round(percent_change, 2),
                'Day-5': last_5_days[0],
                'Day-4': last_5_days[1],
                'Day-3': last_5_days[2],
                'Day-2': last_5_days[3],
                'Day-1 (Prev)': last_5_days[4]
            })
        except: continue

    df_result = pd.DataFrame(gainer_list)
    top_50 = df_result.sort_values(by='Change %', ascending=False).head(50)
    return top_50

if __name__ == "__main__":
    result_df = get_top_50_gainers_with_history()
    
    # แสดงผลใน Terminal
    print(result_df.head(10))
    
    # ส่งเข้า Discord (Top 10 เพื่อความสวยงามในแอป)
    send_to_discord(result_df)
    
    # บันทึกไฟล์ CSV เก็บไว้ดูเอง (ครบทั้ง 50 อันดับ)
    result_df.to_csv('top_50_gainers_discord.csv', index=False)
