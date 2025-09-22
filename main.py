import os
import discord
import requests
from bs4 import BeautifulSoup
from googletrans import Translator
import asyncio
import pytz
from datetime import datetime, timedelta
from flask import Flask
import threading

# -------------------
# 🔧 SETTINGS
# -------------------
POST_HOUR = 16
POST_MINUTE = 25
TIMEZONE = "Europe/Sofia"

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")

if not TOKEN or not CHANNEL_ID:
    print("❌ DISCORD_TOKEN or DISCORD_CHANNEL_ID not set!")
    exit(1)

try:
    CHANNEL_ID = CHANNEL_ID.strip()
    if CHANNEL_ID.startswith("https://discord.com/channels/"):
        parts = CHANNEL_ID.split("/")
        CHANNEL_ID = int(parts[-1])
    else:
        CHANNEL_ID = int(CHANNEL_ID)
except Exception as e:
    print(f"❌ Invalid Channel ID: {e}")
    exit(1)

# -------------------
# Discord client
# -------------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
translator = Translator()

# -------------------
# Flask app (keeps service alive on Render)
# -------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# -------------------
# Forex news logic
# -------------------
def get_forex_news():
    try:
        url = "https://example.com"  # сложи реалния URL
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.find_all("tr", class_="calendar__row")
        events = []

        for row in rows:
            event_cell = row.find("td", class_="calendar__event")
            if event_cell and event_cell.text.strip():
                event_name = event_cell.text.strip()
                try:
                    event_bg = translator.translate(event_name, src="en", dest="bg").text
                except:
                    event_bg = event_name
                events.append(f"{event_name} ({event_bg})")

        return "\n".join(events) if events else "❌ No news found."

    except Exception as e:
        print(f"❌ Error fetching news: {e}")
        return "❌ An error occurred."

async def send_news():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print(f"❌ Channel with ID {CHANNEL_ID} not found.")
        return

    tz = pytz.timezone(TIMEZONE)
    while not client.is_closed():
        now = datetime.now(tz)
        target_time = tz.localize(datetime(now.year, now.month, now.day,
                                           POST_HOUR, POST_MINUTE))
        if now > target_time:
            target_time += timedelta(days=1)
        wait_time = (target_time - now).total_seconds()
        await asyncio.sleep(wait_time)
        news = get_forex_news()
        await channel.send(f"📢 Forex news:\n\n{news}")
        await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"✅ Bot started as {client.user}")
    asyncio.create_task(send_news())

# -------------------
# Запуск на Render
# -------------------
async def main():
    await client.start(TOKEN)

asyncio.run(main())
