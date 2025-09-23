# main.py
import os
import requests
import discord
import asyncio
import pytz
from datetime import datetime, timedelta
from flask import Flask
import threading
from typing import List

# -------------------
# SETTINGS
# -------------------
POST_HOUR = int(os.getenv("POST_HOUR", "7"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Sofia")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
FCS_API_KEY = os.getenv("FCS_API_KEY")

FILTER_IMPORTANCES = os.getenv("FILTER_IMPORTANCES", "2,3")  # 3=High,2=Medium
FILTER_CURRENCIES = set([c.strip().upper() for c in os.getenv("FILTER_CURRENCIES", "").split(",") if c.strip()])

if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
    print("❌ DISCORD_TOKEN or DISCORD_CHANNEL_ID not set")
    exit(1)

try:
    ch = DISCORD_CHANNEL_ID.strip()
    if ch.startswith("https://discord.com/channels/"):
        DISCORD_CHANNEL_ID = int(ch.split("/")[-1])
    else:
        DISCORD_CHANNEL_ID = int(ch)
except Exception as e:
    print(f"❌ Invalid DISCORD_CHANNEL_ID: {e}")
    exit(1)

# -------------------
# Discord client
# -------------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# -------------------
# Flask for health check
# -------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "ForexNewsBot: alive"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# -------------------
# Helpers
# -------------------
def safe_translate_to_bg(text: str) -> str:
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client":"gtx","sl":"en","tl":"bg","dt":"t","q":text}
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        return data[0][0][0] if data else text
    except:
        return text

def split_message(text: str, max_len: int = 1900) -> List[str]:
    if len(text) <= max_len:
        return [text]
    parts, cur = [], ""
    for line in text.splitlines():
        candidate = (cur + "\n" + line) if cur else line
        if len(candidate) > max_len:
            if cur: parts.append(cur); cur=line
            else:
                for i in range(0,len(line),max_len): parts.append(line[i:i+max_len])
                cur=""
        else: cur=candidate
    if cur: parts.append(cur)
    return parts

def generate_event_analysis(event: dict) -> str:
    currency = event.get("currency","")
    impact = str(event.get("impact") or event.get("importance") or "")
    name = event.get("event") or event.get("title") or event.get("name") or ""
    name_bg = safe_translate_to_bg(name)
    time = event.get("time") or event.get("date") or "00:00"

    # Експертен анализ
    if impact=="3":
        analysis=f"⚡ Очаква се силна волатилност за {currency}"
    elif impact=="2":
        analysis=f"🔹 Възможни умерени движения за {currency}"
    else:
        analysis="🔸 Нисък импакт"
    
    return f"{time} | {currency} | Impact:{impact} | {name} ({name_bg})\n{analysis}"

# -------------------
# Fetch Forex news
# -------------------
def get_forex_news(limit:int=50) -> str:
    try:
        if not FCS_API_KEY:
            return "❌ FCS API key missing."
        url="https://fcsapi.com/api-v3/forex/economy_cal"
        params={"access_key":FCS_API_KEY,"limit":limit,"importance":FILTER_IMPORTANCES}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("response") or []
        events=[]
        for ev in data:
            currency = ev.get("currency","")
            impact = str(ev.get("impact") or ev.get("importance") or "")
            if FILTER_CURRENCIES and currency.upper() not in FILTER_CURRENCIES: continue
            if impact not in FILTER_IMPORTANCES.split(","): continue
            events.append(generate_event_analysis(ev))
            if len(events)>=limit: break
        if not events: return "📢 Днес няма важни новини."
        header="📅 24-часов календар на икономически събития:\n\n"
        body="\n".join(events)
        footer="\n\n⚠️ Източник: FCS API"
        return header+body+footer
    except Exception as e:
        print(f"❌ Error fetching news: {e}")
        return "❌ An error occurred while fetching news."

# -------------------
# Discord sending
# -------------------
async def send_long_message(channel, message: str):
    for part in split_message(message):
        try:
            await channel.send(part)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"❌ Failed to send part: {e}")

async def send_news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print(f"❌ Channel {DISCORD_CHANNEL_ID} not found")
        return
    tz = pytz.timezone(TIMEZONE)
    while not client.is_closed():
        now = datetime.now(tz)
        target = tz.localize(datetime(now.year, now.month, now.day, POST_HOUR, POST_MINUTE))
        if now > target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        print(f"⏰ Следващото публикуване след {wait_seconds/60:.1f} мин ({target.isoformat()})")
        await asyncio.sleep(wait_seconds)
        try:
            print("📰 Взимане на новини...")
            news = get_forex_news()
            await send_long_message(channel, f"📢 Forex news:\n\n{news}")
            print("✅ Новините са публикувани.")
        except Exception as e:
            print(f"❌ Грешка при публикуване: {e}")
            try: await channel.send("❌ Грешка при взимане/публикуване на новини.")
            except: pass
        # Автоматично планиране за следващия ден
        await asyncio.sleep(1)

@client.event
async def on_ready():
    print(f"✅ Ботът е стартиран като {client.user}")
    client.loop.create_task(send_news_loop())

if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
