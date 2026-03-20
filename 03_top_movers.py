import requests
import pandas as pd
import os
import sys
from io import StringIO
import re

# --- ⚙️ Igenamiteranyirizo (Configuration) ---
# Kohereza kuri Discord ukoresheje Webhook
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_TOPMOVER")

def clean_ticker(raw_ticker):
    """
    🧩 Gukora isuku kuri Ticker: Kuraho inyuguti z'ikosa nka 'P PLUG' -> 'PLUG'
    """
    if not isinstance(raw_ticker, str):
        return str(raw_ticker)
    
    # Gukata inyuguti dukoresheje umwanya (space)
    parts = raw_ticker.split()
    clean_name = parts[-1] if parts else raw_ticker
    
    # Kuraho ibimenyetso bidasanzwe
    clean_name = re.sub(r'[^A-Z0-9.]', '', clean_name.upper())
    return clean_name

def get_most_active(region="US", count=100):
    """
    🌐 Gushaka imigabane ikora cyane kurusha iyindi kuri Yahoo Finance
    """
    print(f"🌐 Gushaka imigabane {count} ya mbere kuri {region}...")
    
    # 🧩 Hitamo URL ijyanye n'isoko ryifuzwa
    if region == "TH":
        # Plan A: Screener ya Thailand
        url = "https://finance.yahoo.com/screener/predefined/most_actives?count=25&offset=0&region=TH"
        limit = 20
    else:
        url = f"https://finance.yahoo.com/screener/predefined/most_actives?count={count}&offset=0&region=US"
        limit = count

    try:
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://finance.yahoo.com/"
        }
        
        res = requests.get(url, headers=header, timeout=20)
        html_data = StringIO(res.text)
        tables = pd.read_html(html_data)
        
        if not tables:
            return []
            
        df = tables[0]
        raw_tickers = df['Symbol'].head(limit).tolist()
        clean_tickers = [clean_ticker(t) for t in raw_tickers if t]
        
        # 🧩 Kugenzura niba isoko rya Thailand ryatanze ibisubizo byo muri US (Redirect)
        if region == "TH" and not any(".BK" in t for t in clean_tickers):
            print("❌ Ikosa: Yahoo yohereje imigabane ya US aho kuba TH. Geregeza Plan B...")
            
            # Plan B: Fallback URL ijyanye n'isoko rya Thailand ryonyine
            fallback_url = "https://finance.yahoo.com/markets/stocks/most-active/?region=th"
            res = requests.get(fallback_url, headers=header, timeout=20)
            tables = pd.read_html(StringIO(res.text))
            
            if tables:
                df = tables[0]
                raw_tickers = df['Symbol'].head(limit).tolist()
                clean_tickers = [clean_ticker(t) for t in raw_tickers if t]
                
                if any(".BK" in t for t in clean_tickers):
                    print("✅ Plan B yagenze neza!")
                    return clean_tickers
            
            return []

        return clean_tickers
    except Exception as e:
        print(f"❌ Ikosa ryabonetse: {e}")
        return []

def send_to_discord(tickers, market_name):
    """
    📤 Kohereza amakuru kuri Discord
    """
    if not tickers: 
        print(f"⚠️ Nta makuru ahari kuri {market_name}. Gusimbuka.")
        return
    
    if not DISCORD_URL or DISCORD_URL == "None":
        print("❌ Ikosa: DISCORD_WEBHOOK_TOPMOVER ntabwo yateguwe!")
        return
        
    ticker_str = "\n".join(tickers)
    msg = {
        "content": f"🏆 **TOP MOVERS: {market_name}**\n```text\n{ticker_str}\n```"
    }
    
    try:
        res = requests.post(DISCORD_URL, json=msg)
        if res.status_code in [200, 204]:
            print(f"✅ Byoherejwe kuri Discord ({market_name}).")
    except: pass

if __name__ == "__main__":
    print("🚀 Gutangira gushaka imigabane...")
    
    # Isoko rya Thailand (TH)
    th_list = get_most_active("TH", 20)
    if th_list:
        send_to_discord(th_list, "🇹🇭 THAI MARKET (TOP 20)")
    else:
        print("⚠️ Ntibishoboye kubona imigabane ya TH (Redirect issue).")
        
    # Isoko rya US
    us_list = get_most_active("US", 100)
    if us_list:
        send_to_discord(us_list, "🇺🇸 US MARKET (TOP 100)")
