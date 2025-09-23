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
POST_HOUR = int(os.getenv("POST_HOUR", "7"))       # час на публикуване (24h)
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))   # минута
TIMEZONE = os.getenv("TIMEZONE", "Europe/Sofia")  # timezone

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
FCS_API_KEY = os.getenv("FCS_API_KEY")  # FCS API key

FILTER_IMPORTANCES = os.getenv("FILTER_IMPORTANCES", "2,3")  # High + Medium
FILTER_CURRENCIES = set()  # празно = всички валути

if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN not set.")
    exit(1)
if not DISCORD_CHANNEL_ID:
    print("❌ DISCORD_CHANNEL_ID not set.")
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
# Flask app for health checks
# -------------------
app = Flask(__name__)
@app.route("/")
de
