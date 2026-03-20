import requests
import pandas as pd
import os
import sys
from io import StringIO

# --- ⚙️ CONFIG ---
# ดึง Discord Webhook จาก Environment Variable
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_TOPMOVER")

def get_most_active(region="US", count=100):
    """ดึงข้อมูลหุ้นที่มีความเคลื่อนไหวสูงสุดจาก Yahoo Finance"""
    print(f"🌐 กำลังดึงข้อมูล Top {count} สำหรับตลาด {region}...")
    
    # 🧩 ปรับปรุง URL: ใช้ Screener URL แทน Most-Active ทั่วไป เพื่อความแม่นยำของภูมิภาค
    if region == "TH":
        # URL สำหรับตลาดหุ้นไทยโดยเฉพาะ (SET)
        url = "https://finance.yahoo.com/screener/predefined/most_actives?offset=0&count=25&dependent=it&region=TH"
        limit = 20
    else:
        # URL สำหรับตลาดหุ้น US
        url = f"https://finance.yahoo.com/screener/predefined/most_actives?offset=0&count={count}"
        limit = count

    try:
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        res = requests.get(url, headers=header, timeout=15)
        
        # ใช้ StringIO ห่อ HTML string ตามคำแนะนำของ Pandas
        html_data = StringIO(res.text)
        tables = pd.read_html(html_data)
        
        if not tables:
            print(f"⚠️ ไม่พบตารางข้อมูลสำหรับ {region}")
            return []
            
        df = tables[0]
        
        # ดึงรายชื่อหุ้น
        tickers = df['Symbol'].head(limit).tolist()

        # 🧩 Double Check: ถ้าเป็นตลาด TH แต่ไม่มีหุ้นตัวไหนลงท้ายด้วย .BK เลย 
        # แสดงว่า Yahoo ดีดเรากลับไปหน้า US ให้ส่งค่าว่างกลับไปเพื่อไม่ให้ข้อมูลผิดพลาด
        if region == "TH" and not any(".BK" in str(t) for t in tickers):
            print(f"❌ ตรวจพบความผิดพลาด: ระบบดึงหุ้น US มาแทนที่ TH (กำลังลองดึงใหม่...)")
            return []

        return tickers
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการดึงข้อมูล {region}: {e}")
        return []

def send_to_discord(tickers, market_name):
    """ส่งรายชื่อหุ้นไปยัง Discord"""
    if not tickers: 
        print(f"⚠️ ไม่มีข้อมูลหุ้นสำหรับ {market_name} (ข้ามการส่ง)")
        return
    
    if not DISCORD_URL or DISCORD_URL == "None":
        print("❌ Error: ไม่ได้ตั้งค่า DISCORD_WEBHOOK_TOPMOVER ในระบบ!")
        return
        
    ticker_str = "\n".join(tickers)
    msg = {
        "content": f"🏆 **TOP MOVERS: {market_name}**\nพบหุ้นที่มีความเคลื่อนไหวสูงสุด {len(tickers)} อันดับแรก\n```text\n{ticker_str}\n```"
    }
    
    try:
        res = requests.post(DISCORD_URL, json=msg)
        if res.status_code in [200, 204]:
            print(f"✅ ส่งข้อมูล {market_name} ไปยัง Discord เรียบร้อย")
        else:
            print(f"❌ Discord Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ ไม่สามารถส่งข้อมูลไปยัง Discord ได้: {e}")

if __name__ == "__main__":
    # ตรวจสอบอาร์กิวเมนต์ที่ส่งมา
    if len(sys.argv) > 1:
        market = sys.argv[1].upper()
        if market == "TH":
            top_list = get_most_active("TH", 20)
            send_to_discord(top_list, "🇹🇭 THAI MARKET (TOP 20)")
        elif market == "US":
            top_list = get_most_active("US", 100)
            send_to_discord(top_list, "🇺🇸 US MARKET (TOP 100)")
    else:
        # หากไม่ระบุ ให้รันทั้งไทยและ US
        print("🚀 ไม่ได้ระบุตลาด กำลังเริ่มดึงข้อมูลทั้ง TH และ US...")
        
        # รันไทยก่อน
        th_list = get_most_active("TH", 20)
        send_to_discord(th_list, "🇹🇭 THAI MARKET (TOP 20)")
        
        # รัน US ต่อ
        us_list = get_most_active("US", 100)
        send_to_discord(us_list, "🇺🇸 US MARKET (TOP 100)")
