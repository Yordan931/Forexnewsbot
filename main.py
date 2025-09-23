# main.py
import os
import requests
import discord
import asyncio
import pytz
from datetime import datetime, timedelta
from flask import Flask
import threading
import html
from typing import List

# -------------------
# SETTINGS (можеш да променяш и чрез ENV vars)
# -------------------
POST_HOUR = int(os.getenv("POST_HOUR", "7"))       # час на публикуване (24h)
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))   # минута
TIMEZONE = os.getenv("TIMEZONE", "Europe/Sofia")  # timezone

# API keys / tokens (трябва да ги сложиш в Render → Environment)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
FCS_API_KEY = os.getenv("FCS_API_KEY")  # https://fcsapi.com/ key (препоръчително)

# Филтри: impact (comma-separated, напр. "3,2"), currencies (CSV напр "USD,EUR")
FILTER_IMPORTANCES = os.getenv("FILTER_IMPORTANCES", "")  # "3,2" -> 3=High,2=Medium
FILTER_CURRENCIES = set([c.strip().upper() for c in os.getenv("FILTER_CURRENCIES", "").split(",") if c.strip()])

# безопасни проверки
if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN not set. Set it in Environment Variables.")
    exit(1)
if not DISCORD_CHANNEL_ID:
    print("❌ DISCORD_CHANNEL_ID not set. Set it in Environment Variables.")
    exit(1)

try:
    # allow passing channel id as URL or raw id
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
# Flask app for Render (health)
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
def split_message(text: str, max_len: int = 1900) -> List[str]:
    """Split long text into chunks safe for Discord (close to newline boundaries)."""
    if len(text) <= max_len:
        return [text]
    parts = []
    lines = text.splitlines()
    cur = ""
    for line in lines:
        candidate = (cur + "\n" + line) if cur else line
        if len(candidate) > max_len:
            if cur:
                parts.append(cur)
                cur = line
            else:
                # a single line longer than max_len -> hard split
                for i in range(0, len(line), max_len):
                    parts.append(line[i:i+max_len])
                cur = ""
        else:
            cur = candidate
    if cur:
        parts.append(cur)
    return parts

def safe_translate_to_bg(text: str) -> str:
    """Translate EN -> BG using public translate endpoint (no external lib)."""
    try:
        # Google translate public endpoint (undocumented but commonly used)
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "en",
            "tl": "bg",
            "dt": "t",
            "q": text
        }
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        # data[0][0][0] usually contains the translated text
        return data[0][0][0] if data and isinstance(data, list) and data[0] else text
    except Exception:
        return text

# -------------------
# Data fetch: primary = FCS API, fallback = scraping investing.com (best-effort)
# -------------------
def get_forex_news_from_fcs(limit: int = 15) -> List[str]:
    """Use FCS API (recommended). Returns list of formatted event lines."""
    if not FCS_API_KEY:
        raise RuntimeError("FCS API key not provided.")
    url = "https://fcsapi.com/api-v3/forex/economic_calendar"
    params = {
        "access_key": FCS_API_KEY,
        "limit": limit,
        "importance": os.getenv("FCS_IMPORTANCE", "2,3")  # default medium+high
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("response") or data.get("data") or []
        events = []
        for ev in items:
            # different keys possible depending on plan; use safe get
            name = ev.get("event") or ev.get("title") or ev.get("name") or str(ev)
            currency = ev.get("currency") or ev.get("country") or ""
            impact = ev.get("impact") or ev.get("importance") or ""
            time = ev.get("date") or ev.get("time") or ev.get("event_date") or ""
            # filters
            if FILTER_CURRENCIES and currency and currency.upper() not in FILTER_CURRENCIES:
                continue
            if FILTER_IMPORTANCES:
                wanted = set([s.strip() for s in FILTER_IMPORTANCES.split(",") if s.strip()])
                if impact and str(impact) not in wanted and str(ev.get("importance", "")) not in wanted:
                    continue
            # translation
            bg = safe_translate_to_bg(name)
            event_text = f"{time} | {currency} | Impact:{impact} | {name} ({bg})"
            events.append(event_text)
            if len(events) >= limit:
                break
        return events
    except Exception as e:
        # bubble up so caller can fallback
        raise

def get_forex_news_fallback(limit: int = 10) -> List[str]:
    """Simple fallback scraping from investing.com (best-effort)."""
    try:
        url = "https://www.investing.com/economic-calendar/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select('tr[data-event-id]')
        events = []
        for row in rows[:limit]:
            # investing uses classes like "event"
            event_cell = row.find("td", class_="event")
            time_cell = row.find("td", class_="time")
            currency_cell = row.find("td", class_="currency")
            impact_cell = row.find("td", class_="impact")
            name = event_cell.get_text(strip=True) if event_cell else ""
            time = time_cell.get_text(strip=True) if time_cell else ""
            currency = currency_cell.get_text(strip=True) if currency_cell else ""
            impact = impact_cell.get_text(strip=True) if impact_cell else ""
            if FILTER_CURRENCIES and currency and currency.upper() not in FILTER_CURRENCIES:
                continue
            bg = safe_translate_to_bg(name) if name else ""
            events.append(f"{time} | {currency} | Impact:{impact} | {name} ({bg})")
        return events
    except Exception as e:
        # final fallback: empty
        return []

def get_forex_news(limit: int = 15) -> str:
    """Unified getter: try FCS API, else fallback scraper, else friendly message."""
    try:
        events = []
        # try primary (FCS) first
        try:
            events = get_forex_news_from_fcs(limit=limit)
        except Exception as e:
            print(f"⚠️ FCS API failed: {e} — trying fallback scraper")
            events = get_forex_news_fallback(limit=limit)
        if not events:
            return "📢 Няма намерени важни икономически събития (или източникът е празен)."
        # prepare readable block
        header = "📅 Important economic events:\n\n"
        body = "\n".join(events)
        footer = "\n\n⚠️ Data source: FCS API / Investing (fallback)."
        return header + body + footer
    except Exception as e:
        print(f"❌ Unexpected error in get_forex_news: {e}")
        return "❌ An error occurred while fetching news."

# -------------------
# Discord sending
# -------------------
async def send_long_message(channel, message: str):
    parts = split_message(message, max_len=1900)
    for i, part in enumerate(parts):
        try:
            await channel.send(part)
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"❌ Failed to send message part: {e}")

async def send_news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print(f"❌ Channel {DISCORD_CHANNEL_ID} not found. Check the ID and bot permissions.")
        return

    tz = pytz.timezone(TIMEZONE)
    while not client.is_closed():
        now = datetime.now(tz)
        target = tz.localize(datetime(now.year, now.month, now.day, POST_HOUR, POST_MINUTE))
        if now > target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        print(f"⏰ Next post in {wait_seconds/60:.1f} minutes ({target.isoformat()})")
        # wait until target
        await asyncio.sleep(wait_seconds)
        try:
            print("📰 Fetching news...")
            news = get_forex_news()
            await send_long_message(channel, f"📢 Forex news:\n\n{news}")
            print("✅ News posted.")
        except Exception as e:
            print(f"❌ Error while posting news: {e}")
            try:
                await channel.send("❌ Bot error while fetching or posting news.")
            except:
                pass
        # small sleep to avoid immediate rerun
        await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"✅ Bot started as {client.user} - connected to {len(client.guilds)} guilds")
    # start the daily loop
    client.loop.create_task(send_news_loop())

if __name__ == "__main__":
    # Run the bot (discord.Client.run blocks)
    client.run(DISCORD_TOKEN)
