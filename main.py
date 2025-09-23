# main.py
import os
import requests
import discord
import asyncio
import pytz
from datetime import datetime, timedelta
from flask import Flask
import threading
from typing import List, Dict

# ------------------- SETTINGS -------------------
POST_HOUR = int(os.getenv("POST_HOUR", "7"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Sofia")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
FCS_API_KEY = os.getenv("FCS_API_KEY")

FILTER_IMPORTANCES = os.getenv("FILTER_IMPORTANCES", "")  # "3,2"
FILTER_CURRENCIES = set([c.strip().upper() for c in os.getenv("FILTER_CURRENCIES", "").split(",") if c.strip()])

# Safety checks
if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
    print("❌ Discord token or channel ID not set!")
    exit(1)
try:
    ch = DISCORD_CHANNEL_ID.strip()
    if ch.startswith("https://discord.com/channels/"):
        DISCORD_CHANNEL_ID = int(ch.split("/")[-1])
    else:
        DISCORD_CHANNEL_ID = int(ch)
except Exception as e:
    print(f"❌ Invalid channel ID: {e}")
    exit(1)

# ------------------- Discord client -------------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ------------------- Flask for Render -------------------
app = Flask(__name__)
@app.route("/")
def home():
    return "ForexNewsBot: alive"
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=run_flask).start()

# ------------------- Helpers -------------------
def safe_translate_to_bg(text: str) -> str:
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx","sl": "en","tl": "bg","dt": "t","q": text}
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        return data[0][0][0] if data and isinstance(data, list) and data[0] else text
    except:
        return text

def split_message(text: str, max_len: int = 1900) -> List[str]:
    if len(text) <= max_len:
        return [text]
    parts, lines, cur = [], text.splitlines(), ""
    for line in lines:
        candidate = (cur + "\n" + line) if cur else line
        if len(candidate) > max_len:
            if cur: parts.append(cur); cur = line
            else:
                for i in range(0, len(line), max_len): parts.append(line[i:i+max_len])
                cur = ""
        else: cur = candidate
    if cur: parts.append(cur)
    return parts

# ------------------- Fetch news -------------------
def get_forex_news(limit: int = 15) -> List[Dict]:
    """Return list of events as dicts with analysis info"""
    events = []
    if not FCS_API_KEY:
        return events
    url = "https://fcsapi.com/api-v3/forex/economic_calendar"
    params = {"access_key": FCS_API_KEY, "limit": limit, "importance": os.getenv("FCS_IMPORTANCE", "2,3")}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("response") or r.json().get("data") or []
        for ev in data:
            name = ev.get("event") or ev.get("title") or ""
            currency = ev.get("currency") or ""
            impact = str(ev.get("impact") or ev.get("importance") or "")
            time = ev.get("date") or ev.get("time") or ""
            if FILTER_CURRENCIES and currency.upper() not in FILTER_CURRENCIES: continue
            if FILTER_IMPORTANCES:
                wanted = set([s.strip() for s in FILTER_IMPORTANCES.split(",") if s.strip()])
                if impact not in wanted: continue
            bg = safe_translate_to_bg(name)
            events.append({"time": time, "currency": currency, "impact": impact, "name": name, "bg": bg})
    except Exception as e:
        print(f"⚠️ FCS API error: {e}")
    return events

def generate_analysis(events: List[Dict]) -> str:
    """Create summarized analysis by currency and impact"""
    if not events: return "📢 Днес няма важни новини."
    summary = {}
    for ev in events:
        cur = ev["currency"] or "Unknown"
        if cur not in summary: summary[cur] = {"High":0,"Medium":0,"Low":0,"events":[]}
        imp = ev["impact"]
        key = "High" if imp=="3" else "Medium" if imp=="2" else "Low"
        summary[cur][key] += 1
        summary[cur]["events"].append(ev)
    # Prepare text
    analysis_lines = ["📊 Дневен Forex анализ:\n"]
    for cur, info in summary.items():
        line = f"💰 {cur}: High={info['High']}, Medium={info['Medium']}, Low={info['Low']}"
        analysis_lines.append(line)
    analysis_lines.append("\n📰 Подробни новини:")
    for cur, info in summary.items():
        for ev in info["events"]:
            analysis_lines.append(f"{ev['time']} | {cur} | Impact:{ev['impact']} | {ev['name']} ({ev['bg']})")
    return "\n".join(analysis_lines)

# ------------------- Discord posting -------------------
async def send_long_message(channel, message: str):
    for part in split_message(message):
        try:
            await channel.send(part)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"❌ Failed to send message: {e}")

async def send_news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print(f"❌ Channel not found: {DISCORD_CHANNEL_ID}")
        return
    tz = pytz.timezone(TIMEZONE)
    while not client.is_closed():
        now = datetime.now(tz)
        target = tz.localize(datetime(now.year, now.month, now.day, POST_HOUR, POST_MINUTE))
        if now > target: target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            print("📰 Fetching news...")
            events = get_forex_news()
            analysis = generate_analysis(events)
            await send_long_message(channel, analysis)
            print("✅ News posted.")
        except Exception as e:
            print(f"❌ Error posting news: {e}")
            try: await channel.send("❌ Bot error while fetching or posting news.")
            except: pass
        await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"✅ Bot started as {client.user}")
    client.loop.create_task(send_news_loop())

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
