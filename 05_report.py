import os
from supabase import create_client
import requests
from datetime import datetime, timedelta

# --- ⚙️ CONFIGURATION ---
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_NAME = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"

def send_to_discord(embed):
    payload = {
        "embeds": [embed]
    }
    requests.post(DISCORD_URL, json=payload)

def generate_weekly_report():
    print(f"📊 Generating Weekly Report from {TABLE_NAME}...")
    
    # ดึงข้อมูลหุ้นที่ขายไปแล้วในรอบ 7 วันล่าสุด
    one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    res = supabase.table(TABLE_NAME).select("*").eq("status", "sold").execute()
    sold_stocks = res.data
    
    # ดึงข้อมูลหุ้นที่ยังถืออยู่
    active_res = supabase.table(TABLE_NAME).select("*").eq("status", "bought").execute()
    active_stocks = active_res.data

    total_profit = 0
    win_count = 0
    loss_count = 0
    best_trade = {"ticker": "N/A", "gain": -999}

    for s in sold_stocks:
        buy = s.get('buy_price', 0)
        sell = s.get('sell_price', 0)
        if buy > 0:
            profit_pct = ((sell / buy) - 1) * 100
            total_profit += profit_pct
            if profit_pct > 0: win_count += 1
            else: loss_count += 1
            
            if profit_pct > best_trade['gain']:
                best_trade = {"ticker": s['ticker'], "gain": profit_pct}

    # สร้าง Embed Message สำหรับ Discord
    embed = {
        "title": "📈 Weekly Trading Summary",
        "color": 3066993, # สีฟ้า
        "fields": [
            {"name": "💼 Active Holdings", "value": f"{len(active_stocks)} tickers", "inline": True},
            {"name": "✅ Completed Trades", "value": f"{len(sold_stocks)} trades", "inline": True},
            {"name": "📊 Avg. Profit/Loss", "value": f"{total_profit/max(len(sold_stocks),1):.2f}%", "inline": False},
            {"name": "🏆 Best Trade", "value": f"{best_trade['ticker']} ({best_trade['gain']:.2f}%)", "inline": True},
            {"name": "⚖️ Win Rate", "value": f"{(win_count/max(len(sold_stocks),1))*100:.1f}%", "inline": True}
        ],
        "footer": {"text": f"Report generated on {datetime.now().strftime('%Y-%m-%d')}"}
    }

    send_to_discord(embed)
    print("✅ Report sent to Discord.")

if __name__ == "__main__":
    generate_weekly_report()
