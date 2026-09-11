
import os
import base64
import sys
import sqlite3
import logging
import traceback
import asyncio
import json
import re
import time
import requests
import random
import uuid
import threading
import qrcode
from datetime import datetime, timedelta
from urllib.parse import quote

# ======================================================
# مدیریت منطقه زمانی (بدون pytz) - کاملاً سازگار با Python 3.13
# ======================================================
try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")
    TZ_AVAILABLE = True
except ImportError:
    TZ_AVAILABLE = False
    class _FallbackTZ:
        def __init__(self):
            self.offset = timedelta(hours=3, minutes=30)
        def utcoffset(self, dt):
            return self.offset
        def dst(self, dt):
            return timedelta(0)
        def tzname(self, dt):
            return "Asia/Tehran"
        def fromutc(self, dt):
            return dt + self.offset
    TEHRAN_TZ = _FallbackTZ()

def get_now():
    if TZ_AVAILABLE:
        return datetime.now(TEHRAN_TZ)
    else:
        return datetime.utcnow() + timedelta(hours=3, minutes=30)

# ======================================================
# پچ کردن jdatetime و hijridate برای کار با zoneinfo
# ======================================================
class _FakePytz:
    class timezone:
        def __init__(self, name):
            self.name = name
        def localize(self, dt):
            return dt
        def normalize(self, dt):
            return dt
        def utcoffset(self, dt):
            return timedelta(hours=3, minutes=30)
        def tzname(self, dt):
            return "Asia/Tehran"
    
    @staticmethod
    def timezone(name):
        return _FakePytz.timezone(name)

if 'pytz' not in sys.modules:
    import types
    sys.modules['pytz'] = types.ModuleType('pytz')
    sys.modules['pytz'].timezone = _FakePytz.timezone

import jdatetime
from hijridate import Gregorian
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InlineQueryResultCachedPhoto, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler
from telegram.request import HTTPXRequest
from telethon import TelegramClient, events, types
from telethon.tl.types import PeerUser, PeerChannel, PeerChat, MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage, ReactionEmoji, MessageEntityBold, MessageEntityUnderline, MessageEntityStrike, MessageEntityBlockquote, MessageEntitySpoiler, MessageEntityItalic, MessageEntityCode, MessageEntityPre, InputMediaDice
from telethon.tl.functions.messages import SendReactionRequest, DeleteMessagesRequest, SetTypingRequest, ToggleDialogPinRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateStatusRequest, GetAuthorizationsRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.errors import FloodWaitError, SessionPasswordNeededError, ChatWriteForbiddenError
from telethon.tl.functions.channels import GetParticipantsRequest, CreateChannelRequest, EditPhotoRequest
from telethon.tl.types import ChannelParticipantsAdmins, InputPeerEmpty
import psutil
from platform import python_version, uname
from currency_converter import CurrencyConverter
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import urllib.parse

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "VROOM",
        "version": "4.9.6"
    })

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@flask_app.route('/ping')
def ping():
    return jsonify({"status": "alive", "message": "Bot is awake"}), 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 وب سرور روی پورت {port} در حال اجراست")
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

os.environ['TZ'] = 'Asia/Tehran'
try:
    time.tzset()
except:
    pass

GOOGLE_SEARCH_API_KEY = "AIzaSyCMYOU0NpU5xfu7GrffyywVUugd1yD2uDU"
GOOGLE_CSE_ID = "3185e48756dfd482f"
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

GEMINI_KEY = "AIzaSyBhlSytH4Zfe-ww1D8HsrgJfCf5TRY1SLc"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
PAXSENIX_API_KEY = "sk-paxsenix-Xo_BAFNGgWVZ_ymWd02Rk1JHbyoDSEzfPhiolJ3F12cY6XZG"
PAXSENIX_API_URL = "https://api.paxsenix.org/v1/chat/completions"
DEEPSEEK_FREE_URL = "https://deepseek.api-sina-free.workers.dev/?text="

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_CONFIGS = [
    {"api_id": 22409632, "api_hash": "b74c1ee200ad9ced6315859e9bd4125a"},
    {"api_id": 28297221, "api_hash": "8d682eb5c41a9762ef73f9ebe06c4eff"},
    {"api_id": 28039994, "api_hash": "00877cdcd706564a4de6abf7f7d64349"},
    {"api_id": 29031463, "api_hash": "64f122a7094dbab7e32b911eae6589e9"},
    {"api_id": 12832882, "api_hash": "1953c708cb3c47ecba74dc618b209e22"},
    {"api_id": 26645489, "api_hash": "6a212d0a400c97264600b3f932de5c2f"},
]

def get_user_api(user_id):
    conn = sqlite3.connect('main_database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT api_id, api_hash FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] is not None and row[1] is not None:
        conn.close()
        return {"api_id": row[0], "api_hash": row[1]}
    
    api_count = {}
    for api in API_CONFIGS:
        cursor.execute('SELECT COUNT(*) FROM users WHERE api_id = ?', (api["api_id"],))
        api_count[api["api_id"]] = cursor.fetchone()[0]
    
    best_api = min(API_CONFIGS, key=lambda x: api_count.get(x["api_id"], 0))
    
    cursor.execute('UPDATE users SET api_id = ?, api_hash = ? WHERE user_id = ?', 
                   (best_api["api_id"], best_api["api_hash"], user_id))
    conn.commit()
    conn.close()
    
    logger.info(f"API اختصاص یافته به کاربر {user_id}: {best_api['api_id']}")
    return best_api

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده! توی Railway برو Variables و مقدار BOT_TOKEN رو با توکن جدیدت ست کن.")
ADMIN_ID = 6443963679
ADMIN_IDS = {6443963679, 8671606468}

def is_admin(uid) -> bool:
    try:
        return int(uid) in ADMIN_IDS
    except Exception:
        return False

def find_session_file(user_id) -> str:
    """پیدا کردن مسیر سشن کاربر از دیتابیس یا پوشه user_sessions."""
    uid = str(user_id)
    try:
        ud = db.get_user(uid) or {}
        sf = ud.get('session_file')
        if sf:
            sf = str(sf)
            if os.path.exists(sf):
                return sf
            # اگر بدون پسوند .session ذخیره شده
            if os.path.exists(sf + '.session'):
                return sf
            base = os.path.basename(sf)
            alt = os.path.join(SESSIONS_FOLDER, base)
            if os.path.exists(alt):
                return alt
            if os.path.exists(alt + '.session'):
                return alt
    except Exception:
        pass
    try:
        if not os.path.isdir(SESSIONS_FOLDER):
            return None
        for name in os.listdir(SESSIONS_FOLDER):
            if uid not in name:
                continue
            full = os.path.join(SESSIONS_FOLDER, name)
            if name.endswith('.session'):
                return full[:-8] if full.endswith('.session') else full
            if os.path.isfile(full) and not name.endswith('-journal'):
                return full
            # پوشه/فایل بدون پسوند — تلthon session path بدون .session
            if not name.endswith('.session-journal'):
                cand = os.path.join(SESSIONS_FOLDER, name.replace('.session', ''))
                if os.path.exists(cand + '.session') or os.path.exists(cand):
                    return cand if not cand.endswith('.session') else cand[:-8]
    except Exception:
        pass
    return None

BOT_USERNAME = "Gap_5_bot"
MUSIC_BOT = "Gap_4_bot"

SESSIONS_FOLDER = 'user_sessions'
if not os.path.exists(SESSIONS_FOLDER):
    os.makedirs(SESSIONS_FOLDER)

GROUP_ID = -1002817019483


# ========== ماژول ارزها (Swap API + Fragment Peg) ==========
SWAP_API_URL = "https://swapwallet.app/api/v1/market/prices"
SWAP_API_KEY = "apikey-h8T5ufE73fILlDudXnPJp6CRYV9PSMKviBB0SxCXCAOzSFneGcBHaUa19am2kTIU"
_CRYPTO_CACHE = {"ts": 0.0, "data": None}

async def fetch_crypto_prices():
    import time as _t
    now = _t.time()
    if _CRYPTO_CACHE["data"] and now - _CRYPTO_CACHE["ts"] < 15:
        return _CRYPTO_CACHE["data"]
    try:
        import aiohttp
        headers = {"x-api-key": SWAP_API_KEY, "Accept": "application/json"}
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SWAP_API_URL, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("result") if isinstance(data, dict) and "result" in data else data
                    _CRYPTO_CACHE["data"] = result
                    _CRYPTO_CACHE["ts"] = now
                    return result
    except Exception as e:
        logger.error(f"crypto prices: {e}")
    return _CRYPTO_CACHE.get("data")

def _fmt_price(value):
    try:
        v = float(str(value).replace(",", "").strip())
        if v >= 1000:
            return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"
        if v >= 1:
            return f"{v:,.3f}"
        if v >= 0.0001:
            return f"{v:.6f}"
        return f"{v:.8f}"
    except Exception:
        return str(value)


async def render_crypto_chart_image(title: str, lines: list) -> str:
    """کارت تصویری نرخ ارز — شبیه خروجی ربات ارز"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import tempfile, time as _t
        W, H = 900, max(420, 120 + len(lines) * 52)
        img = Image.new('RGB', (W, H), (8, 12, 28))
        draw = ImageDraw.Draw(img)
        # cyberpunk grid
        for x in range(0, W, 40):
            draw.line([(x, 0), (x, H)], fill=(20, 40, 70), width=1)
        for y in range(0, H, 40):
            draw.line([(0, y), (W, y)], fill=(20, 40, 70), width=1)
        # frame
        draw.rectangle([8, 8, W-9, H-9], outline=(0, 220, 255), width=3)
        draw.rectangle([16, 16, W-17, H-17], outline=(120, 40, 255), width=1)
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        font_title = font_body = ImageFont.load_default()
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font_title = ImageFont.truetype(fp, 36)
                    font_body = ImageFont.truetype(fp, 24)
                    break
                except Exception:
                    pass
        draw.text((40, 28), title[:60], fill=(0, 255, 220), font=font_title)
        y = 90
        colors = [(0, 255, 180), (255, 200, 80), (120, 200, 255), (255, 120, 200)]
        for i, line in enumerate(lines[:18]):
            c = colors[i % len(colors)]
            draw.ellipse([36, y+6, 52, y+22], fill=c)
            draw.text((66, y), str(line)[:70], fill=(230, 240, 255), font=font_body)
            y += 48
        out = os.path.join(tempfile.gettempdir(), f"crypto_card_{int(_t.time()*1000)}.png")
        img.save(out, 'PNG')
        return out
    except Exception as e:
        logger.error(f"crypto chart: {e}")
        return None



PERSIAN_COIN_MAP = {
    "بیتکوین": "BTC", "بیت کوین": "BTC", "بیت": "BTC",
    "اتریوم": "ETH", "اتر": "ETH", "اتریم": "ETH",
    "تتر": "USDT", "دلار": "USDT",
    "سولانا": "SOL", "سول": "SOL",
    "تون": "TON", "تون کوین": "TON",
    "ترون": "TRX", "ریپل": "XRP", "بایننس": "BNB", "بی ان بی": "BNB",
    "دوج": "DOGE", "دوجکوین": "DOGE", "شیبا": "SHIB", "نات": "NOT",
    "کاردانو": "ADA", "آدا": "ADA", "پپه": "PEPE", "آواکس": "AVAX",
    "لینک": "LINK", "چین لینک": "LINK",
}

async def compose_cyberpunk_coin_card(symbol: str, usd_price: float, irt_price: float, change_pct: float = None) -> str:
    """کارت چارت سایبرپانک شبیه ربات ارز — خروجی مسیر فایل PNG"""
    import io, tempfile, time as _t, random
    try:
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        from matplotlib.gridspec import GridSpec
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        logger.error(f"chart deps: {e}")
        return None
    try:
        if change_pct is None:
            change_pct = random.uniform(-8.5, 12.5)
        is_bull = change_pct >= 0
        # OHLCV synthetic
        periods = 80
        price = max(float(usd_price), 1e-8)
        sigma = max(abs(change_pct) / 100.0, 0.015)
        closes = np.zeros(periods)
        closes[-1] = price
        for i in range(periods - 2, -1, -1):
            closes[i] = closes[i+1] / np.exp(np.random.normal(0, sigma * 0.3))
        opens = np.roll(closes, 1); opens[0] = closes[0]
        highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, sigma * 0.2, periods)))
        lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, sigma * 0.2, periods)))
        volumes = 1000 + np.random.uniform(500, 4000, periods)

        THEME = {
            'bg': '#0D111A', 'up': '#00F0FF', 'down': '#FF003C',
            'grid': '#1A2133', 'muted': '#64748B', 'ema9': '#FFD700', 'ema21': '#B026FF',
        }
        fig = plt.figure(figsize=(9, 5.2), dpi=120, facecolor=THEME['bg'])
        gs = GridSpec(2, 1, figure=fig, height_ratios=[3.2, 0.9], hspace=0.08)
        ax = fig.add_subplot(gs[0, 0]); ax.set_facecolor(THEME['bg'])
        ax.grid(True, color=THEME['grid'], linestyle='--', linewidth=0.5)
        x = np.arange(periods)
        colors = [THEME['up'] if closes[i] >= opens[i] else THEME['down'] for i in range(periods)]
        ax.vlines(x, lows, highs, color=colors, linewidth=1.0)
        for i in range(periods):
            h = max(abs(closes[i] - opens[i]), closes[i] * 1e-6)
            ax.add_patch(patches.Rectangle((x[i]-0.35, min(opens[i], closes[i])), 0.7, h, facecolor=colors[i], edgecolor=colors[i]))
        # EMA
        def ema(arr, p):
            a = 2/(p+1); out = np.zeros_like(arr); out[0]=arr[0]
            for i in range(1, len(arr)): out[i] = a*arr[i] + (1-a)*out[i-1]
            return out
        ax.plot(x, ema(closes, 9), color=THEME['ema9'], lw=1.2, alpha=0.85)
        ax.plot(x, ema(closes, 21), color=THEME['ema21'], lw=1.2, alpha=0.85)
        ax.tick_params(colors=THEME['muted'], labelbottom=False); ax.yaxis.tick_right()
        for sp in ax.spines.values(): sp.set_color(THEME['grid'])
        axv = fig.add_subplot(gs[1, 0], sharex=ax); axv.set_facecolor(THEME['bg'])
        axv.bar(x, volumes, color=colors, alpha=0.65)
        axv.tick_params(colors=THEME['muted'], labelbottom=False); axv.yaxis.tick_right()
        for sp in axv.spines.values(): sp.set_color(THEME['grid'])
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=THEME['bg'], bbox_inches='tight', pad_inches=0.05)
        plt.close(fig)
        buf.seek(0)
        chart = Image.open(buf).convert('RGBA')
        # Card compose
        card_w, card_h = 1080, 780
        bg = Image.new('RGBA', (card_w, card_h), (8, 10, 16, 255))
        draw = ImageDraw.Draw(bg)
        accent = (0, 240, 255) if is_bull else (255, 0, 60)
        draw.rectangle([0, 0, card_w, 260], fill=(*accent, 25))
        draw.rounded_rectangle([35, 35, card_w-35, card_h-35], radius=24, outline=(30, 40, 60), width=2)
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        f_xl = f_xxl = f_md = ImageFont.load_default()
        for fp in font_paths:
            if os.path.exists(fp):
                f_xl = ImageFont.truetype(fp, 64)
                f_xxl = ImageFont.truetype(fp, 88)
                f_md = ImageFont.truetype(fp, 28)
                break
        draw.text((80, 55), symbol.upper(), fill=(255, 255, 255), font=f_xl)
        draw.text((80, 140), f"${_fmt_price(usd_price)}", fill=(255, 255, 255), font=f_xxl)
        pct = f"{'+' if is_bull else ''}{change_pct:.2f}%"
        draw.rounded_rectangle([80, 245, 80 + 160, 290], radius=10, fill=(*accent, 50))
        draw.text((95, 252), pct, fill=accent, font=f_md)
        # paste chart
        cw = card_w - 100
        ch = int(chart.height * (cw / chart.width))
        chart = chart.resize((cw, ch), Image.Resampling.LANCZOS)
        bg.paste(chart, (50, card_h - ch - 50), chart)
        out = os.path.join(tempfile.gettempdir(), f"cyber_{symbol}_{int(_t.time()*1000)}.png")
        bg.convert('RGB').save(out, 'PNG', optimize=True)
        return out
    except Exception as e:
        logger.error(f"compose_cyberpunk: {e}")
        return None


async def compile_crypto_rates_text():
    prices = await fetch_crypto_prices()
    if not prices:
        return "❌ ارتباط با API معاملاتی برقرار نشد."
    usdt_irt = float(prices.get("USDT/IRT", 0) or 0)
    coins = ["BTC", "ETH", "TON", "SOL", "BNB", "XRP", "DOGE", "NOT", "PEPE", "ADA", "LINK", "AVAX"]
    lines = ["💎 <b>بازار جهانی:</b>\n"]
    for sym in coins:
        usd = prices.get(f"{sym}/USDT", "0")
        if usd and str(usd) != "0":
            try:
                uf = float(usd)
                irt = uf * usdt_irt
                lines.append(f"💵 <b>{sym}:</b>\n   ▫️ <code>${_fmt_price(uf)}</code>\n   ▫️ <code>{_fmt_price(irt)} تومان</code>")
            except Exception:
                pass
    return "\n".join(lines)

_PREMIUM_USD = {12: 28.99, 6: 15.99, 3: 11.99}
_STARS_USD = {50: 0.75, 100: 1.50, 150: 2.25, 250: 3.75, 500: 7.50, 1000: 15.00, 2500: 37.50}

async def compile_crypto_premium_text():
    prices = await fetch_crypto_prices()
    ton = float((prices or {}).get("TON/USDT", 0) or 0)
    usdt_irt = float((prices or {}).get("USDT/IRT", 0) or 0)
    if ton <= 0:
        return "❌ نرخ TON در دسترس نیست."
    lines = ["💎 <b>نرخ تلگرام پریمیوم (فرگمنت):</b>\n"]
    for m in (12, 6, 3):
        usd = _PREMIUM_USD[m]
        ton_need = round(usd / ton, 2)
        irt = usd * usdt_irt
        disc = -52 if m == 12 else (-47 if m == 6 else -20)
        lines.append(
            f"💵 <b>اشتراک {m} ماهه ({disc}%):</b>\n"
            f"  ▫️ فرگمنت: <code>{ton_need} TON</code>\n"
            f"  ▫️ دلار: <code>${_fmt_price(usd)}</code>\n"
            f"  ▫️ تومان: <code>{_fmt_price(irt)} تومان</code>"
        )
    return "\n\n".join(lines)

async def compile_crypto_stars_text():
    prices = await fetch_crypto_prices()
    ton = float((prices or {}).get("TON/USDT", 0) or 0)
    usdt_irt = float((prices or {}).get("USDT/IRT", 0) or 0)
    if ton <= 0:
        return "❌ نرخ TON در دسترس نیست."
    lines = ["⭐ <b>نرخ استارز (Stars):</b>\n"]
    for pack in (50, 100, 150, 250, 500, 1000, 2500):
        usd = _STARS_USD[pack]
        ton_need = round(usd / ton, 2)
        irt = usd * usdt_irt
        lines.append(
            f"💵 <b>بسته {pack}:</b>\n"
            f"  ▫️ فرگمنت: <code>{ton_need} TON</code>\n"
            f"  ▫️ دلار: <code>${_fmt_price(usd)}</code>\n"
            f"  ▫️ تومان: <code>{_fmt_price(irt)} تومان</code>"
        )
    return "\n\n".join(lines)


MEDIA_FOLDER = 'media_storage'
if not os.path.exists(MEDIA_FOLDER):
    os.makedirs(MEDIA_FOLDER)

REPORT_CONFIG_FILE = "report_config.json"
REPORT_MEDIA_FOLDER = 'reported_media'
if not os.path.exists(REPORT_MEDIA_FOLDER):
    os.makedirs(REPORT_MEDIA_FOLDER)

ALLOWED_EMOJIS = [
    "🤯", "🐳", "😍", "💩", "👏", "🍌", "🤓", "😢", "🙉", "🤩",
    "🤝", "👀", "🌚", "🗿", "🤡", "😐", "👨‍💻", "😭", "🙈", "❤",
    "🙏", "😴", "💋", "🥰", "🤪", "✍️", "🥱", "👻", "🤣", "🌭",
    "😨", "🍓", "🔥", "🖕", "🤗", "🤔", "🤬", "😁", "🎄", "🫡",
    "⚡", "🥴", "😈", "🏆", "😇", "🎃", "☃️", "🤮", "👍", "👎",
    "😱", "😖", "🕊", "💯", "💔", "🤨", "❤️‍🔥", "💘", "😘", "💊",
    "🆒", "🤷‍♂", "🤷‍♀", "🎅"
]

def full_chat_id_to_short(full_id):
    if full_id is None:
        return None
    try:
        full_id = int(full_id)
    except (TypeError, ValueError):
        return None
    abs_id = abs(full_id)
    if abs_id > 10**12:
        return abs_id - 10**12
    return abs_id

classic_fonts = [
    "0123456789",
    "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
    "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
    "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
    "⁰¹²³⁴⁵⁶⁷⁸⁹",
    "₀₁₂₃₄₅₆₇₈₉",
    "⓪①②③④⑤⑥⑦⑧⑨",
    "⓿❶❷❸❹❺❻❼❽❾",
    "➀➁➂➃➄➅➆➇➈➉",
    "１２３４５６７８９０",
    "⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽",
    "⒈⒉⒊⒋⒌⒍⒎⒏⒐⒑",
    "一二三四五六七八九〇",
    "๑๒๓๔๕๖๗๘๙๐",
    "০১২৩৪৫৬৭৮৯",
    "੦੧੨੩੪੫੬੭੮੯",
    "૦૧૨૩૪૫૬૭૮૯",
    "〇一二三四五六七八九",
    "🄀➀➁➂➃➄➅➆➇➈",
    "🄋①②③④⑤⑥⑦⑧⑨",
    "🄌❶❷❸❹❺❻❼❽❾",
    "0➀➁➂➃➄➅➆➇➈",
    "0₁2₃4₅6₇8₉",
    "0¹2³4⁵6⁷8⁹",
    "𝟎𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
    "𝟘1𝟚3𝟜5𝟞7𝟠9",
    "0₁2³4₅6⁷8₉",
    "⓪1②3④5⑥7⑧9",
    "0❶2❸4❺6❼8❾",
    "０１２３４５６７８９",
    "⁰₁²₃⁴₅⁶₇⁸₉",
    "0𝟙2𝟛4𝟝6𝟟8𝟡",
    "𝟎1𝟐3𝟒5𝟔7𝟖9",
    "0𝟭2𝟯4𝟱6𝟳8𝟵",
    "𝟶1𝟸3𝟺5𝟼7𝟾9",
    "①2③4⑤6⑦8⑨0",
    "❶2❸4❺6❼8❾0",
    "➊➋➌➍➎➏➐➑➒➓",
    "⓵⓶⓷⓸⓹⓺⓻⓼⓽⓾",
    "➊2➌4➎6➐8➒0",
    "①②③④⑤⑥⑦⑧⑨⓪",
    "𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡𝟘",
    "𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗𝟎",
    "𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵𝟬",
    "𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿𝟶",
    "¹²³⁴⁵⁶⁷⁸⁹⁰",
    "₁₂₃₄₅₆₇₈₉₀",
    "➀➁➂➃➄➅➆➇➈⓪",
    "❶❷❸❹❺❻❼❽❾⓪"
]

flags = [
    "🇮🇷", "🇺🇸", "🇬🇧", "🇩🇪", "🇫🇷", "🇮🇹", "🇪🇸", "🇹🇷", "🇷🇺",
    "🇨🇳", "🇯🇵", "🇰🇷", "🇸🇦", "🇦🇪", "🇶🇦", "🇰🇼", "🇮🇶", "🇸🇾",
    "🇱🇧", "🇯🇴", "🇪🇬", "🇲🇦", "🇩🇿", "🇹🇳", "🇱🇾", "🇸🇩", "🇾🇪",
    "🇴🇲", "🇧🇭", "🇵🇰", "🇦🇫", "🇮🇳", "🇧🇩", "🇧🇷", "🇦🇷", "🇲🇽",
    "🇨🇦", "🇦🇺", "🇳🇿", "🇿🇦", "🇳🇬", "🇰🇪", "🇪🇹", "🇬🇭", "🇺🇬",
    "🇺🇦", "🇵🇱", "🇳🇱", "🇧🇪", "🇸🇪", "🇳🇴", "🇩🇰", "🇫🇮", "🇨🇭",
    "🇦🇹", "🇬🇷", "🇵🇹", "🇮🇪", "🇨🇿", "🇭🇺", "🇷🇴", "🇧🇬", "🇷🇸",
    "🇭🇷", "🇸🇰", "🇸🇮", "🇱🇹", "🇱🇻", "🇪🇪", "🇦🇿", "🇦🇲", "🇬🇪",
    "🇰🇿", "🇺🇿", "🇹🇯", "🇹🇲", "🇰🇬", "🇲🇳", "🇻🇳", "🇹🇭", "🇲🇾",
    "🇸🇬", "🇮🇩", "🇵🇭", "🇲🇲", "🇰🇭", "🇱🇦", "🇳🇵", "🇱🇰", "🇲🇻",
]

SPAM_MESSAGES = [
    "کص ننتو تو فاضلاب ریختن، ماهی‌های کانال سیر شدن",
    "کون پدرت تو گور می‌سوزه، شیاطین تفریحشون شده",
    "کص خواهرت زنگ زده گفت کسش دیگه جا نداره واسه مشتری",
    "کون مادرت تو حموم ولگردا جا خوش کرده، صبح تا شب کس می‌گیرن",
    "کص خالتو چراغ راه کردن، هر رهگذری یه چراغ روشن کنه",
    "کون داییتو سگای ولگرد به گونی کشیدن، کونشو لیسیدن تا صبح",
    "کص ننت تو بازارچه فروشی راه انداخت، تخفیف هفته‌ی کس",
    "کون پدرت تو گور کون می‌ده به جن‌ها، جن‌ها گفتن بوی گند میده",
    "کص خواهرت تو تاکسی اینترنتی تخفیف کس داد، راننده‌ها صف کشیدن",
    "کون مادرت تو مسجد کیر می‌خورد، مؤذن گفت کونیه اذان رو",
    "کص خالتو تو سطل زباله پیدا کردن، سگا گفتن مال ماست",
    "کون دایی تو مجلس عروسی کیر می‌مکید، داماد گفت منم می‌خوام",
    "کص ننت تو پاساژ ویترین شد، مردم با کس بهش نگاه می‌کردن",
    "کون پدرت تو گور کون تکون می‌ده، اموات گفتن بس کن",
    "کص خواهرت تو استخر بچه‌ها کس پخش کرد، آبله کس گرفتن",
    "کون مادرت تو مدرسه شبانه کس فروخت، مدیر مدرسه مشتری ثابت",
    "کص خالتو تو مهمونی پهن کردن، مهمونا گفتن چه عطر کسی",
    "کون دایی تو بیمارستان کیر می‌خورد، پرستارا گفتن کونی بستری",
    "کص ننت تو هواپیما کس باز کرد، مهموندارا کس کشیدن و خلبان غش کرد",
    "کون پدرت تو گور کیر می‌مالید به کفن، کفن کونی شد و پاره شد",
    "کص خواهرت تو قطار کس داد، مسافرا از بوی کس پیاده شدن",
    "کون مادرت تو شهرداری کیر خورد، کارمنداش گفتن کونیه جدید",
    "کص خالتو تو کتابخونه کس می‌مالید، کتابا بوی کس گرفتن",
    "کون دایی تو سینما کیر می‌مکید، تماشاگرا فیلم کس می‌دیدن",
    "کص ننت تو مترو کس فروخت، واگن‌ها پر از بوی کس شد",
    "کون پدرت تو گور کون می‌ساید، قبرستان لرزید و ریخت",
    "کص خواهرت تو هتل کس می‌داد، رزرو هتل تا ابد پر شد",
    "کون مادرت تو ورزشگاه کیر خورد، تماشاگرا کس‌بینی کردن",
    "کص خالتو تو سونا کس پخت، بخار کس شد همه خفه شدن",
    "کون دایی تو رستوران کیر می‌مکید، آشپز گفت سس کونی شده",
    "کص ننت تو تاکسی کس ول کرد، راننده گفت کرایه رو کس می‌دم",
    "کون پدرت تو گور کیر می‌زد به خاک، زمین لرزید و کونش ترکید",
    "کص خواهرت تو باشگاه بدنسازی کس مالید، دمبل‌ها بوی کس گرفتن",
    "کون مادرت تو بیمارستان روانی کیر خورد، بیمارا شفا یافتن اما کونیش شدن",
    "کص خالتو تو دیسکو کس پخش کرد، دی‌جی گفت این آهنگ کس‌خواره",
    "کون دایی تو کافی‌نت کیر می‌مکید، همه سایتا کس شدن",
    "کص ننت تو باغ وحش کس به میمون داد، میمون کس‌خوار شد و فرار کرد",
    "کون پدرت تو گور کون تکون می‌ده، مرده‌ها بیدار شدن و کس کشیدن",
    "کص خواهرت تو استخر شنای کس ریخت، آب کس شد و بچه ماهیا مردن",
    "کون مادرت تو هتل کیر می‌خورد، تخت‌ها کس شدن و مهمونا رفتن",
    "کص خالتو تو هواپیما کس باز کرد، مهموندارا کس کشیدن و هواپیما سقوط کرد",
    "کون دایی تو قطار سریع‌السیر کیر می‌مکید، قطار از سرعت کس واژگون شد",
    "کص ننت تو فروشگاه اینترنتی کس فروخت، مرجوعی کس شد و سایت هک شد",
    "کون پدرت تو گور کیر می‌زد به استخون، مغز کس شد و پوسید",
    "کص خواهرت تو باشگاه رقص کس داد، رقص کس شد و همه رقصیدن",
    "کون مادرت تو مدرسه رانندگی کیر خورد، ماشین کس شد و تصادف کرد",
    "کص خالتو تو پارکینگ کس مالید، ماشینا کس شدن و دزدیدن",
    "کون دایی تو آزمایشگاه کیر می‌مکید، نمونه‌ها کس شدن و آزمایش خراب شد",
    "کص ننت تو مطب دندانپزشکی کس داد، دندان‌ها کس شدن و ریختن",
    "کون پدرت تو گور کیر می‌زد به کفن، پارچه کس شد و پاره شد",
    "کص خواهرت تو فروشگاه حیوانات کس فروخت، حیوونا کس شدن و فرار کردن",
    "کون مادرت تو زمین بازی کیر خورد، وسایل کس شدن و بچه‌ها گریه کردن",
    "کص خالتو تو استودیو ضبط کس پخش شد، آهنگ کس شد و خواننده فرار کرد",
    "کون دایی تو رستوران چینی کیر می‌مکید، چوپستون کس شد و غذا ریخت",
    "کص ننت تو فروشگاه لباس کس مالید، لباسا کس شدن و پوسیدن",
    "کون پدرت تو گور کیر می‌زد به کرم، کرم کس شد و قبر رو خورد",
    "کص خواهرت تو کافه کس داد، قهوه کس شد و مشتریا رفتن",
    "کون مادرت تو کتابخونه کیر خورد، کتابا کس شدن و سوختن",
    "کص خالتو تو فروشگاه اسباب‌بازی کس فروخت، اسباب‌بازی کس شد و بچه‌ها ترسیدن",
    "کون دایی تو سینما کیر می‌مکید، فیلم کس شد و پرده پاره شد",
    "کص ننت تو هاستل کس داد، تخت‌ها کس شدن و مهمونا رفتن",
    "کون پدرت تو گور کون می‌ساید، خاک قبر کس شد و باد بردش",
    "کص خواهرت تو فروشگاه دیجیتال کس فروخت، گوشی کس شد و باتری ترکید",
    "کون مادرت تو باشگاه تنیس کیر خورد، راکت کس شد و توپ نپرید",
    "کص خالتو تو رستوران ایتالیایی کس مالید، پاستا کس شد و مشتریا استفراغ کردن",
    "کون دایی تو اتاق بازی کیر می‌مکید، بازی‌ها کس شدن و کنسول سوخت",
    "کص ننت تو فروشگاه عتیقه کس داد، عتیقه‌ها کس شدن و شکستن",
    "کون پدرت تو گور کیر می‌زد به سنگ قبر، سنگ ترکید و کسش نمایان شد",
    "کص خواهرت تو فروشگاه گل کس فروخت، گل‌ها کس شدن و پژمردن",
    "کون مادرت تو سینمای روباز کیر خورد، پرده کس شد و فیلم پخش نشد",
    "کص خالتو تو فروشگاه لوازم آرایشی کس مالید، لوازم کس شد و پوستا سوخت",
    "کون دایی تو بیمارستان دامپزشکی کیر می‌مکید، حیوونا کس شدن و مردن",
    "کص ننت تو فروشگاه مبلمان کس داد، مبل‌ها کس شدن و ترکیدن",
    "کون پدرت تو گور کیر می‌زد به ریشه، درخت کس داد و خشک شد",
    "کص خواهرت تو فروشگاه کفش کس فروخت، کفشا کس شد و پاها تاول زد",
    "کون مادرت تو رستوران ژاپنی کیر خورد، سوشی کس شد و ماهی‌ها مردن",
    "کص خالتو تو فروشگاه پارچه کس مالید، پارچه کس شد و پاره شد",
    "کون دایی تو فروشگاه موسیقی کیر می‌مکید، سازها کس شد و صدا نداد",
    "کص ننت تو فروشگاه عینک کس داد، عینکا کس شد و دید تاریک شد",
    "کون پدرت تو گور کون تکون می‌ده، زمین لرزید و کسش ترکید",
    "کص خواهرت تو فروشگاه ساعت کس فروخت، ساعتا کس شد و عقربه‌ها چرخیدن",
    "کون مادرت تو فروشگاه جواهرات کیر خورد، جواهرا کس شد و برقش رفت",
    "کص خالتو تو فروشگاه کیف کس مالید، کیفا کس شد و دسته‌هاش پاره شد",
    "کون دایی تو فروشگاه کاغذ کیر می‌مکید، کاغذا کس شد و پوسیدن",
    "کص ننت تو فروشگاه رنگ کس داد، رنگا کس شد و دیوارا ترکیدن",
    "کون پدرت تو گور کیر می‌زد به خاک، خاک کس شد و گند زد",
    "کص خواهرت تو فروشگاه چوب کس فروخت، چوبا کس شد و پوسیدن",
    "کون مادرت تو فروشگاه آهن کیر خورد، آهنا کس شد و زنگ زدن",
    "کص خالتو تو فروشگاه پلاستیک کس مالید، پلاستیکا کس شد و ترکیدن",
    "کون دایی تو فروشگاه شیشه کیر می‌مکید، شیشه‌ها کس شد و شکستن",
    "کص ننت تو فروشگاه سنگ کس داد، سنگا کس شد و خرد شدن",
    "کون پدرت تو گور کون می‌ساید، قبر کس شد و ریخت",
    "کص خواهرت تو فروشگاه فلز کس فروخت، فلزا کس شد و اکسید شدن",
    "کون مادرت تو فروشگاه نخ کیر خورد، نخا کس شد و پاره شدن",
    "کص خالتو تو فروشگاه سیم کس مالید، سیما کس شد و قطع شدن",
    "کون دایی تو فروشگاه لوله کیر می‌مکید، لوله‌ها کس شد و ترکیدن",
    "کص ننت تو فروشگاه پیچ کس داد، پیچا کس شد و شل شدن",
    "کون پدرت تو گور کیر می‌زد به مهره، مهره کس شد و لق شد",
    "کص خواهرت تو فروشگاه ورق کس فروخت، ورقه‌ها کس شد و سوراخ شدن",
    "کون مادرت تو فروشگاه پروفیل کیر خورد، پروفیل‌ها کس شد و خم شدن",
    "کص خالتو تو فروشگاه تیرآهن کس مالید، تیرآهنا کس شد و افتاد",
    "کون دایی تو فروشگاه نبشی کیر می‌مکید، نبشی‌ها کس شد و شکست",
    "کص ننت تو فروشگاه ناودانی کس داد، ناودانی‌ها کس شد و نشتی داشتن",
    "کون پدرت تو گور کون تکون می‌ده، لرزه افتاد و قبر ریخت",
    "کص خواهرت تو فروشگاه پروفیل آلومینیوم کس فروخت، پروفیل‌ها کس شد و ترکیدن",
    "کون مادرت تو فروشگاه ورق گالوانیزه کیر خورد، ورقه‌ها کس شد و زنگ زدن",
    "کص خالتو تو فروشگاه توری کس مالید، توری‌ها کس شد و پاره شدن",
    "کون دایی تو فروشگاه میخ کیر می‌مکید، میخا کس شد و کج شدن",
    "کص ننت تو فروشگاه پیچ و مهره کس داد، پیچ و مهره‌ها کس شد و باز شدن",
    "کون پدرت تو گور کیر می‌زد به میلگرد، میلگرد کس شد و خم شد",
    "کص خواهرت تو فروشگاه سیمان کس فروخت، سیمان کس شد و خشک نشد",
    "کون مادرت تو فروشگاه گچ کیر خورد، گچ کس شد و ترکید",
    "کص خالتو تو فروشگاه آجر کس مالید، آجرا کس شد و خرد شدن",
    "کون دایی تو فروشگاه بلوک کیر می‌مکید، بلوکا کس شد و شکست",
    "کص ننت تو فروشگاه سنگ‌فرش کس داد، سنگ‌فرش کس شد و لق شد",
    "کون پدرت تو گور کون می‌ساید، قبرستان کس شد و بوی گند گرفت",
    "کص خواهرت تو فروشگاه کفپوش کس فروخت، کفپوشا کس شد و پاره شدن",
    "کون مادرت تو فروشگاه دیوارپوش کیر خورد، دیوارپوشا کس شد و کنده شدن",
    "کص خالتو تو فروشگاه کاغذ دیواری کس مالید، کاغذ دیواری کس شد و ترکید",
    "کون دایی تو فروشگاه رنگ ساختمانی کیر می‌مکید، رنگا کس شد و پوست دادن",
    "کص ننت تو فروشگاه چسب کس داد، چسبا کس شد و خشک نشد",
    "کون پدرت تو گور کیر می‌زد به درزگیر، درزگیر کس شد و نشتی داشت",
    "کص خواهرت تو فروشگاه عایق کس فروخت، عایقا کس شد و پوسیدن",
    "کون مادرت تو فروشگاه پلاستیک‌فوم کیر خورد، پلاستیک‌فوم کس شد و خرد شد",
    "کص خالتو تو فروشگاه یونولیت کس مالید، یونولیت کس شد و ترکید",
    "کون دایی تو فروشگاه گچبری کیر می‌مکید، گچبری‌ها کس شد و ریخت",
    "کص ننت تو فروشگاه آینه کس داد، آینه‌ها کس شد و تار شدن",
    "کون پدرت تو گور کون تکون می‌ده، قبر لرزید و ریخت",
    "کص خواهرت تو فروشگاه شیشه دکوراتیو کس فروخت، شیشه‌ها کس شد و شکست",
    "کون مادرت تو فروشگاه چوب صنعتی کیر خورد، چوبا کس شد و پوسیدن",
    "کص خالتو تو فروشگاه ام‌دی‌اف کس مالید، ام‌دی‌اف‌ها کس شد و ورم کردن",
    "کون دایی تو فروشگاه اچ‌دی‌اف کیر می‌مکید، اچ‌دی‌اف‌ها کس شد و ترکیدن",
    "کص ننت تو فروشگاه لمینت کس داد، لمینت‌ها کس شد و کنده شدن",
    "کون پدرت تو گور کیر می‌زد به پارکت، پارکت کس شد و ترکید",
    "کص خواهرت تو فروشگاه موکت کس فروخت، موکت‌ها کس شد و بوی گند گرفت",
    "کون مادرت تو فروشگاه فرش کیر خورد، فرشا کس شد و پوسیدن",
    "کص خالتو تو فروشگاه گلیم کس مالید، گلیم‌ها کس شد و پاره شدن",
    "کون دایی تو فروشگاه قالی کیر می‌مکید، قالی‌ها کس شد و ریخت",
    "کص ننت تو فروشگاه تابلوفرش کس داد، تابلوفرش‌ها کس شد و رنگ پریدن",
    "کون پدرت تو گور کون می‌ساید، خاک قبر کس شد و بوی کس گرفت",
    "کص خواهرت تو فروشگاه مبل کس فروخت، مبل‌ها کس شد و ترکیدن",
    "کون مادرت تو فروشگاه صندلی کیر خورد، صندلی‌ها کس شد و شکستن",
    "کص خالتو تو فروشگاه میز کس مالید، میزها کس شد و لق شدن",
    "کون دایی تو فروشگاه کمد کیر می‌مکید، کمدها کس شد و درهاش کج شد",
    "کص ننت تو فروشگاه طاقچه کس داد، طاقچه‌ها کس شد و ریخت",
    "کون پدرت تو گور کیر می‌زد به قفسه، قفسه کس شد و خم شد",
    "کص خواهرت تو فروشگاه کتابخانه کس فروخت، کتابخانه کس شد و کتابا ریخت",
    "کون مادرت تو فروشگاه آویز کیر خورد، آویزها کس شد و افتاد",
    "کص خالتو تو فروشگاه رگال کس مالید، رگال‌ها کس شد و شکست",
    "کون دایی تو فروشگاه چوب لباسی کیر می‌مکید، چوب لباسی‌ها کس شد و خم شدن",
    "کص ننت تو فروشگاه جاکفشی کس داد، جاکفشی‌ها کس شد و ترکیدن",
    "کون پدرت تو گور کون تکون می‌ده، قبر لرزید و فرو ریخت",
    "کص خواهرت تو فروشگاه جارختی کس فروخت، جارختی‌ها کس شد و کنده شدن",
    "کون مادرت تو فروشگاه آباژور کیر خورد، آباژورها کس شد و سوختن",
    "کص خالتو تو فروشگاه لوستر کس مالید، لوسترها کس شد و افتادن",
    "کون دایی تو فروشگاه چراغ کیر می‌مکید، چراغا کس شد و خاموش شدن",
    "کص ننت تو فروشگاه لامپ کس داد، لامپا کس شد و ترکیدن",
    "کون پدرت تو گور کیر می‌زد به کلید، کلید کس شد و قفل نشد",
    "کص خواهرت تو فروشگاه پریز کس فروخت، پریزا کس شد و جرقه زدن",
    "کون مادرت تو فروشگاه سیم‌کشی کیر خورد، سیم‌ها کس شد و قطع شدن",
    "کص خالتو تو فروشگاه فیوز کس مالید، فیوزها کس شد و سوختن",
    "کون دایی تو فروشگاه کنتاکتور کیر می‌مکید، کنتاکتورها کس شد و چسبیدن",
    "کص ننت تو فروشگاه کلید محافظ کس داد، کلیدها کس شد و عمل نکردن",
    "کون پدرت تو گور کون می‌ساید، قبر ترکید و کسش نمایان شد",
    "کص خواهرت تو فروشگاه جعبه فیوز کس فروخت، جعبه‌ها کس شد و شکستن",
    "کون مادرت تو فروشگاه رله کیر خورد، رله‌ها کس شد و اتصال کوتاه کردن",
    "کص خالتو تو فروشگاه تایمر کس مالید، تایمرها کس شد و کوک نشدن",
    "کون دایی تو فروشگاه سنسور کیر می‌مکید، سنسورها کس شد و خطا دادن",
    "کص ننت تو فروشگاه ترموستات کس داد، ترموستات‌ها کس شد و دما رو اشتباه گرفتن",
    "کون پدرت تو گور کیر می‌زد به شیر، شیر کس شد و باز موند",
    "کص خواهرت تو فروشگاه شیرآلات کس فروخت، شیرآلات کس شد و چکه کردن",
    "کون مادرت تو فروشگاه لوله‌کشی کیر خورد، لوله‌ها کس شد و نشتی داشتن",
    "کص خالتو تو فروشگاه اتصالات کس مالید، اتصالات کس شد و باز شدن",
    "کون دایی تو فروشگاه بست کیر می‌مکید، بست‌ها کس شد و لق شدن",
    "کص ننت تو فروشگاه واشر کس داد، واشرها کس شد و پاره شدن",
    "کون پدرت تو گور کون تکون می‌ده، قبر لرزید و فرو ریخت",
    "کص خواهرت تو فروشگاه آهن‌آلات کس فروخت، آهن‌آلات کس شد و زنگ زدن",
    "کون مادرت تو فروشگاه فولاد کیر خورد، فولاد کس شد و ترکید",
    "کص خالتو تو فروشگاه برنج کس مالید، برنج کس شد و اکسید شد",
    "کون دایی تو فروشگاه مس کیر می‌مکید، مس کس شد و رنگ عوض کرد",
    "کص ننت تو فروشگاه سرب کس داد، سرب کس شد و ذوب شد",
    "کون پدرت تو گور کیر می‌زد به روی، روی کس شد و پوسید",
    "کص خواهرت تو فروشگاه قلع کس فروخت، قلع کس شد و شکست",
    "کون مادرت تو فروشگاه نیکل کیر خورد، نیکل کس شد و سیاه شد",
    "کص خالتو تو فروشگاه کروم کس مالید، کروم کس شد و کنده شد",
    "کون دایی تو فروشگاه نقره کیر می‌مکید، نقره کس شد و تار شد",
    "کص ننت تو فروشگاه طلا کس داد، طلا کس شد و برقش رفت",
    "کون پدرت تو گور کون می‌ساید، قبر کس شد و خاکستر شد",
    "کص خواهرت تو فروشگاه پلاتین کس فروخت، پلاتین کس شد و نرم شد",
    "کون مادرت تو فروشگاه تیتانیوم کیر خورد، تیتانیوم کس شد و خم شد",
    "کص خالتو تو فروشگاه آلومینیوم کس مالید، آلومینیوم کس شد و ترکید",
    "کون دایی تو فروشگاه منیزیم کیر می‌مکید، منیزیم کس شد و سوخت",
    "کص ننت تو فروشگاه کبالت کس داد، کبالت کس شد و مغناطیس شد",
    "کون پدرت تو گور کیر می‌زد به تنگستن، تنگستن کس شد و شکست",
    "کص خواهرت تو فروشگاه وانادیم کس فروخت، وانادیم کس شد و اکسید شد",
    "کون مادرت تو فروشگاه مولیبدن کیر خورد، مولیبدن کس شد و نرم شد",
    "کص خالتو تو فروشگاه نیوبیم کس مالید، نیوبیم کس شد و خم شد",
    "کون دایی تو فروشگاه تانتالم کیر می‌مکید، تانتالم کس شد و ترکید",
    "کص ننت تو فروشگاه زیرکونیوم کس داد، زیرکونیوم کس شد و پوسید",
    "کون پدرت تو گور کون تکون می‌ده، زمین لرزید و کسش ترکید",
    "کص خواهرت تو فروشگاه هافنیوم کس فروخت، هافنیوم کس شد و اکسید شد",
    "کون مادرت تو فروشگاه رنیوم کیر خورد، رنیوم کس شد و نرم شد",
    "کص خالتو تو فروشگاه اسمیم کس مالید، اسمیم کس شد و شکست",
    "کون دایی تو فروشگاه ایریدیم کیر می‌مکید، ایریدیم کس شد و تار شد",
    "کص ننت تو فروشگاه پالادیم کس داد، پالادیم کس شد و برقش رفت",
    "کون پدرت تو گور کیر می‌زد به رودیم، رودیم کس شد و پوسید",
    "کص خواهرت تو فروشگاه روتنیم کس فروخت، روتنیم کس شد و خم شد",
    "کون مادرت تو فروشگاه اسکاندیم کیر خورد، اسکاندیم کس شد و ترکید",
    "کص خالتو تو فروشگاه ایتریم کس مالید، ایتریم کس شد و اکسید شد",
    "کون دایی تو فروشگاه لانتانیم کیر می‌مکید، لانتانیم کس شد و نرم شد",
    "کص ننت تو فروشگاه سریم کس داد، سریم کس شد و شکست",
    "کون پدرت تو گور کون می‌ساید، قبر کس شد و خاکستر شد",
    "کص خواهرت تو فروشگاه پرازئودیمیم کس فروخت، پرازئودیمیم کس شد و تار شد",
    "کون مادرت تو فروشگاه نئودیمیم کیر خورد، نئودیمیم کس شد و برقش رفت",
    "کص خالتو تو فروشگاه پرومتیم کس مالید، پرومتیم کس شد و پوسید",
    "کون دایی تو فروشگاه ساماریم کیر می‌مکید، ساماریم کس شد و خم شد",
    "کص ننت تو فروشگاه یوروپیم کس داد، یوروپیم کس شد و ترکید",
    "کون پدرت تو گور کیر می‌زد به گادولینیم، گادولینیم کس شد و اکسید شد",
    "کص خواهرت تو فروشگاه تربیم کس فروخت، تربیم کس شد و نرم شد",
    "کون مادرت تو فروشگاه دیسپروزیم کیر خورد، دیسپروزیم کس شد و شکست",
    "کص خالتو تو فروشگاه هولمیم کس مالید، هولمیم کس شد و تار شد",
    "کون دایی تو فروشگاه اربیوم کیر می‌مکید، اربیوم کس شد و برقش رفت",
    "کص ننت تو فروشگاه تولیم کس داد، تولیم کس شد و پوسید",
    "کون پدرت تو گور کون تکون می‌ده، زمین لرزید و کسش ترکید",
    "کص خواهرت تو فروشگاه ایتربیوم کس فروخت، ایتربیوم کس شد و خم شد",
    "کون مادرت تو فروشگاه لوتسیم کیر خورد، لوتسیم کس شد و ترکید",
    "کص خالتو تو فروشگاه هافنیوم کس مالید، هافنیوم کس شد و اکسید شد",
    "کون دایی تو فروشگاه تانتالم کیر می‌مکید، تانتالم کس شد و نرم شد",
        "کص ننت تو کفش من جا شد، هر قدم می‌زنم می‌لرزه",
    "کون پدرت تو گور کیر می‌خوره، شیاطین صف کشیدن",
    "کص خواهرت تو پارک فروشی راه انداخت، بچه‌ها صف کشیدن",
    "کون مادرت تو حموم عمومی تخم‌مرغ می‌ذاره، صبحونه رایگان",
    "کص خالتو سگا لیسیدن، گفتن نمک زیاد داره",
    "کون داییتو مجلس ختم کیر مالیدن، مرده زنده شد",
    "کص ننت تو یخچال فاسد شد، بوی گندش کل شهر گرفت",
    "کون پدرت تو تابوت کیر می‌خوره، می‌گه طعم بهشته",
    "کص خواهرت تو سینما پخش شد، سالن پر از بوی کس شد",
    "کون مادرت تو باغچه کاشت، درخت کون دراومد",
    "کص خالتو کتابخونه ثبت کردن، امانت می‌دن با کارت",
    "کون دایی تو حموم کیر می‌خورد، صابون جا موند و آب کیر شد",
    "کص ننت تو ماشین لباسشویی گیر کرد، برنامه سنگین روش ریخت",
    "کون پدرت تو گور کون تکون میده، زلزله ۷ ریشتری اومد",
    "کص خواهرت تو تاکسی به راننده داد، کرایه رفت بالا",
    "کون مادرت تو مدرسه به معلم داد، نمره بیست گرفت",
    "کص خالتو عروسی پخش کردن، عروس داماد شاخ درآوردن",
    "کون دایی تو گور کیر می‌مکید، مرده‌ها حسودیشون شد",
    "کص ننت تو فر پخت، نون کس پخته شد",
    "کون پدرت تو آشغال‌ها گیر کرد، سگا صف کشیدن",
    "کص خواهرت تو استخر شنا کرد، آب کیر شد همه چی",
    "کون مادرت تو مجلس عزا کیر می‌خورد، عزادارا خندشون گرفت",
    "کص خالتو بیمارستان واکسن زدن، کس‌واکسنی شد",
    "کون دایی تو کافی‌شاپ کیر می‌مکید، قهوه تلخ شد",
    "کص ننت تو هواپیما جا شد، مسافرا چتر باز کردن",
    "کون پدرت تو گور کون می‌ساید، سنگ قبرش برق می‌زنه",
    "کص خواهرت تو تلویزیون پخش زنده داشت، کل ایران دید",
    "کون مادرت تو قطار کیر می‌خورد، واگن‌ها لرزیدن",
    "کص خالتو مترو فروخت، واگن زنانه پر شد",
    "کون دایی تو نماز جمعه کیر می‌مکید، خطیب مونث شد",
    "کص ننت تو شب یلدا باز شد، هندونه‌ها کیر شدن",
    "کون پدرت تو گور کیر می‌زد به مار، مار کونی شد",
    "کص خواهرت تو حموم به روبات داد، هوش مصنوعی کس‌خوار شد",
    "کون مادرت تو آشپزخونه سوخت، غذا کیر شد",
    "کص خالتو باغ وحش به میمون دادن، میمون آدم شد",
    "کون دایی تو کوه کیر می‌مکید، سنگ‌ها ریخت",
    "کص ننت تو جاده مالیده شد، آسفالت لیز شد",
    "کون پدرت تو تابوت باز شد، بوی کیر پیچید",
    "کص خواهرت تو فروشگاه تخفیف داشت، اجناس کس شد",
    "کون مادرت تو بیمارستان کیر می‌خورد، دکترا شاگردی کردن",
    "کص خالتو مدرسه تدریس کردن، درس کس‌شناسی",
    "کون دایی تو عروسی کیر می‌زد به دف، ساز کونی شد",
    "کص ننت تو قبرستون کس می‌داد، مرده‌ها نماز شبشون شد",
    "کون پدرت تو گور کیر می‌مالید به استخوناش، مغز استخوان کیر شد",
    "کص خواهرت تو پمپ بنزین سوخت، آتیش گرفت همه جا",
    "کون مادرت تو رستوران کیر می‌خورد، غذا کیری شد",
    "کص خالتو تو تاکسی اینترنتی سوار شد، راننده کیرش خشک شد",
    "کون دایی تو باشگاه کیر می‌مکید، دمبل‌ها کیر شدن",
    "کص ننت تو بندر کس می‌داد، کشتی‌ها لنگر انداختن",
    "کون پدرت تو گور کیر می‌زد به خاک، زمین لرزید",
    "کص خواهرت تو سونا کس پخت، بخار کیر شد",
    "کون مادرت تو مطب دکتر کیر می‌خورد، نسخه کیری نوشت",
    "کص خالتو پشت کامپیوتر کس مالید، هارد کیر شد",
    "کون دایی تو اتوبوس کیر می‌مکید، مسافرا پیاده شدن",
    "کص ننت تو سفر کس خشک کرد، خاک راه کیر شد",
    "کون پدرت تو گور کون می‌لرزونه، اموات بیدار شدن",
    "کص خواهرت تو لباسشویی کس ریخت، ماشین خراب شد",
    "کون مادرت تو نانوایی کیر می‌خورد، نون کیری پخت",
    "کص خالتو آرایشگاه کس مالید، مشتریا کیر شدن",
    "کون دایی تو تعمیرگاه کیر می‌مکید، ماشینا روشن شدن",
    "کص ننت تو بیمارستان روانی کس داد، بیمارا خوب شدن",
    "کون پدرت تو گور کیر می‌زد به سنگ، قبر شکست",
    "کص خواهرت تو دانشگاه کس تدریس کرد، استادا شاگرد شدن",
    "کون مادرت تو بازار کیر می‌خورد، اجناس کیری شد",
    "کص خالتو تو سینمای خانگی کس پخش شد، فیلم کیری شد",
    "کون دایی تو زمین فوتبال کیر می‌مکید، توپ کیر شد",
    "کص ننت تو حمام عمومی کس فروخت، صابون کیری شد",
    "کون پدرت تو گور کون می‌سایید، خاکستر کیر شد",
    "کص خواهرت تو قطار زیرزمینی کس داد، واگن‌ها کیر شدن",
    "کون مادرت تو فروشگاه زنجیره‌ای کیر می‌خورد، اجناس تخفیف کیری",
    "کص خالتو تو پارک آبی کس شنا کرد، آب کیر شد",
    "کون دایی تو کتابفروشی کیر می‌مکید، کتابا کیری شدن",
    "کص ننت تو کوهنوردی کس خشک کرد، سنگ‌ها کیر شدن",
    "کون پدرت تو گور کیر می‌زد به مارمولک، مارمولک کونی شد",
    "کص خواهرت تو تاکسی تلفنی کس داد، راننده کیرش دراومد",
    "کون مادرت تو رستوران فست‌فود کیر می‌خورد، همبرگر کیری شد",
    "کص خالتو تو سینما ۳ بعدی کس پخش شد، عینکا کیر شدن",
    "کون دایی تو باشگاه بدنسازی کیر می‌مکید، عضلات کیر شدن",
    "کص ننت تو باغ‌وحش کس به شیر داد، شیر کونی شد",
    "کون پدرت تو گور کیر می‌زد به ریشه درخت، درخت کیر داد",
    "کص خواهرت تو مدرسه شبانه روزی کس فروخت، مدیر کیر شد",
    "کون مادرت تو بیمارستان اعصاب کیر می‌خورد، بیمارا شفا یافتن",
    "کص خالتو تو دیسکو کس مالید، موسیقی کیری شد",
    "کون دایی تو کافی‌نت کیر می‌مکید، اینترنت کیر شد",
    "کص ننت تو مزرعه کس به گاو داد، شیر کیری شد",
    "کون پدرت تو گور کون تکون می‌ده، مرده‌ها می‌رقصن",
    "کص خواهرت تو استخر شنای کس ریخت، آب کیر شد و ماهیا مردن",
    "کون مادرت تو هتل کیر می‌خورد، تخت‌ها کیر شدن",
    "کص خالتو تو هواپیما کس باز کرد، مهموندارا کیر شدن",
    "کون دایی تو قطار سریع‌السیر کیر می‌مکید، سرعت کیر شد",
    "کص ننت تو فروشگاه اینترنتی کس فروخت، مرجوعی کیری",
    "کون پدرت تو گور کیر می‌زد به استخون، مغز کیر شد",
    "کص خواهرت تو باشگاه رقص کس داد، رقص کیری شد",
    "کون مادرت تو مدرسه رانندگی کیر می‌خورد، ماشین کیر شد",
    "کص خالتو تو پارکینگ کس مالید، ماشینا کیر شدن",
    "کون دایی تو آزمایشگاه کیر می‌مکید، نمونه‌ها کیری شدن",
    "کص ننت تو مطب دندانپزشکی کس داد، دندان‌ها کیر شدن",
    "کون پدرت تو گور کیر می‌زد به کفن، پارچه کیری شد",
    "کص خواهرت تو فروشگاه حیوانات کس فروخت، حیوونا کیر شدن",
    "کون مادرت تو زمین بازی کیر می‌خورد، وسایل کیری شد",
    "کص خالتو تو استودیو ضبط کس پخش شد، آهنگ کیری شد",
    "کون دایی تو رستوران چینی کیر می‌مکید، چوپستون کیر شد",
    "کص ننت تو فروشگاه لباس کس مالید، لباسا کیری شدن",
    "کون پدرت تو گور کیر می‌زد به کرم، کرم کونی شد",
    "کص خواهرت تو کافه کس داد، قهوه کیری شد",
    "کون مادرت تو کتابخونه کیر می‌خورد، کتابا کیر شدن",
    "کص خالتو تو فروشگاه اسباب‌بازی کس فروخت، اسباب‌بازی کیری شد",
    "کون دایی تو سینما کیر می‌مکید، فیلم کیری شد",
    "کص ننت تو هاستل کس داد، تخت‌ها کیر شدن",
    "کون پدرت تو گور کون می‌ساید، خاک قبر کیر شد",
    "کص خواهرت تو فروشگاه دیجیتال کس فروخت، گوشی کیری شد",
    "کون مادرت تو باشگاه تنیس کیر می‌خورد، راکت کیر شد",
    "کص خالتو تو رستوران ایتالیایی کس مالید، پاستا کیری شد",
    "کون دایی تو اتاق بازی کیر می‌مکید، بازی‌ها کیری شدن",
    "کص ننت تو فروشگاه عتیقه کس داد، عتیقه‌ها کیر شدن",
    "کون پدرت تو گور کیر می‌زد به سنگ قبر، سنگ ترکید",
    "کص خواهرت تو فروشگاه گل کس فروخت، گل‌ها کیری شدن",
    "کون مادرت تو سینمای روباز کیر می‌خورد، پرده کیر شد",
    "کص خالتو تو فروشگاه لوازم آرایشی کس مالید، لوازم کیری شدن",
    "کون دایی تو بیمارستان دامپزشکی کیر می‌مکید، حیوونا کیر شدن",
    "کص ننت تو فروشگاه مبلمان کس داد، مبل‌ها کیر شدن",
    "کون پدرت تو گور کیر می‌زد به ریشه، درخت کیر داد",
    "کص خواهرت تو فروشگاه کفش کس فروخت، کفشا کیری شدن",
    "کون مادرت تو رستوران ژاپنی کیر می‌خورد، سوشی کیری شد",
    "کص خالتو تو فروشگاه پارچه کس مالید، پارچه کیری شد",
    "کون دایی تو فروشگاه موسیقی کیر می‌مکید، سازها کیر شدن",
    "کص ننت تو فروشگاه عینک کس داد، عینکا کیری شدن",
    "کون پدرت تو گور کون تکون می‌ده، زمین می‌لرزه",
    "کص خواهرت تو فروشگاه ساعت کس فروخت، ساعتا کیر شدن",
    "کون مادرت تو فروشگاه جواهرات کیر می‌خورد، جواهرا کیر شدن",
    "کص خالتو تو فروشگاه کیف کس مالید، کیفا کیری شدن",
    "کون دایی تو فروشگاه کاغذ کیر می‌مکید، کاغذا کیر شدن",
    "کص ننت تو فروشگاه رنگ کس داد، رنگا کیری شدن",
    "کون پدرت تو گور کیر می‌زد به خاک، خاک کیر شد",
    "کص ننت تو فروشگاه تنگستن کس داد، تنگستن کس شد و شکست",
]

BOT_VERSION = "4.9.6"
BOT_CREATOR = "VROOM"
PANEL_HEADER_IMAGE = "panel_header.png"  # تصویر بالای پنل (تصویر جدید VROOM)

# تصویر پنل embed شده — اگر فایل کنار اسکریپت نباشد از این ساخته می‌شود
_PANEL_HEADER_B64 = """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"""

def ensure_panel_header_files():
    """ساخت فایل‌های تصویر پنل از base64 اگر روی دیسک نباشند"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        targets = [
            os.path.join(base_dir, "panel_header.png"),
            os.path.join(base_dir, "panel_header_base.png"),
            os.path.join(base_dir, "user_panel_header.png"),
            "panel_header.png",
            "panel_header_base.png",
            "user_panel_header.png",
            os.path.join("media_storage", "panel_header.png"),
        ]
        raw = None
        for t in targets:
            try:
                if t and os.path.exists(t) and os.path.getsize(t) > 1000:
                    return t
            except Exception:
                pass
        try:
            raw = base64.b64decode(_PANEL_HEADER_B64)
        except Exception as e:
            logger.error(f"decode panel b64: {e}")
            return None
        for t in targets[:3]:
            try:
                os.makedirs(os.path.dirname(t) or ".", exist_ok=True)
                with open(t, "wb") as f:
                    f.write(raw)
            except Exception as e:
                logger.debug(f"write panel {t}: {e}")
        return targets[0] if os.path.exists(targets[0]) else ("panel_header.png" if os.path.exists("panel_header.png") else None)
    except Exception as e:
        logger.error(f"ensure_panel_header_files: {e}")
        return None


HEARTS = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🤍"]
MOONS = ["🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘", "🌑"]

media_cache = {}
panel_photo_cache = {}  # user_id -> photo file_id برای اینلاین یک‌پیامه
user_panel_cache = {}  # owner_id -> pending user panel data
message_cache = {}
user_inline_messages = {}

action_types = {
    'تایپ': types.SendMessageTypingAction(),
    'ویس': types.SendMessageRecordAudioAction(),
    'ویدیو': types.SendMessageRecordVideoAction(),
    'عکس': types.SendMessageUploadPhotoAction(progress=0),
    'فیلم': types.SendMessageUploadVideoAction(progress=0),
    'فایل': types.SendMessageUploadDocumentAction(progress=0),
    'بازی': types.SendMessageGamePlayAction(),
    'استیکر': types.SendMessageChooseStickerAction(),
    'موقعیت': types.SendMessageGeoLocationAction(),
    'تماس': types.SendMessageChooseContactAction(),
    'صحبت': types.SpeakingInGroupCallAction(),
    'لغو': types.SendMessageCancelAction(),
}

R = "❤️"
W = "🤍"
SLEEP = 0.1

def create_heart_matrix(size):
    heart = []
    for i in range(size):
        row = ""
        for j in range(size):
            if (i == 0 and (j == 0 or j == size-1)) or \
               (i == 1 and (j == 0 or j == 1 or j == size-2 or j == size-1)) or \
               (i == 2 and (j == 0 or j == 1 or j == 2 or j == size-3 or j == size-2 or j == size-1)) or \
               (i >= 3 and i < size-1 and (j >= i-2 and j <= size-(i-2)-1)) or \
               (i == size-1 and (j >= size//2 - 1 and j <= size//2 + 1)):
                row += R
            else:
                row += W
        heart.append(row)
    return "\n".join(heart)

JOINED_HEART = create_heart_matrix(7)
HEARTLET_LEN = JOINED_HEART.count(R)

class ReportConfig:
    def __init__(self, user_id, config_file=REPORT_CONFIG_FILE):
        self.user_id = user_id
        self.config_file = config_file
        self.report_group_id = GROUP_ID
        self.auto_save_media = True
        self.report_deleted_media = True
        self.report_edited_messages = True
        self.report_ttl_media = True
        self.load_config()
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    user_settings = data.get(str(self.user_id), {})
                    self.report_group_id = user_settings.get('report_group_id', GROUP_ID)
                    self.auto_save_media = user_settings.get('auto_save_media', True)
                    self.report_deleted_media = user_settings.get('report_deleted_media', True)
                    self.report_edited_messages = user_settings.get('report_edited_messages', True)
                    self.report_ttl_media = user_settings.get('report_ttl_media', True)
                logger.info(f"تنظیمات گزارش برای کاربر {self.user_id} لود شد")
            else:
                self.save_config()
        except Exception as e:
            logger.error(f"خطا در بارگذاری تنظیمات: {e}")
    
    def save_config(self):
        try:
            data = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
            
            data[str(self.user_id)] = {
                'report_group_id': self.report_group_id,
                'auto_save_media': self.auto_save_media,
                'report_deleted_media': self.report_deleted_media,
                'report_edited_messages': self.report_edited_messages,
                'report_ttl_media': self.report_ttl_media
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            logger.info(f"تنظیمات گزارش برای کاربر {self.user_id} ذخیره شد")
        except Exception as e:
            logger.error(f"خطا در ذخیره تنظیمات: {e}")
    
    def set_report_group(self, group_id):
        self.report_group_id = group_id
        self.save_config()
        return f"✅ گروه گزارش به {group_id} تغییر کرد"
    
    def toggle_auto_save(self):
        self.auto_save_media = not self.auto_save_media
        self.save_config()
        status = "فعال" if self.auto_save_media else "غیرفعال"
        return f"✅ ذخیره خودکار رسانه‌ها {status} شد"

class MainDatabase:
    def __init__(self, db_name='main_database.db'):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS media_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                target_id INTEGER,
                lock_link BOOLEAN DEFAULT 0,
                lock_photo BOOLEAN DEFAULT 0,
                lock_video BOOLEAN DEFAULT 0,
                lock_sticker BOOLEAN DEFAULT 0,
                lock_gif BOOLEAN DEFAULT 0,
                lock_voice BOOLEAN DEFAULT 0,
                lock_file BOOLEAN DEFAULT 0,
                lock_music BOOLEAN DEFAULT 0,
                lock_video_note BOOLEAN DEFAULT 0,
                lock_contact BOOLEAN DEFAULT 0,
                lock_location BOOLEAN DEFAULT 0,
                lock_emoji BOOLEAN DEFAULT 0,
                lock_text BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, target_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                phone TEXT,
                self_active BOOLEAN DEFAULT 0,
                admin_approved BOOLEAN DEFAULT 0,
                rejected BOOLEAN DEFAULT 0,
                request_sent BOOLEAN DEFAULT 0,
                step TEXT,
                phone_code_hash TEXT,
                code TEXT,
                password TEXT,
                request_date TEXT,
                activation_date TEXT,
                expiration_date TEXT,
                session_file TEXT,
                api_id INTEGER,
                api_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                message_text TEXT,
                message_type TEXT DEFAULT 'text',
                media_file TEXT,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                known_name TEXT,
                chat_id INTEGER,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                key TEXT,
                value TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_memory (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS selfbot_settings (
                user_id INTEGER PRIMARY KEY,
                time_enabled BOOLEAN DEFAULT 0,
                flag_enabled BOOLEAN DEFAULT 0,
                pv_lock_all BOOLEAN DEFAULT 0,
                autosend_mode BOOLEAN DEFAULT 0,
                text_style TEXT,
                report_group_id INTEGER DEFAULT -1002817019483,
                ai_1_pm BOOLEAN DEFAULT 0,
                ai_2_pm BOOLEAN DEFAULT 0,
                ai_3_pm BOOLEAN DEFAULT 0,
                ai_1_group BOOLEAN DEFAULT 0,
                ai_2_group BOOLEAN DEFAULT 0,
                ai_3_group BOOLEAN DEFAULT 0,
                translate_english BOOLEAN DEFAULT 0,
                translate_arabic BOOLEAN DEFAULT 0,
                translate_hebrew BOOLEAN DEFAULT 0,
                translate_russian BOOLEAN DEFAULT 0,
                translate_turkish BOOLEAN DEFAULT 0,
                panel_mode BOOLEAN DEFAULT 1,
                time_font_indices TEXT,
                selected_flags TEXT,
                filter_enabled BOOLEAN DEFAULT 0,
                selfbot_enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enemies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                enemy_id INTEGER,
                chat_type TEXT DEFAULT 'pv',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, enemy_id, chat_type)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locked_pvs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                locked_user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, locked_user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                chat_id INTEGER,
                target_id INTEGER,
                emoji TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, chat_id, target_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auto_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                channel_id INTEGER,
                comment_text TEXT,
                channel_title TEXT,
                channel_type TEXT,
                channel_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, channel_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                comment_sent BOOLEAN DEFAULT 0,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, channel_id, message_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                chat_id INTEGER,
                message_id INTEGER,
                message_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, chat_id, message_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enemy_spam_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                spam_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS filter_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                word TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, word)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spam_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                spam_protection BOOLEAN DEFAULT 0,
                spam_limit INTEGER DEFAULT 10,
                mute_duration INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                target_id INTEGER,
                lock_type TEXT,
                enabled BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, target_id, lock_type)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pinned_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                chat_id INTEGER,
                message_id INTEGER,
                pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, chat_id, message_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bio_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                setting_name TEXT,
                status TEXT DEFAULT 'خاموش',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, setting_name)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question TEXT,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, question)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monshi_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status BOOLEAN DEFAULT 0,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_bio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bio_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'api_id' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN api_id INTEGER")
        if 'api_hash' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN api_hash TEXT")
        
        # migration for selected_flags in selfbot_settings
        cursor.execute("PRAGMA table_info(selfbot_settings)")
        sb_columns = [col[1] for col in cursor.fetchall()]
        if 'selected_flags' not in sb_columns:
            try:
                cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN selected_flags TEXT")
            except Exception:
                pass
        for col, typedef in [
            ('profile_clock_enabled', 'BOOLEAN DEFAULT 0'),
            ('profile_clock_color', "TEXT DEFAULT 'cyan'"),
            ('profile_clock_backup', 'TEXT'),
        ]:
            if col not in sb_columns:
                try:
                    cursor.execute(f"ALTER TABLE selfbot_settings ADD COLUMN {col} {typedef}")
                except Exception:
                    pass
        
        conn.commit()
        conn.close()
        logger.info("✓ دیتابیس اصلی ایجاد شد (و ستون‌های api_id و api_hash و selected_flags و profile_clock اضافه شدند)")
    
    def add_user(self, user_id, full_name, username):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, full_name, username, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, full_name, username))
        conn.commit()
        conn.close()
    
    def get_user(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        return dict(zip(columns, row)) if row else None
    
    def update_user(self, user_id, **kwargs):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values())
        values.append(user_id)
        cursor.execute(f'UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', values)
        conn.commit()
        conn.close()
    
    def get_pending_requests(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users 
            WHERE request_sent = 1 AND admin_approved = 0 AND rejected = 0 AND step IS NULL
            ORDER BY request_date DESC
        ''')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_pending_login(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users 
            WHERE admin_approved = 1 AND self_active = 0 AND step IS NOT NULL
            ORDER BY activation_date DESC
        ''')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_active_users(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users 
            WHERE self_active = 1 AND admin_approved = 1
            ORDER BY activation_date DESC
        ''')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_all_users(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, full_name, username, phone, self_active, created_at 
            FROM users ORDER BY created_at DESC
        ''')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_selfbot_settings(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM selfbot_settings WHERE user_id = ?', (user_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        
        if row:
            settings = dict(zip(columns, row))
            settings['ai_status'] = {
                'ai_1_pm': bool(settings.get('ai_1_pm', 0)),
                'ai_2_pm': bool(settings.get('ai_2_pm', 0)),
                'ai_3_pm': bool(settings.get('ai_3_pm', 0)),
                'ai_1_group': bool(settings.get('ai_1_group', 0)),
                'ai_2_group': bool(settings.get('ai_2_group', 0)),
                'ai_3_group': bool(settings.get('ai_3_group', 0))
            }
            settings['translate'] = {
                'english': bool(settings.get('translate_english', 0)),
                'arabic': bool(settings.get('translate_arabic', 0)),
                'hebrew': bool(settings.get('translate_hebrew', 0)),
                'russian': bool(settings.get('translate_russian', 0)),
                'turkish': bool(settings.get('translate_turkish', 0)),
                'german': bool(settings.get('translate_german', 0)),
                'french': bool(settings.get('translate_french', 0)),
                'spanish': bool(settings.get('translate_spanish', 0)),
                'italian': bool(settings.get('translate_italian', 0)),
                'chinese': bool(settings.get('translate_chinese', 0)),
                'japanese': bool(settings.get('translate_japanese', 0)),
                'korean': bool(settings.get('translate_korean', 0)),
                'hindi': bool(settings.get('translate_hindi', 0)),
                'persian': bool(settings.get('translate_persian', 0)),
            }
            time_font_indices = settings.get('time_font_indices', 'all')
            if time_font_indices and time_font_indices != 'all':
                try:
                    settings['time_font_indices'] = [int(x) for x in time_font_indices.split(',')]
                except:
                    settings['time_font_indices'] = 'all'
            else:
                settings['time_font_indices'] = 'all'
            selected_flags = settings.get('selected_flags')
            if selected_flags and selected_flags != 'all' and selected_flags.strip():
                try:
                    settings['selected_flags'] = [f for f in selected_flags.split(',') if f]
                except:
                    settings['selected_flags'] = 'all'
            else:
                settings['selected_flags'] = 'all'
            settings.setdefault('selfbot_enabled', 1)
            return settings
        else:
            default_settings = {
                'user_id': user_id,
                'time_enabled': 0,
                'flag_enabled': 0,
                'pv_lock_all': 0,
                'autosend_mode': 0,
                'text_style': None,
                'report_group_id': GROUP_ID,
                'ai_1_pm': 0,
                'ai_2_pm': 0,
                'ai_3_pm': 0,
                'ai_1_group': 0,
                'ai_2_group': 0,
                'ai_3_group': 0,
                'translate_english': 0,
                'translate_arabic': 0,
                'translate_hebrew': 0,
                'translate_russian': 0,
                'translate_turkish': 0,
                'panel_mode': 1,
                'time_font_indices': 'all',
                'selected_flags': 'all',
                'filter_enabled': 0,
                'selfbot_enabled': 1,
                'profile_clock_enabled': 0,
                'profile_clock_color': 'cyan',
                'profile_clock_backup': None,
                'ai_status': {
                    'ai_1_pm': False,
                    'ai_2_pm': False,
                    'ai_3_pm': False,
                    'ai_1_group': False,
                    'ai_2_group': False,
                    'ai_3_group': False
                },
                'translate': {
                    'english': False,
                    'arabic': False,
                    'hebrew': False,
                    'russian': False,
                    'turkish': False
                }
            }
            self.set_selfbot_settings(user_id, default_settings)
            return default_settings
    
    def set_selfbot_settings(self, user_id, settings):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        settings_to_save = settings.copy()
        settings_to_save.pop('ai_status', None)
        settings_to_save.pop('translate', None)
        
        if 'time_font_indices' in settings_to_save and isinstance(settings_to_save['time_font_indices'], list):
            settings_to_save['time_font_indices'] = ','.join(map(str, settings_to_save['time_font_indices']))
        if 'selected_flags' in settings_to_save and isinstance(settings_to_save['selected_flags'], list):
            settings_to_save['selected_flags'] = ','.join(settings_to_save['selected_flags'])
        
        columns = ', '.join(settings_to_save.keys())
        placeholders = ', '.join(['?' for _ in settings_to_save])
        values = list(settings_to_save.values())
        
        cursor.execute(f'''
            INSERT OR REPLACE INTO selfbot_settings ({columns}, updated_at) 
            VALUES ({placeholders}, CURRENT_TIMESTAMP)
        ''', values)
        conn.commit()
        conn.close()
    
    def update_selfbot_setting(self, user_id, key, value):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM selfbot_settings WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            self.get_selfbot_settings(user_id)
        try:
            cursor.execute(
                f'UPDATE selfbot_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                (value, user_id)
            )
        except sqlite3.OperationalError:
            # ستون وجود ندارد — اضافه کن (نوع مناسب)
            try:
                if isinstance(value, str) or value is None:
                    typedef = 'TEXT'
                elif isinstance(value, float):
                    typedef = 'REAL'
                else:
                    typedef = 'INTEGER DEFAULT 0'
                cursor.execute(f'ALTER TABLE selfbot_settings ADD COLUMN {key} {typedef}')
                cursor.execute(
                    f'UPDATE selfbot_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                    (value, user_id)
                )
            except Exception:
                pass
        conn.commit()
        conn.close()
    
    def update_ai_status(self, user_id, ai_status):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        for key, value in ai_status.items():
            if key in ['ai_1_pm', 'ai_2_pm', 'ai_3_pm', 'ai_1_group', 'ai_2_group', 'ai_3_group']:
                cursor.execute(f'UPDATE selfbot_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (1 if value else 0, user_id))
        conn.commit()
        conn.close()
    
    def add_enemy(self, owner_id, enemy_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        try:
            enemy_id = int(enemy_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO enemies (owner_id, enemy_id, chat_type)
                VALUES (?, ?, ?)
            ''', (owner_id, enemy_id, chat_type))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()
    
    def remove_enemy(self, owner_id, enemy_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
            enemy_id = int(enemy_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM enemies WHERE owner_id = ? AND enemy_id = ? AND chat_type = ?', (owner_id, enemy_id, chat_type))
        conn.commit()
        conn.close()
    
    def get_enemies(self, owner_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT enemy_id FROM enemies WHERE owner_id = ? AND chat_type = ?', (owner_id, chat_type))
        enemies = [row[0] for row in cursor.fetchall()]
        conn.close()
        return enemies
    
    def is_enemy(self, owner_id, enemy_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        try:
            enemy_id = int(enemy_id)
        except Exception:
            pass
        enemies = self.get_enemies(owner_id, chat_type)
        for e in enemies:
            try:
                if int(e) == int(enemy_id):
                    return True
            except Exception:
                if e == enemy_id:
                    return True
        return False
    
    def add_locked_pv(self, owner_id, locked_user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO locked_pvs (owner_id, locked_user_id) VALUES (?, ?)', (owner_id, locked_user_id))
        conn.commit()
        conn.close()
    
    def remove_locked_pv(self, owner_id, locked_user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM locked_pvs WHERE owner_id = ? AND locked_user_id = ?', (owner_id, locked_user_id))
        conn.commit()
        conn.close()
    
    def get_locked_pvs(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT locked_user_id FROM locked_pvs WHERE owner_id = ?', (owner_id,))
        locked_pvs = [row[0] for row in cursor.fetchall()]
        conn.close()
        return locked_pvs
    
    def is_pv_locked(self, owner_id, user_id):
        locked_pvs = self.get_locked_pvs(owner_id)
        return user_id in locked_pvs
    
    def get_media_locks(self, owner_id, target_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM media_locks WHERE owner_id = ? AND target_id = ?', (owner_id, target_id))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(zip(columns, row))
        return {
            'owner_id': owner_id,
            'target_id': target_id,
            'lock_link': 0,
            'lock_photo': 0,
            'lock_video': 0,
            'lock_sticker': 0,
            'lock_gif': 0,
            'lock_voice': 0,
            'lock_file': 0,
            'lock_music': 0,
            'lock_video_note': 0,
            'lock_contact': 0,
            'lock_location': 0,
            'lock_emoji': 0,
            'lock_text': 0
        }
    
    def set_media_lock(self, owner_id, target_id, lock_type, value):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM media_locks WHERE owner_id = ? AND target_id = ?', (owner_id, target_id))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute(f'UPDATE media_locks SET {lock_type} = ?, created_at = CURRENT_TIMESTAMP WHERE owner_id = ? AND target_id = ?', (1 if value else 0, owner_id, target_id))
        else:
            lock_settings = {
                'owner_id': owner_id,
                'target_id': target_id,
                'lock_link': 0,
                'lock_photo': 0,
                'lock_video': 0,
                'lock_sticker': 0,
                'lock_gif': 0,
                'lock_voice': 0,
                'lock_file': 0,
                'lock_music': 0,
                'lock_video_note': 0,
                'lock_contact': 0,
                'lock_location': 0,
                'lock_emoji': 0,
                'lock_text': 0
            }
            lock_settings[lock_type] = 1 if value else 0
            columns = ', '.join(lock_settings.keys())
            placeholders = ', '.join(['?' for _ in lock_settings])
            values = list(lock_settings.values())
            cursor.execute(f'INSERT INTO media_locks ({columns}) VALUES ({placeholders})', values)
        
        conn.commit()
        conn.close()
    
    def get_user_lock(self, owner_id, target_id, lock_type):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT enabled FROM user_locks WHERE owner_id = ? AND target_id = ? AND lock_type = ?', (owner_id, target_id, lock_type))
        result = cursor.fetchone()
        conn.close()
        return bool(result[0]) if result else False
    
    def set_user_lock(self, owner_id, target_id, lock_type, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_locks (owner_id, target_id, lock_type, enabled)
            VALUES (?, ?, ?, ?)
        ''', (owner_id, target_id, lock_type, 1 if enabled else 0))
        conn.commit()
        conn.close()
    
    def set_reaction(self, owner_id, chat_id, target_id, emoji):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO reactions (owner_id, chat_id, target_id, emoji) VALUES (?, ?, ?, ?)', (owner_id, chat_id, target_id, emoji))
        conn.commit()
        conn.close()
    
    def get_reaction(self, owner_id, chat_id, target_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT emoji FROM reactions WHERE owner_id = ? AND chat_id = ? AND target_id = ?', (owner_id, chat_id, target_id))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def remove_reaction(self, owner_id, chat_id, target_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM reactions WHERE owner_id = ? AND chat_id = ? AND target_id = ?', (owner_id, chat_id, target_id))
        conn.commit()
        conn.close()
    
    def set_auto_comment(self, owner_id, channel_id, comment_text, channel_title, channel_type, channel_username):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO auto_comments (owner_id, channel_id, comment_text, channel_title, channel_type, channel_username)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (owner_id, channel_id, comment_text, channel_title, channel_type, channel_username))
        conn.commit()
        conn.close()
    
    def get_auto_comments(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auto_comments WHERE owner_id = ?', (owner_id,))
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_auto_comment(self, owner_id, channel_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auto_comments WHERE owner_id = ? AND channel_id = ?', (owner_id, channel_id))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        return dict(zip(columns, row)) if row else None
    
    def remove_auto_comment(self, owner_id, channel_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM auto_comments WHERE owner_id = ? AND channel_id = ?', (owner_id, channel_id))
        conn.commit()
        conn.close()
    
    def mark_comment_sent(self, owner_id, channel_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sent_comments (owner_id, channel_id, message_id, comment_sent) 
            VALUES (?, ?, ?, 1)
        ''', (owner_id, channel_id, message_id))
        conn.commit()
        conn.close()
    
    def is_comment_sent(self, owner_id, channel_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT comment_sent FROM sent_comments 
            WHERE owner_id = ? AND channel_id = ? AND message_id = ?
        ''', (owner_id, channel_id, message_id))
        result = cursor.fetchone()
        conn.close()
        return result and result[0] == 1
    
    def cache_message(self, owner_id, chat_id, message_id, message_text):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO message_cache (owner_id, chat_id, message_id, message_text) VALUES (?, ?, ?, ?)', (owner_id, chat_id, message_id, message_text))
        conn.commit()
        conn.close()
    
    def get_cached_message(self, owner_id, chat_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT message_text FROM message_cache WHERE owner_id = ? AND chat_id = ? AND message_id = ?', (owner_id, chat_id, message_id))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def add_enemy_spam_message(self, owner_id, spam_text):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO enemy_spam_messages (owner_id, spam_text) VALUES (?, ?)', (owner_id, spam_text))
        conn.commit()
        conn.close()
    
    def get_enemy_spam_messages(self, owner_id):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, spam_text FROM enemy_spam_messages WHERE owner_id = ? ORDER BY created_at', (owner_id,))
        results = cursor.fetchall()
        conn.close()
        return [{'id': row[0], 'text': row[1]} for row in results]
    
    def clear_enemy_spam_messages(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM enemy_spam_messages WHERE owner_id = ?', (owner_id,))
        conn.commit()
        conn.close()
    
    def delete_enemy_spam_message(self, owner_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM enemy_spam_messages WHERE owner_id = ? AND id = ?', (owner_id, message_id))
        conn.commit()
        conn.close()
    
    def add_filter_word(self, owner_id, word):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO filter_words (owner_id, word) VALUES (?, ?)', (owner_id, word))
        conn.commit()
        conn.close()
    
    def remove_filter_word(self, owner_id, word):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM filter_words WHERE owner_id = ? AND word = ?', (owner_id, word))
        conn.commit()
        conn.close()
    
    def remove_filter_word_by_id(self, owner_id, word_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM filter_words WHERE owner_id = ? AND id = ?', (owner_id, word_id))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    
    def toggle_filter_word_by_id(self, owner_id, word_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT enabled FROM filter_words WHERE owner_id = ? AND id = ?', (owner_id, word_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        new_state = 0 if row[0] else 1
        cursor.execute('UPDATE filter_words SET enabled = ? WHERE owner_id = ? AND id = ?', (new_state, owner_id, word_id))
        conn.commit()
        conn.close()
        return bool(new_state)
    
    def get_filter_words(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, word, enabled FROM filter_words WHERE owner_id = ? ORDER BY id', (owner_id,))
        results = cursor.fetchall()
        conn.close()
        return [{'id': row[0], 'word': row[1], 'enabled': bool(row[2])} for row in results]
    
    def toggle_filter_word(self, owner_id, word, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE filter_words SET enabled = ? WHERE owner_id = ? AND word = ?', (1 if enabled else 0, owner_id, word))
        conn.commit()
        conn.close()
    
    def toggle_all_filters(self, owner_id, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE filter_words SET enabled = ? WHERE owner_id = ?', (1 if enabled else 0, owner_id))
        conn.commit()
        conn.close()
    
    def get_filter_enabled(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT filter_enabled FROM selfbot_settings WHERE user_id = ?', (owner_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except:
            conn.close()
            return 0
    
    def set_filter_enabled(self, owner_id, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE selfbot_settings SET filter_enabled = ? WHERE user_id = ?', (1 if enabled else 0, owner_id))
        except:
            try:
                cursor.execute('ALTER TABLE selfbot_settings ADD COLUMN filter_enabled BOOLEAN DEFAULT 0')
                cursor.execute('UPDATE selfbot_settings SET filter_enabled = ? WHERE user_id = ?', (1 if enabled else 0, owner_id))
            except:
                pass
        conn.commit()
        conn.close()
    
    def get_spam_settings(self, owner_id):
        owner_id = str(owner_id)
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM spam_settings WHERE owner_id = ?', (owner_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(zip(columns, row))
        return {
            'owner_id': owner_id,
            'spam_protection': 0,
            'spam_limit': 10,
            'mute_duration': 10
        }
    
    def set_spam_settings(self, owner_id, spam_protection=None, spam_limit=None, mute_duration=None):
        owner_id = str(owner_id)
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM spam_settings WHERE owner_id = ?', (owner_id,))
        exists = cursor.fetchone()
        
        settings = {}
        if spam_protection is not None:
            settings['spam_protection'] = spam_protection
        if spam_limit is not None:
            settings['spam_limit'] = spam_limit
        if mute_duration is not None:
            settings['mute_duration'] = mute_duration
        
        if exists:
            set_clause = ', '.join([f"{key} = ?" for key in settings.keys()])
            values = list(settings.values())
            values.append(owner_id)
            cursor.execute(f'UPDATE spam_settings SET {set_clause} WHERE owner_id = ?', values)
        else:
            default_settings = {
                'owner_id': owner_id,
                'spam_protection': 0,
                'spam_limit': 10,
                'mute_duration': 10
            }
            default_settings.update(settings)
            columns = ', '.join(default_settings.keys())
            placeholders = ', '.join(['?' for _ in default_settings])
            values = list(default_settings.values())
            cursor.execute(f'INSERT INTO spam_settings ({columns}) VALUES ({placeholders})', values)
        
        conn.commit()
        conn.close()
    
    def get_original_name(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM user_info WHERE user_id = ? AND key = "original_name" ORDER BY timestamp DESC LIMIT 1', (owner_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_original_name(self, owner_id, original_name):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO user_info (user_id, key, value) VALUES (?, "original_name", ?)', (owner_id, original_name))
        conn.commit()
        conn.close()
    
    def get_current_name(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM user_info WHERE user_id = ? AND key = "current_name" ORDER BY timestamp DESC LIMIT 1', (owner_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_current_name(self, owner_id, current_name):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO user_info (user_id, key, value) VALUES (?, "current_name", ?)', (owner_id, current_name))
        conn.commit()
        conn.close()
    
    def get_user_name(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT known_name, first_name, username FROM user_memory WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            known_name, first_name, username = result
            if known_name:
                return known_name
            elif first_name:
                return first_name
            elif username:
                return f"@{username}"
        return f"کاربر {user_id}"
    
    def get_user_info(self, user_id, key=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        if key:
            cursor.execute('SELECT value FROM user_info WHERE user_id = ? AND key = ? ORDER BY timestamp DESC LIMIT 1', (user_id, key))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        else:
            cursor.execute('SELECT key, value FROM user_info WHERE user_id = ?', (user_id,))
            results = cursor.fetchall()
            conn.close()
            return dict(results) if results else {}
    
    def update_user_memory(self, user_id, username, first_name, last_name, chat_id, known_name=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM user_memory WHERE user_id = ?', (user_id,))
        user_exists = cursor.fetchone()
        
        if user_exists:
            cursor.execute('''
                UPDATE user_memory 
                SET username = ?, first_name = ?, last_name = ?, known_name = ?, chat_id = ?, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (username, first_name, last_name, known_name, chat_id, user_id))
        else:
            cursor.execute('''
                INSERT INTO user_memory (user_id, username, first_name, last_name, known_name, chat_id, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name, known_name, chat_id))
        conn.commit()
        conn.close()
    
    def add_broadcast(self, admin_id, message_text, message_type='text', media_file=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO broadcasts (admin_id, message_text, message_type, media_file)
            VALUES (?, ?, ?, ?)
        ''', (admin_id, message_text, message_type, media_file))
        broadcast_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return broadcast_id
    
    def update_broadcast_stats(self, broadcast_id, sent_count, failed_count):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE broadcasts SET sent_count = ?, failed_count = ?
            WHERE id = ?
        ''', (sent_count, failed_count, broadcast_id))
        conn.commit()
        conn.close()
    
    def add_pinned_message(self, owner_id, chat_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO pinned_messages (owner_id, chat_id, message_id) VALUES (?, ?, ?)', (owner_id, chat_id, message_id))
        conn.commit()
        conn.close()
    
    def get_pinned_messages(self, owner_id, chat_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT message_id FROM pinned_messages WHERE owner_id = ? AND chat_id = ?', (owner_id, chat_id))
        results = cursor.fetchall()
        conn.close()
        return [row[0] for row in results]

    def get_bio_setting(self, user_id, setting_name):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT status FROM bio_settings WHERE user_id = ? AND setting_name = ?', (user_id, setting_name))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 'خاموش'
    
    def set_bio_setting(self, user_id, setting_name, status):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO bio_settings (user_id, setting_name, status) 
            VALUES (?, ?, ?)
        ''', (user_id, setting_name, status))
        conn.commit()
        conn.close()
    
    def ensure_banned_table(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS banned_users ("
            "user_id INTEGER PRIMARY KEY, reason TEXT, "
            "banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()
        conn.close()

    def is_user_banned(self, user_id):
        try:
            self.ensure_banned_table()
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (int(user_id),))
            r = cursor.fetchone()
            conn.close()
            return bool(r)
        except Exception:
            return False

    def ban_user(self, user_id, reason=''):
        """فقط سلف را خاموش می‌کند — داده/سشن کاربر پاک نمی‌شود."""
        self.ensure_banned_table()
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO banned_users (user_id, reason) VALUES (?, ?)', (int(user_id), reason or 'self_off'))
        conn.commit()
        conn.close()
        try:
            # فقط self_active=0 — session_file و بقیه فیلدها دست نخورده می‌مانند
            self.update_user(str(user_id), self_active=0)
        except Exception:
            pass

    def unban_user(self, user_id):
        """آنبن: رفع بن + آماده‌سازی برای روشن شدن دوباره سلف."""
        self.ensure_banned_table()
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM banned_users WHERE user_id = ?', (int(user_id),))
        conn.commit()
        conn.close()
        try:
            self.update_user(str(user_id), self_active=1)
        except Exception:
            pass

    def get_monshi_status(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT status, answer FROM monshi_status WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return {'status': bool(result[0]), 'answer': result[1]} if result else {'status': False, 'answer': ''}
    
    def set_monshi_status(self, user_id, status, answer=''):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO monshi_status (user_id, status, answer) VALUES (?, ?, ?)",
            (user_id, 1 if status else 0, answer)
        )
        conn.commit()
        conn.close()
        if status:
            try:
                self.clear_monshi_sent(user_id)
            except Exception:
                pass

    def _ensure_monshi_sent(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS monshi_sent ("
            "owner_id INTEGER, peer_id INTEGER, "
            "PRIMARY KEY (owner_id, peer_id))"
        )
        conn.commit()
        conn.close()

    def was_monshi_sent(self, owner_id, peer_id):
        try:
            self._ensure_monshi_sent()
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM monshi_sent WHERE owner_id = ? AND peer_id = ?",
                (int(owner_id), int(peer_id))
            )
            r = cursor.fetchone()
            conn.close()
            return bool(r)
        except Exception:
            return False

    def mark_monshi_sent(self, owner_id, peer_id):
        try:
            self._ensure_monshi_sent()
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO monshi_sent (owner_id, peer_id) VALUES (?, ?)",
                (int(owner_id), int(peer_id))
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def clear_monshi_sent(self, owner_id):
        try:
            self._ensure_monshi_sent()
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM monshi_sent WHERE owner_id = ?", (int(owner_id),))
            conn.commit()
            conn.close()
        except Exception:
            pass


    def add_answer(self, user_id, question, answer):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO bot_answers (user_id, question, answer) 
            VALUES (?, ?, ?)
        ''', (user_id, question, answer))
        conn.commit()
        conn.close()
    
    def remove_answer(self, user_id, question):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM bot_answers WHERE user_id = ? AND question = ?', (user_id, question))
        conn.commit()
        conn.close()
    
    def get_answers(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT question, answer FROM bot_answers WHERE user_id = ? OR user_id = ?', (str(user_id), user_id))
        results = cursor.fetchall()
        conn.close()
        return {q: a for q, a in results}

    def get_learning_enabled(self, user_id):
        try:
            s = self.get_selfbot_settings(user_id)
            return bool(s.get('learning_enabled', 1))
        except Exception:
            return True

    def set_learning_enabled(self, user_id, enabled):
        try:
            self.update_selfbot_setting(user_id, 'learning_enabled', 1 if enabled else 0)
        except Exception:
            pass

    def get_backup_enabled(self, user_id):
        try:
            s = self.get_selfbot_settings(user_id)
            return bool(s.get('backup_enabled', 0))
        except Exception:
            return False

    def set_backup_enabled(self, user_id, enabled):
        try:
            self.update_selfbot_setting(user_id, 'backup_enabled', 1 if enabled else 0)
        except Exception:
            pass

db = MainDatabase()
selfbot_managers = {}

def convert_persian_to_english(text):
    if not text:
        return text
    
    persian_to_english = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
        '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    }
    for persian, english in persian_to_english.items():
        text = text.replace(persian, english)
    return text

def create_time():
    return get_now().strftime("%H:%M")

def create_time2():
    return get_now().strftime("%H:%M:%S")

# ========== ساعت روی پروفایل (سایبرپانک) ==========
PROFILE_CLOCK_COLORS = {
    "cyan": (0, 255, 200),
    "green": (0, 255, 120),
    "purple": (180, 80, 255),
    "pink": (255, 60, 180),
    "orange": (255, 140, 40),
    "red": (255, 40, 80),
    "blue": (40, 160, 255),
    "white": (230, 245, 255),
}

def compose_profile_clock_image(photo_path: str, color_name: str = "cyan", out_path: str = None) -> str:
    """ساعت پروفایل شبیه نمونه: قاب دندانه‌دار، قوس نئون، عکس وسط نیمه‌تاریک + مدار"""
    import math, tempfile, time as _t, random as _rnd
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
    except Exception as e:
        logger.error(f"compose_profile_clock PIL: {e}")
        return None
    try:
        color = PROFILE_CLOCK_COLORS.get((color_name or "cyan").lower(), PROFILE_CLOCK_COLORS["cyan"])
        size = 800
        cx = cy = size // 2
        canvas = Image.new("RGBA", (size, size), (5, 8, 12, 255))

        # عکس مربعی
        base = Image.open(photo_path).convert("RGBA")
        w, h = base.size
        side = min(w, h)
        base = base.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
        base = base.resize((size, size), Image.Resampling.LANCZOS)
        base = ImageEnhance.Contrast(base).enhance(1.25)
        base = ImageEnhance.Brightness(base).enhance(0.85)

        r_photo = int(size * 0.42)
        photo_mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(photo_mask).ellipse([cx - r_photo, cy - r_photo, cx + r_photo, cy + r_photo], fill=255)

        photo_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        photo_layer.paste(base, (0, 0), photo_mask)

        # نیمه چپ تاریک
        dark_half = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(dark_half).rectangle([0, 0, cx - 4, size], fill=(0, 0, 0, 155))
        # فقط داخل دایره
        alpha = dark_half.split()[-1]
        alpha = Image.composite(alpha, Image.new("L", (size, size), 0), photo_mask)
        dark_half.putalpha(alpha)
        photo_layer = Image.alpha_composite(photo_layer, dark_half)

        # خطوط مدار روی راست
        circuit = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        cd = ImageDraw.Draw(circuit)
        _rnd.seed(7)
        for _ in range(40):
            x1 = _rnd.randint(cx, size - 30)
            y1 = _rnd.randint(30, size - 30)
            if (x1 - cx) ** 2 + (y1 - cy) ** 2 > r_photo ** 2:
                continue
            x2 = x1 + _rnd.randint(-50, 70)
            y2 = y1 + _rnd.randint(-60, 60)
            cd.line([(x1, y1), (x2, y2)], fill=(*color, 100), width=1)
            cd.ellipse([x1 - 2, y1 - 2, x1 + 2, y1 + 2], fill=(*color, 160))
        calpha = circuit.split()[-1]
        calpha = Image.composite(calpha, Image.new("L", (size, size), 0), photo_mask)
        circuit.putalpha(calpha)
        photo_layer = Image.alpha_composite(photo_layer, circuit)
        canvas = Image.alpha_composite(canvas, photo_layer)

        # قاب دندانه‌دار
        rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        rd = ImageDraw.Draw(rim)
        r_outer = int(size * 0.48)
        r_inner = int(size * 0.435)
        teeth = 56
        for i in range(teeth):
            a0 = math.radians(i * 360 / teeth - 90)
            a1 = math.radians((i + 0.5) * 360 / teeth - 90)
            mid = (a0 + a1) / 2
            pts = [
                (cx + r_inner * math.cos(a0), cy + r_inner * math.sin(a0)),
                (cx + r_outer * math.cos(mid - 0.01), cy + r_outer * math.sin(mid - 0.01)),
                (cx + r_outer * math.cos(mid + 0.01), cy + r_outer * math.sin(mid + 0.01)),
                (cx + r_inner * math.cos(a1), cy + r_inner * math.sin(a1)),
            ]
            rd.polygon(pts, fill=(*color, 45), outline=(*color, 190))
        for ww, aa in ((7, 180), (3, 255)):
            rd.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], outline=(*color, aa), width=ww)
        canvas = Image.alpha_composite(canvas, rim)

        # قوس نئون راست
        now = get_now()
        day_pct = (now.hour * 60 + now.minute) / (24.0 * 60)
        arc_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ad = ImageDraw.Draw(arc_img)
        arc_r = r_outer - 2
        span = 25 + day_pct * 155
        bbox = [cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r]
        for thick, alpha in ((24, 35), (16, 70), (10, 140), (5, 255)):
            ad.arc(bbox, start=-75, end=-75 + span, fill=(*color, alpha), width=thick)
        canvas = Image.alpha_composite(canvas, arc_img)

        try:
            font_num = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
            font_lab = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
        except Exception:
            font_num = font_lab = ImageFont.load_default()

        draw = ImageDraw.Draw(canvas)
        r_tick = int(size * 0.395)
        for i in range(12):
            ang = math.radians(i * 30 - 90)
            x1 = cx + (r_tick - 4) * math.cos(ang)
            y1 = cy + (r_tick - 4) * math.sin(ang)
            x2 = cx + (r_tick + 12) * math.cos(ang)
            y2 = cy + (r_tick + 12) * math.sin(ang)
            draw.line([(x1, y1), (x2, y2)], fill=(*color, 210), width=3)
            num = str(i if i else 12)
            nx = cx + (r_tick - 30) * math.cos(ang)
            ny = cy + (r_tick - 30) * math.sin(ang)
            bb = draw.textbbox((0, 0), num, font=font_num)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            draw.text((nx - tw / 2, ny - th / 2), num, fill=(*color, 235), font=font_num)

        h, m = now.hour % 12, now.minute
        s = getattr(now, "second", 0) or 0
        hour_a = math.radians((h + m / 60) * 30 - 90)
        min_a = math.radians((m + s / 60) * 6 - 90)
        hx = cx + r_tick * 0.40 * math.cos(hour_a)
        hy = cy + r_tick * 0.40 * math.sin(hour_a)
        mx = cx + r_tick * 0.70 * math.cos(min_a)
        my = cy + r_tick * 0.70 * math.sin(min_a)
        draw.line([(cx, cy), (hx, hy)], fill=(*color, 245), width=9)
        draw.line([(cx, cy), (mx, my)], fill=(*color, 255), width=4)
        draw.ellipse([mx - 7, my - 7, mx + 7, my + 7], fill=(*color, 255))
        draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(*color, 255))
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(8, 12, 18, 255))

        time_str = now.strftime("%H∶%M")
        draw.text((30, 24), time_str, fill=(*color, 245), font=font_lab)
        pct_str = f"{int(day_pct * 100)}%"
        bb = draw.textbbox((0, 0), pct_str, font=font_lab)
        draw.text((size - 30 - (bb[2] - bb[0]), 24), pct_str, fill=(*color, 245), font=font_lab)

        if not out_path:
            out_path = os.path.join(tempfile.gettempdir(), f"pclock_{int(_t.time() * 1000)}.png")
        canvas.convert("RGB").save(out_path, "PNG", optimize=True)
        return out_path
    except Exception as e:
        logger.error(f"compose_profile_clock: {e}\n{traceback.format_exc()}")
        return None


def create_tarikh():
    jdatetime.set_locale('fa_IR')
    jd = jdatetime.date.fromgregorian(date=get_now().date())
    return jd.strftime("%Y/%m/%d")

def create_tarikh2():
    jdatetime.set_locale('fa_IR')
    jd = jdatetime.date.fromgregorian(date=get_now().date())
    return jd.strftime("%A %d %B %Y")

def moon_or_sun():
    hour = int(get_now().strftime("%H"))
    return "☀️ روز" if 6 <= hour < 18 else "🌙 شب"

def love_emoji():
    emojis = ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '💖', '💗', '💓', '💕', '💞', '💘', '💝']
    return random.choice(emojis)

def random_emoji():
    emojis = ['🔥', '⭐', '🌟', '✨', '💫', '🌈', '🎯', '🏆', '👑', '💎', '🎨', '🎭', '🎪', '🎯', '🎲']
    return random.choice(emojis)

def get_weekday():
    weekdays = {
        'Saturday': 'شنبه', 'Sunday': 'یکشنبه', 'Monday': 'دوشنبه',
        'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه', 'Thursday': 'پنج‌شنبه',
        'Friday': 'جمعه'
    }
    return weekdays.get(get_now().strftime('%A'), get_now().strftime('%A'))

def get_season():
    month = get_now().month
    if 3 <= month <= 5:
        return '🌸 بهار'
    elif 6 <= month <= 8:
        return '☀️ تابستان'
    elif 9 <= month <= 11:
        return '🍂 پاییز'
    else:
        return '❄️ زمستان'

fortunes = [
    "🌟 امروز روز خوبی برای شروع کارهای جدید است.",
    "💫 یک خبر خوب در راه است، منتظر باش.",
    "🌙 امشب ستاره‌ها به نفع تو هستند.",
    "🌸 عشق در گوشه و کنار زندگی توست، فقط باید ببینی.",
    "💰 یک فرصت مالی عالی در انتظار توست.",
    "🎯 به هدف‌هایت نزدیک‌تر شدی، ادامه بده.",
    "🌟 کسی که دوستش داری، به تو فکر می‌کند.",
    "🌈 روزت پر از رنگ و انرژی خواهد بود.",
    "💪 امروز قوی‌تر از همیشه‌ای، از این قدرت استفاده کن.",
    "🎉 جشن و شادی در راه است.",
    "📚 وقت آن رسیده که چیز جدیدی یاد بگیری.",
    "🤝 یک دوست جدید پیدا می‌کنی.",
    "💖 قلب تو امروز پر از عشق خواهد بود.",
    "🌟 ستاره بختت درخشان است.",
    "🎯 هر چه امروز بکاری، فردا درو می‌کنی.",
    "🌙 امشب رویاهایت را جدی بگیر.",
    "🌸 بهار زندگی تو شروع شده است.",
    "💰 پول و ثروت به سمت تو می‌آید.",
    "🎨 امروز خلاقیت تو در اوج است.",
    "🏆 موفقیت بزرگ در انتظار توست."
]

hafez_fortunes = [
    ("غم و شادی در این جهان به هم پیوسته‌اند", "🍃"),
    ("دل به امید وصل تو زنده است", "💕"),
    ("هر چه خواهی، همان خواهی یافت", "🌟"),
    ("صبر کن که گشایش در کار توست", "🌙"),
    ("عشق تو را به اوج می‌رساند", "❤️"),
    ("دوری و نزدیکی تقدیر توست", "🕊️"),
    ("بهار عمرت از راه رسید", "🌸"),
    ("دل به دریا بزن که نجات یابی", "🌊"),
]

coffee_fortunes = [
    "☕ عشق جدیدی وارد زندگی تو می‌شود",
    "☕ یک سفر طولانی در انتظار توست",
    "☕ خبر خوش از دور دست می‌رسد",
    "☕ به زودی ثروت زیادی به دست می‌آوری",
    "☕ کسی که دوستش داری، به تو نزدیک‌تر می‌شود",
    "☕ کارهای ناتمامت را امروز تمام کن",
    "☕ یک پیشنهاد عالی دریافت می‌کنی",
]

def is_channel_post(message):
    try:
        if hasattr(message, 'post') and message.post:
            return True
        if hasattr(message, 'is_channel') and message.is_channel:
            if hasattr(message, 'is_group') and not message.is_group:
                return True
            if not hasattr(message, 'from_id') or not message.from_id:
                return True
        if hasattr(message, 'chat') and message.chat:
            chat = message.chat
            if hasattr(chat, 'broadcast') and chat.broadcast:
                return True
        if hasattr(message, 'fwd_from') and message.fwd_from:
            if hasattr(message.fwd_from, 'from_id'):
                if hasattr(message.fwd_from.from_id, 'channel_id'):
                    return True
        return False
    except:
        return False

def is_link_message(text):
    if not text:
        return False
    patterns = [
        r'https?://\S+',
        r't\.me/\S+',
        r'www\.\S+',
        r'\S+\.(com|ir|org|net|info)\S*'
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def is_emoji_message(text):
    if not text:
        return False
    text = text.strip()
    if not text:
        return False
    emoji_pattern = re.compile(
        r'^[\U0001F600-\U0001F64F' 
        r'\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF'
        r'\U00002700-\U000027BF'
        r'\U000024C2-\U0001F251'
        r'\U0001F900-\U0001F9FF'
        r']+$', 
        flags=re.UNICODE
    )
    return bool(emoji_pattern.match(text))

def convert_to_classic_font(text, font_index):
    if font_index < 0 or font_index >= len(classic_fonts):
        font_index = 0
    if isinstance(classic_fonts[font_index], dict):
        font = classic_fonts[font_index]
        return ''.join(font.get(c, c) for c in text)
    else:
        font = classic_fonts[font_index]
        # map digits 0-9; if font shorter/longer, use modulo or keep original
        result = []
        for c in text:
            if c.isdigit():
                d = int(c)
                if len(font) >= 10:
                    result.append(font[d])
                elif len(font) > 0:
                    result.append(font[d % len(font)])
                else:
                    result.append(c)
            else:
                result.append(c)
        return ''.join(result)

async def get_ai_response(text, ai_type, user_id=None):
    try:
        if ai_type == 1:
            url = f"{GEMINI_URL}?key={GEMINI_KEY}"
            payload = {"contents": [{"parts": [{"text": text}]}]}
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result:
                    return result['candidates'][0]['content']['parts'][0]['text'].strip()
        elif ai_type == 2:
            headers = {'Authorization': f'Bearer {PAXSENIX_API_KEY}', 'Content-Type': 'application/json'}
            data = {'model': 'gpt-3.5-turbo', 'messages': [{'role': 'user', 'content': text}]}
            response = requests.post(PAXSENIX_API_URL, headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result:
                    return result['choices'][0]['message']['content'].strip()
        elif ai_type == 3:
            response = requests.get(DEEPSEEK_FREE_URL + quote(text), timeout=30)
            if response.status_code == 200:
                return response.text.strip()
    except:
        pass
    return None


# ریشه‌های دستور (فقط تطبیق دقیق کلمه اول — نه پیشوند داخل متن)
COMMAND_ROOTS = {
    'لیست', 'شروع', 'تایم', 'قلب', 'ماه', 'اطلاعات', 'دانلود', 'تاریخ', 'فعال', 'غیرفعال',
    'حذف', 'ست', 'بولد', 'زیرخط', 'خط', 'نقل', 'اسپویلر', 'کج', 'کد', 'پیش', 'اسپم', 'بلاک',
    'ریکت', 'پیوی', 'گروه', 'درباره', 'من', 'قفل', 'باز', 'تنظیم', 'اکشن', 'دشمن', 'دوست', 'کانال',
    'کامنت', 'تست', 'پاک', 'اضافه', 'اتمام', 'تغییر', 'پروف', 'پینگ', 'سرچ', 'خروج',
    'عشق', 'سنتت', 'هک', 'وضعیت', '.پنل', 'پنل', '/panel', '.اهنگ', 'سلف', 'پین', 'تگ',
    'امار', '.کد', 'تقویم', 'فونت', 'انگلیسی', 'عربی', 'عبری', 'روسی', 'ترکی', 'اتوسین',
    'لغو', 'منشی', 'افزودن', 'بولینگ', 'تاس', 'سه', 'شانس', 'نشست\u200cهای', 'قیمت', 'نرخ',
    'استیکر', 'ساخت', 'اسکرین\u200cشات', 'اسکرین‌شات', 'تشخیص', 'ساعت', 'بیو', 'ترجمه', 'دلار',
    'یادگیری', 'بکاپ', 'بکاب', 'اتمام', 'فال', 'اطلاعات', '.بن', '.انبن', 'بن', 'انبن', 'دارت', 'بسکتبال', 'فوتبال', '.بن', '.انبن', 'بن', 'انبن',
    'یوزرنیم',
    'یوزنیم', 'ایدی', 'آیدی', 'آیدی\u200cعددی', 'ایدی\u200cعددی', 'username', 'id',
    'فیلتر', 'ویس', 'صدا', 'ویدیوبهویس', 'ویدیو_به_ویس',
}

def is_bot_command_text(text: str) -> bool:
    """فقط وقتی پیام واقعاً دستور است True برمی‌گرداند (نه کلمه داخل جمله)."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if not t:
        return False
    # متن بلند = دستور نیست (حداکثر ~12 کلمه / 120 کاراکتر برای دستورات معمولی)
    if len(t) > 180 or len(t.split()) > 15:
        # استثنا: بکاپ و اسپم و استیکر متن و یادگیری با آرگومان
        if not t.startswith(('بکاپ ', 'بکاب ', 'اسپم ', 'استیکر متن', 'یادگیری ', 'منشی ', 'افزودن پاسخ', 'ترجمه ')):
            return False
    # دستورات چندکلمه‌ای شناخته‌شده
    multi_starts = (
        'پنل کاربر', 'تغییر پروفایل', 'تغییر اسم', 'تغییر بیو', 'ساعت در بیو',
        'بیو تاریخ', 'بیو کامل', 'بیو عاشقانه', 'بیو ایموجی', 'بیو فصل',
        'بیو روز هفته', 'بیو شمارش معکوس', 'بیو متن دلخواه', 'اتمام متن',
        'اتمام اسپم', 'اضافه اسپم', 'پاک کردن اسپم', 'حذف اسپم', 'لیست اسپم',
        'لیست دشمن', 'لیست پاسخ', 'پاک کردن پاسخ', 'افزودن پاسخ', 'حذف پاسخ',
        'گروه گزارش', 'تنظیم گزارش', 'تنظیم اسپم', 'سلف روشن', 'سلف خاموش',
        'اسپم روشن', 'اسپم خاموش', 'تگ همه', 'لغو تگ', 'تگ ادمین', 'قلب پیشرفته',
        'خروج سرچ', 'من کی ام', 'ایدی عددی', 'آیدی عددی', 'ساخت استیکر', 'استیکر متن',
        'ترجمه به', 'یادگیری روشن', 'یادگیری خاموش', 'یادگیری حذف', 'یادگیری لیست',
        'بکاپ روشن', 'بکاپ خاموش', 'منشی روشن', 'منشی خاموش',
        '.بن', '.انبن',
        'اکشن تایپ', 'اکشن ویس', 'اکشن ویدیو', 'اکشن عکس',
        'اکشن فیلم', 'اکشن فایل', 'اکشن بازی', 'اکشن استیکر',
        'اکشن موقعیت', 'اکشن تماس', 'اکشن صحبت', 'اکشن خاموش', 'اکشن لیست',
        'نشستهای فعال', 'نشست های فعال', 'نشست‌های فعال',
        'فیلتر روشن', 'فیلتر خاموش', 'فیلتر لیست', 'فیلتر حذف',
        'ساعت روشن', 'ساعت خاموش', 'ساعت رنگ',
        'ویدیو به ویس', 'ویدیو به صدا',
    )
    for m in multi_starts:
        if t == m or t.startswith(m + ' '):
            return True
    parts = t.split()
    cmd = parts[0]
    if cmd not in COMMAND_ROOTS and not cmd.startswith('.'):
        return False
    # دستورات تک‌کلمه‌ای حساس: فقط اگر کل پیام همان دستور باشد (یا فقط با آرگومان‌های کوتاه)
    alone_cmds = {
        'پروف', 'پینگ', 'وضعیت', 'قلب', 'ماه', 'پین', 'درباره', 'تقویم',
        'دارت', 'بسکتبال', 'فوتبال', 'بولینگ', 'یوزرنیم', 'یوزنیم', 'ایدی', 'آیدی',
    }
    if cmd in alone_cmds:
        # پروف / یوزرنیم / ایدی: فقط خود دستور (آرگومان ندارد) — ریپلای جدا چک می‌شود
        if len(parts) > 1:
            # ایدی عددی / آیدی عددی
            if cmd in ('ایدی', 'آیدی') and parts[1] in ('عددی', 'عدد'):
                return len(parts) <= 2
            return False
        return True
    return True

COMMAND_KEYWORDS = tuple(sorted(COMMAND_ROOTS, key=len, reverse=True))


# نگاشت زبان‌های فارسی به کدهای استاندارد ISO که deep_translator تضمینی می‌شناسد
TRANSLATE_LANG_CODES = {
    'english': 'en',
    'arabic': 'ar',
    'hebrew': 'iw',
    'russian': 'ru',
    'turkish': 'tr',
    'german': 'de',
    'french': 'fr',
    'spanish': 'es',
    'italian': 'it',
    'chinese': 'zh-CN',
    'japanese': 'ja',
    'korean': 'ko',
    'hindi': 'hi',
    'persian': 'fa',
}
LANG_NAME_FA = {
    'english': 'انگلیسی', 'arabic': 'عربی', 'hebrew': 'عبری', 'russian': 'روسی',
    'turkish': 'ترکی', 'german': 'آلمانی', 'french': 'فرانسوی', 'spanish': 'اسپانیایی',
    'italian': 'ایتالیایی', 'chinese': 'چینی', 'japanese': 'ژاپنی', 'korean': 'کره‌ای',
    'hindi': 'هندی', 'persian': 'فارسی',
}
FA_TO_LANG = {
    'انگلیسی': 'english', 'عربی': 'arabic', 'عبری': 'hebrew', 'روسی': 'russian',
    'ترکی': 'turkish', 'آلمانی': 'german', 'فرانسوی': 'french', 'اسپانیایی': 'spanish',
    'ایتالیایی': 'italian', 'چینی': 'chinese', 'ژاپنی': 'japanese', 'کره‌ای': 'korean',
    'هندی': 'hindi', 'فارسی': 'persian',
}

async def apply_text_style(message_text, style):
    if not message_text or not style:
        return message_text, []
    entities = []
    if style == 'بولد':
        entities.append(MessageEntityBold(offset=0, length=len(message_text)))
    elif style == 'زیرخط':
        entities.append(MessageEntityUnderline(offset=0, length=len(message_text)))
    elif style == 'خط خورده':
        entities.append(MessageEntityStrike(offset=0, length=len(message_text)))
    elif style == 'نقل قول':
        entities.append(MessageEntityBlockquote(offset=0, length=len(message_text)))
    elif style == 'اسپویلر':
        entities.append(MessageEntitySpoiler(offset=0, length=len(message_text)))
    elif style == 'کج':
        entities.append(MessageEntityItalic(offset=0, length=len(message_text)))
    elif style == 'کد':
        entities.append(MessageEntityCode(offset=0, length=len(message_text)))
    elif style == 'پیش':
        entities.append(MessageEntityPre(offset=0, length=len(message_text), language=""))
    return message_text, entities

async def get_target_user(event, client=None):
    try:
        if event.is_reply:
            replied_msg = await event.get_reply_message()
            return replied_msg.sender_id
        elif client and isinstance(event.message.peer_id, PeerUser) and not event.is_reply:
            return event.message.peer_id.user_id
        return None
    except:
        return None

async def _wrap_edit(message, text: str):
    try:
        await message.edit(text)
    except FloodWaitError as fl:
        await asyncio.sleep(fl.seconds)

async def advanced_heart_phase1(message):
    BIG_SCROLL = "🧡💛💚💙💜🖤🤎"
    await _wrap_edit(message, JOINED_HEART)
    for heart in BIG_SCROLL:
        await _wrap_edit(message, JOINED_HEART.replace(R, heart))
        await asyncio.sleep(SLEEP)

async def advanced_heart_phase2(message):
    ALL = ["❤️"] + list("🧡💛💚💙💜🤎🖤")
    format_heart = JOINED_HEART.replace(R, "{}")
    for _ in range(5):
        heart = format_heart.format(*random.choices(ALL, k=HEARTLET_LEN))
        await _wrap_edit(message, heart)
        await asyncio.sleep(SLEEP)

async def advanced_heart_phase3(message):
    await _wrap_edit(message, JOINED_HEART)
    await asyncio.sleep(SLEEP * 2)
    repl = JOINED_HEART
    for _ in range(JOINED_HEART.count(W)):
        repl = repl.replace(W, R, 1)
        await _wrap_edit(message, repl)
        await asyncio.sleep(SLEEP)

async def advanced_heart_phase4(message):
    for i in range(7, 0, -1):
        heart_matrix = "\n".join([R * i] * i)
        await _wrap_edit(message, heart_matrix)
        await asyncio.sleep(SLEEP)

async def advanced_heart_animation(message):
    await advanced_heart_phase1(message)
    await asyncio.sleep(SLEEP * 3)
    await advanced_heart_phase2(message)
    await asyncio.sleep(SLEEP * 2)
    await advanced_heart_phase3(message)
    await asyncio.sleep(SLEEP * 2)
    await advanced_heart_phase4(message)
    await asyncio.sleep(0.5)
    await message.edit("❤️ I")
    await asyncio.sleep(0.5)
    await message.edit("❤️ I Love")
    await asyncio.sleep(0.5)
    await message.edit("❤️ I Love You")
    await asyncio.sleep(3)
    await message.edit("❤️ I Love You <3")


def find_ffmpeg_bin():
    """پیدا کردن مسیر ffmpeg در محیط‌های مختلف (Railway/Docker/local)"""
    import shutil
    candidates = [
        shutil.which("ffmpeg"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/bin/ffmpeg",
        "/nix/var/nix/profiles/default/bin/ffmpeg",
        os.environ.get("FFMPEG_PATH"),
    ]
    for p in candidates:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    return None

class SelfBotManager:
    def __init__(self, user_id):
        self.user_id = int(user_id)
        self.client = None
        self.running = False
        self.my_id = None
        self.BASE_NAME = None
        self.ORIGINAL_NAME = None
        self.spam_tasks = {}
        self.report_config = ReportConfig(user_id)
        self.adding_spam = False
        self.spam_counters = {}
        self.mute_timestamps = {}
        self.current_chat_id = None
        self.active_actions = {}
        self.action_tasks = {}
        self.translate_mode = {
            "english": False, "arabic": False, "hebrew": False, "russian": False,
            "turkish": False, "german": False, "french": False, "spanish": False,
            "italian": False, "chinese": False, "japanese": False, "korean": False,
            "hindi": False, "persian": False,
        }
        # ترجمه مخصوص یک کاربر (پنل کاربر): target_id -> {lang: bool}
        self.per_user_translate = {}
        self.search_mode = False
        self.last_search_results = []
        self.connection_attempts = 0
        self.max_attempts = 5
        self._handlers_set = False
        self.panel_mode = True
        self.api_id = None
        self.api_hash = None
        self.time_font_cycle = 0
        self.time_font_indices = 'all'
        self.reconnect_task = None
        self.last_ping = 0
        self.keepalive_running = False
        self.last_error_time = 0
        self.error_count = 0
        self.last_keepalive_check = 0
        self.autosend_mode = False
        self.monshi_mode = False
        self.monshi_answer = ""
        self.monshi_step = None  # None | 'wait_text' | 'collecting'
        self.monshi_draft = ""
        self.learning_step = None  # None | 'wait_answer'
        self.learning_question = None
        self.learning_enabled = True
        self.backup_enabled = False
        self.backup_step = None
        self.mentioning_groups = set()
        self.current_bio = self.load_bio()
        self.auto_comment_settings = {}
        self.auto_comment_sent = set()
        self.STATE_FILE = f'state_{user_id}.json'
        self.load_state()
    
    def load_state(self):
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.autosend_mode = data.get('autosend_mode', False)
                    auto_comment_settings = data.get('auto_comment_settings', {})
                    self.auto_comment_settings = {int(k): v for k, v in auto_comment_settings.items()}
                    self.auto_comment_sent = set(data.get('auto_comment_sent', []))
                    logger.info(f"وضعیت کاربر {self.user_id} از فایل بارگذاری شد")
        except Exception as e:
            logger.error(f"خطا در بارگذاری وضعیت: {e}")
    
    def save_state(self):
        try:
            data = {
                'autosend_mode': self.autosend_mode,
                'auto_comment_settings': {str(k): v for k, v in self.auto_comment_settings.items()},
                'auto_comment_sent': list(self.auto_comment_sent)
            }
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"وضعیت کاربر {self.user_id} ذخیره شد")
        except Exception as e:
            logger.error(f"خطا در ذخیره وضعیت: {e}")
    
    def load_bio(self):
        try:
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT bio_text FROM user_bio WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (self.user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else ""
        except:
            return ""
    
    def save_bio(self, bio_text):
        try:
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO user_bio (user_id, bio_text) VALUES (?, ?)', (self.user_id, bio_text))
            conn.commit()
            conn.close()
            self.current_bio = bio_text
        except Exception as e:
            logger.error(f"خطا در ذخیره بیو: {e}")
    
    def get_bio_setting(self, setting_name):
        return db.get_bio_setting(self.user_id, setting_name)
    
    def set_bio_setting(self, setting_name, status):
        db.set_bio_setting(self.user_id, setting_name, status)
    
    async def ensure_original_bio_saved(self):
        """اولین بار بیو اصلی اکانت را ذخیره کن تا موقع خاموش کردن برگردد"""
        try:
            if self.current_bio is not None and str(self.current_bio).strip() != "":
                return
            if not self.client or not self.client.is_connected():
                return
            me = await self.client.get_me()
            full = await self.client(GetFullUserRequest(me.id))
            about = ""
            try:
                about = full.full_user.about or ""
            except Exception:
                about = getattr(full, 'about', None) or ""
            # فقط اگر هیچ افزونه بیویی روشن نباشد، این را به‌عنوان بیو اصلی ذخیره کن
            any_on = any(
                self.get_bio_setting(n) == 'روشن'
                for n in (
                    'ساعت_در_بیو', 'ساعت_در_بیو_۲', 'بیو_تاریخ', 'بیو_کامل',
                    'بیو_عاشقانه', 'بیو_ایموجی', 'بیو_فصل', 'بیو_روز_هفته',
                    'بیو_شمارش_معکوس', 'بیو_متن_دلخواه'
                )
            )
            if not any_on:
                self.save_bio(about or "")
        except Exception as e:
            logger.debug(f"ensure_original_bio: {e}")

    async def update_bio_with_settings(self):
        try:
            if not self.client or not self.client.is_connected():
                logger.warning(f"کلاینت برای کاربر {self.user_id} متصل نیست")
                return

            await self.ensure_original_bio_saved()
            bio_text = self.current_bio or ""

            time1 = self.get_bio_setting('ساعت_در_بیو') == 'روشن'
            time2 = self.get_bio_setting('ساعت_در_بیو_۲') == 'روشن'
            date = self.get_bio_setting('بیو_تاریخ') == 'روشن'
            full = self.get_bio_setting('بیو_کامل') == 'روشن'
            love = self.get_bio_setting('بیو_عاشقانه') == 'روشن'
            random_emoji_bio = self.get_bio_setting('بیو_ایموجی') == 'روشن'
            season = self.get_bio_setting('بیو_فصل') == 'روشن'
            weekday_bio = self.get_bio_setting('بیو_روز_هفته') == 'روشن'
            countdown = self.get_bio_setting('بیو_شمارش_معکوس') == 'روشن'
            custom_text = self.get_bio_setting('بیو_متن_دلخواه') == 'روشن'

            any_on = any([time1, time2, date, full, love, random_emoji_bio, season, weekday_bio, countdown, custom_text])

            if not any_on:
                # همه خاموش → بیو اصلی یا خالی (حذف افزودنی‌ها از بیوگرافی)
                new_bio = bio_text or ""
                await self.client(UpdateProfileRequest(about=new_bio[:70] if new_bio else " "))
                # یک فاصله اجباری سپس خالی برای اطمینان از پاک شدن در برخی کلاینت‌ها
                if not new_bio:
                    await asyncio.sleep(0.3)
                    await self.client(UpdateProfileRequest(about=""))
                logger.info(f"بیو پاک/بازیابی شد برای {self.user_id}")
                return

            if full:
                new_bio = f'{moon_or_sun()} | {bio_text} | {create_time2()} | {create_tarikh2()} | {get_weekday()} | {get_season()}'
            elif date:
                new_bio = f'{moon_or_sun()} | {bio_text} | {create_time2()} | {create_tarikh2()}'
            elif love:
                new_bio = f'{love_emoji()} | {bio_text} | {create_time2()} | {create_tarikh()}'
            elif time2:
                new_bio = f'{bio_text} | {create_time2()}'
            elif time1:
                new_bio = f'{bio_text} | {create_time()}'
            elif random_emoji_bio:
                new_bio = f'{random_emoji()} {bio_text} {random_emoji()} | {create_time()}'
            elif season:
                new_bio = f'{get_season()} | {bio_text} | {create_time()}'
            elif weekday_bio:
                new_bio = f'{get_weekday()} | {bio_text} | {create_time()}'
            elif countdown:
                now = get_now()
                try:
                    target = datetime(now.year + 1, 3, 21)
                    if getattr(now, 'tzinfo', None):
                        target = target.replace(tzinfo=now.tzinfo)
                    diff = target - now
                    days = getattr(diff, 'days', 0)
                except Exception:
                    days = 0
                new_bio = f'{bio_text} | ⏳ {days} روز تا سال نو'
            elif custom_text:
                custom = self.get_bio_setting('بیو_متن_دلخواه_متن') or ""
                new_bio = f'{custom} | {bio_text} | {create_time()}'
            else:
                new_bio = bio_text or ""

            await self.client(UpdateProfileRequest(about=(new_bio or "")[:70]))
            logger.info(f"بیو به‌روزرسانی شد: {(new_bio or '(خالی)')[:50]}...")
        except Exception as e:
            logger.error(f"خطا در به‌روزرسانی بیو: {e}\n{traceback.format_exc()}")
    
    async def fortune_telling(self, chat_id, event=None):
        fortune = random.choice(fortunes)
        emoji = random.choice(['🌟', '💫', '🌙', '🌸', '💰', '🎯', '🌈', '💪', '🎉', '💖'])
        
        text = f"""
{emoji} **فال امروز تو** {emoji}
━━━━━━━━━━━━━━━━━━━━

{fortune}

━━━━━━━━━━━━━━━━━━━━
💫 باور داشته باش که بهترین‌ها در راهند!
        """
        
        if event:
            await event.edit(text, parse_mode='markdown')
        else:
            await self.client.send_message(chat_id, text)
    
    async def hafez_fortune(self, chat_id, event=None):
        text, emoji = random.choice(hafez_fortunes)
        
        msg = f"""
🕌 **فال حافظ** 🕌
━━━━━━━━━━━━━━━━━━━━

{emoji} {text}

━━━━━━━━━━━━━━━━━━━━
"زین قفس چون برفتم، آزادم" 🕊️
        """
        
        if event:
            await event.edit(msg, parse_mode='markdown')
        else:
            await self.client.send_message(chat_id, msg)
    
    async def coffee_fortune(self, chat_id, event=None):
        fortune = random.choice(coffee_fortunes)
        
        msg = f"""
☕ **فال قهوه** ☕
━━━━━━━━━━━━━━━━━━━━

{fortune}

━━━━━━━━━━━━━━━━━━━━
☕ قهوه‌ات را بنوش و به فردا امیدوار باش!
        """
        
        if event:
            await event.edit(msg, parse_mode='markdown')
        else:
            await self.client.send_message(chat_id, msg)
    
    async def auto_sync_message(self, event):
        if self.autosend_mode and isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            try:
                await event.message.mark_read()
                logger.debug(f"اتوسین: پیام {event.message.id} سین شد")
            except Exception as e:
                logger.error(f"خطا در اتوسین: {e}")
    
    def set_auto_comment(self, channel_id, comment_text, channel_title, channel_type, channel_username):
        self.auto_comment_settings[channel_id] = {
            'text': comment_text,
            'title': channel_title,
            'type': channel_type,
            'username': channel_username
        }
        self.save_state()
        return f"متن کامنت تنظیم شد: {comment_text[:30]}..."
    
    def get_auto_comments(self):
        return self.auto_comment_settings
    
    def remove_auto_comment(self, channel_id):
        if channel_id in self.auto_comment_settings:
            title = self.auto_comment_settings[channel_id]['title']
            del self.auto_comment_settings[channel_id]
            self.save_state()
            return f"تنظیمات {title} حذف شد"
        return "این کانال تنظیم نشده است"
    
    async def auto_comment_handler(self, event):
        try:
            message = event.message
            if not is_channel_post(message):
                return
            chat = await message.get_chat()
            cid = chat.id
            if cid not in self.auto_comment_settings:
                return
            post_key = f"{cid}_{message.id}"
            if post_key in self.auto_comment_sent:
                return
            config = self.auto_comment_settings[cid]
            await asyncio.sleep(0.5)
            await self.client.send_message(
                chat.id,
                config['text'],
                reply_to=message.id
            )
            self.auto_comment_sent.add(post_key)
            self.save_state()
            logger.info(f"✅ نظر ارسال شد به پست {message.id} در کانال {config['title']}")
        except Exception as e:
            logger.error(f"خطا در ارسال نظر اتوماتیک: {e}")
    
    async def start(self, session_file):
        try:
            if self.running and self.client and self.client.is_connected():
                logger.info(f"سلف‌بات برای کاربر {self.user_id} از قبل در حال اجراست")
                return True
                
            self.connection_attempts += 1
            logger.info(f"شروع سلف‌بات برای کاربر {self.user_id} - تلاش {self.connection_attempts}")
            
            if not os.path.exists(session_file):
                logger.error(f"فایل سشن یافت نشد: {session_file}")
                return False
            
            user_api = get_user_api(str(self.user_id))
            if not user_api:
                logger.error(f"هیچ API ای برای کاربر {self.user_id} یافت نشد")
                return False
            
            self.api_id = user_api["api_id"]
            self.api_hash = user_api["api_hash"]
            
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            self.client = TelegramClient(
                session_file, 
                self.api_id, 
                self.api_hash,
                connection_retries=10,
                retry_delay=3,
                timeout=60,
                flood_sleep_threshold=60,
                device_model="SelfBot",
                system_version="4.8.0",
                app_version="4.8.0"
            )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.error(f"کاربر {self.user_id} احراز هویت نشده است")
                return False
            
            me = await self.client.get_me()
            if not me:
                logger.error(f"خطا در دریافت اطلاعات کاربر {self.user_id}")
                return False
                
            self.my_id = me.id
            self.BASE_NAME = me.first_name or "Self-Bot"
            
            logger.info(f"اطلاعات کاربر {self.user_id}: {self.BASE_NAME} (ID: {self.my_id}) | API: {self.api_id}")
            
            original_name = db.get_original_name(self.user_id)
            if not original_name:
                db.set_original_name(self.user_id, self.BASE_NAME)
                db.set_current_name(self.user_id, self.BASE_NAME)
                self.ORIGINAL_NAME = self.BASE_NAME
            else:
                self.ORIGINAL_NAME = original_name
            
            settings = db.get_selfbot_settings(self.user_id)
            _tdef = {
                "english": False, "arabic": False, "hebrew": False, "russian": False,
                "turkish": False, "german": False, "french": False, "spanish": False,
                "italian": False, "chinese": False, "japanese": False, "korean": False,
                "hindi": False, "persian": False,
            }
            loaded = settings.get('translate') or {}
            self.translate_mode = {**_tdef, **{k: bool(v) for k, v in loaded.items()}}
            self.panel_mode = settings.get('panel_mode', True)
            self.time_font_indices = settings.get('time_font_indices', 'all')
            self.autosend_mode = settings.get('autosend_mode', False)
            
            monshi_data = db.get_monshi_status(self.user_id)
            self.monshi_mode = monshi_data['status']
            self.monshi_answer = monshi_data['answer']
            try:
                self.learning_enabled = db.get_learning_enabled(self.user_id)
                self.backup_enabled = db.get_backup_enabled(self.user_id)
            except Exception:
                pass
            
            if not self._handlers_set:
                self.setup_handlers()
                self._handlers_set = True
                logger.info(f"هندلرها برای کاربر {self.user_id} تنظیم شدند")
            
            asyncio.create_task(self.update_profile_task())
            asyncio.create_task(self.update_bio_task())
            
            self.running = True
            self.keepalive_running = True
            self.connection_attempts = 0
            self.error_count = 0
            self.last_error_time = 0
            
            asyncio.create_task(self.keep_alive_task())
            
            # ساخت خودکار گروه گزارش در صورت نیاز (اولین ورود)
            try:
                asyncio.create_task(self.ensure_report_group())
            except Exception as e:
                logger.error(f"ensure_report_group schedule: {e}")
            
            logger.info(f"✅ سلف‌بات برای کاربر {self.user_id} با موفقیت شروع شد")
            return True
            
        except Exception as e:
            logger.error(f"خطا در شروع سلف‌بات برای کاربر {self.user_id}: {str(e)}")
            
            if self.connection_attempts < self.max_attempts:
                wait_time = 5 * self.connection_attempts
                logger.info(f"تلاش مجدد در {wait_time} ثانیه برای کاربر {self.user_id} - تلاش {self.connection_attempts + 1}")
                await asyncio.sleep(wait_time)
                return await self.start(session_file)
            
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            return False
    
    async def ensure_report_group(self):
        """اگر گروه گزارش پیش‌فرض است، یک گروه خصوصی «گزارش دهی» می‌سازد،
        آن را سنجاق می‌کند و راهنمای کوتاه می‌فرستد."""
        try:
            current = self.report_config.report_group_id
            # فقط وقتی هنوز گروه پیش‌فرض است یا گروهی وجود ندارد
            if current and current != GROUP_ID and current != 0:
                # بررسی کن گروه هنوز در دسترس است
                try:
                    await self.client.get_entity(current)
                    return  # گروه شخصی از قبل وجود دارد
                except Exception:
                    pass  # گروه قبلی از بین رفته → دوباره بساز
            
            logger.info(f"در حال ساخت گروه گزارش برای کاربر {self.user_id}...")
            result = await self.client(CreateChannelRequest(
                title="گزارش دهی",
                about="گروه اختصاصی گزارش‌های سلف‌بات VROOM\nپیام‌های حذف‌شده، ویرایش‌شده و رسانه‌ها اینجا ذخیره می‌شوند.",
                megagroup=True
            ))
            if not result or not result.chats:
                logger.error("CreateChannelRequest نتیجه خالی برگرداند")
                return
            new_chat = result.chats[0]
            # آیدی کامل سوپرگروه
            full_id = int(f"-100{new_chat.id}")
            self.report_config.set_report_group(full_id)
            # ذخیره در تنظیمات سلف‌بات هم
            try:
                db.update_selfbot_setting(self.user_id, 'report_group_id', full_id)
            except Exception:
                pass
            
            guide = (
                "📌 **گروه گزارش‌دهی اختصاصی شما**\n\n"
                "از این لحظه تمام گزارش‌های سلف‌بات (پیام‌های حذف‌شده، ویرایش‌شده، رسانه‌ها و ...) "
                "در همین گروه ارسال می‌شوند.\n\n"
                "🔧 راهنمای سریع:\n"
                "• برای تغییر گروه گزارش: داخل گروه موردنظر دستور `تنظیم گزارش` را بزنید.\n"
                "• می‌توانید یک کانال سیو مسیج یا گروه دیگری هم تنظیم کنید.\n"
                "• برای دیدن گروه فعلی: `گروه گزارش`\n\n"
                "✅ این گروه برای شما سنجاق شده است."
            )
            try:
                await self.client.send_message(full_id, guide)
            except Exception as e:
                logger.debug(f"ارسال راهنما: {e}")
            
            # سنجاق کردن چت (اگر لیست پین پر بود یکی را از پین دربیاور)
            try:
                peer = await self.client.get_input_entity(full_id)
                # ابتدا سعی در پین
                try:
                    await self.client(ToggleDialogPinRequest(peer=peer, pinned=True))
                except Exception as pin_err:
                    # احتمالاً سقف پین پر است → یکی از پین‌های موجود را باز کن
                    logger.debug(f"پین اول ناموفق: {pin_err}")
                    try:
                        dialogs = await self.client.get_dialogs(limit=30)
                        pinned = [d for d in dialogs if getattr(d, 'pinned', False)]
                        if pinned:
                            # قدیمی‌ترین پین را باز کن
                            old = pinned[-1]
                            old_peer = await self.client.get_input_entity(old.entity)
                            await self.client(ToggleDialogPinRequest(peer=old_peer, pinned=False))
                            await asyncio.sleep(0.5)
                            await self.client(ToggleDialogPinRequest(peer=peer, pinned=True))
                    except Exception as e2:
                        logger.debug(f"آزادسازی پین: {e2}")
            except Exception as e:
                logger.debug(f"سنجاق گروه گزارش: {e}")
            
            logger.info(f"✅ گروه گزارش {full_id} برای کاربر {self.user_id} ساخته و تنظیم شد")
        except Exception as e:
            logger.error(f"ensure_report_group error for {self.user_id}: {e}\n{traceback.format_exc()}")
    
    async def keep_alive_task(self):
        reconnect_attempts = 0
        while self.running and self.keepalive_running:
            try:
                await asyncio.sleep(30)
                
                if not self.running:
                    break
                
                if self.client and self.client.is_connected():
                    try:
                        await self.client.get_me()
                        self.last_ping = time.time()
                        self.error_count = 0
                        reconnect_attempts = 0
                        logger.debug(f"Keepalive برای کاربر {self.user_id} موفق")
                    except Exception as e:
                        self.error_count += 1
                        self.last_error_time = time.time()
                        logger.warning(f"خطا در keepalive برای کاربر {self.user_id} ({self.error_count}): {e}")
                        
                        if self.error_count >= 3:
                            logger.warning(f"تلاش مجدد برای کاربر {self.user_id} بعد از {self.error_count} خطا")
                            reconnect_attempts += 1
                            await self.reconnect()
                else:
                    logger.warning(f"اتصال کاربر {self.user_id} قطع شده، تلاش برای reconnect...")
                    reconnect_attempts += 1
                    await self.reconnect()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"خطا در keep_alive_task برای کاربر {self.user_id}: {e}")
                reconnect_attempts += 1
                await asyncio.sleep(60)
    
    async def reconnect(self):
        try:
            logger.info(f"شروع reconnect برای کاربر {self.user_id}")
            
            user_data = db.get_user(str(self.user_id))
            if not user_data or not user_data.get('session_file'):
                logger.error(f"فایل سشن برای کاربر {self.user_id} یافت نشد")
                return False
            
            session_file = user_data['session_file']
            
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            self.running = False
            self._handlers_set = False
            
            await asyncio.sleep(5)
            
            attempt = 0
            while True:
                attempt += 1
                logger.info(f"تلاش reconnect {attempt} برای کاربر {self.user_id}")
                
                if await self.start(session_file):
                    logger.info(f"✅ reconnect برای کاربر {self.user_id} موفقیت‌آمیز بود")
                    return True
                
                wait_time = min(attempt * 10, 300)
                logger.info(f"تلاش reconnect {attempt} ناموفق بود، صبر {wait_time} ثانیه...")
                await asyncio.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"خطا در reconnect برای کاربر {self.user_id}: {e}")
            return False
    
    async def stop(self):
        try:
            self.running = False
            self.keepalive_running = False
            
            settings = db.get_selfbot_settings(self.user_id)
            settings['panel_mode'] = self.panel_mode
            db.set_selfbot_settings(self.user_id, settings)
            
            if self.client:
                for task in self.spam_tasks.values():
                    task.cancel()
                self.spam_tasks.clear()
                
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            self._handlers_set = False
            logger.info(f"✅ سلف‌بات برای کاربر {self.user_id} متوقف شد")
            
        except Exception as e:
            logger.error(f"خطا در توقف سلف‌بات برای کاربر {self.user_id}: {e}")
    
    def setup_handlers(self):
        try:
            @self.client.on(events.NewMessage(incoming=True))
            async def handle_new_message(event):
                if not self.running:
                    return
                await self.handle_new_message(event)
            
            @self.client.on(events.MessageEdited(incoming=True))
            async def handle_edited_message(event):
                if not self.running:
                    return
                await self.handle_edited_message(event)
            
            @self.client.on(events.MessageDeleted)
            async def handle_deleted_message(event):
                if not self.running:
                    return
                await self.handle_deleted_message(event)
            
            @self.client.on(events.NewMessage(outgoing=True))
            async def handle_outgoing_message(event):
                if not self.running:
                    return
                await self.handle_outgoing_message(event)
            
            @self.client.on(events.NewMessage())
            async def auto_comment_handler(event):
                if not self.running:
                    return
                await self.auto_comment_handler(event)
            
            @self.client.on(events.NewMessage())
            async def report_handler(event):
                if not self.running:
                    return
                await self.handle_report_message(event)
            
            @self.client.on(events.NewMessage(outgoing=True))
            async def handle_commands(event):
                if not self.running:
                    return
                await self.handle_commands(event)
                
        except Exception as e:
            logger.error(f"خطا در تنظیم هندلرها برای کاربر {self.user_id}: {e}")
    
    async def handle_commands(self, event):
        if event.sender_id != self.my_id:
            return
        if not event.text:
            return
        
        raw_text = event.text.strip()
        command_text = raw_text.replace('\u200c', '')  # ZWNJ
        command_text = command_text.replace(chr(0x200c), '')
        if not command_text:
            return
        if not is_bot_command_text(command_text) and not is_bot_command_text(raw_text):
            return
        
        parts = command_text.split()
        if not parts:
            return
        
        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        # بن / انبن فقط ادمین
        if cmd in ('.بن', '.انبن', 'بن', 'انبن') or command_text.strip() in ('.بن', '.انبن'):
            if not is_admin(self.user_id) and not is_admin(getattr(self, 'my_id', 0) or 0):
                return
            if not event.is_reply:
                await event.edit('⚠️ روی پیام کاربر ریپلای کنید')
                return
            try:
                rm = await event.get_reply_message()
                target = await rm.get_sender()
                tid = int(target.id) if target else None
                if not tid:
                    await event.edit('❌ کاربر پیدا نشد')
                    return
                if cmd in ('.بن', 'بن') or command_text.strip().startswith('.بن'):
                    # حفظ کامل دیتابیس و سشن — فقط خاموش
                    db.ban_user(tid, 'self_off')
                    try:
                        db.update_selfbot_setting(tid, 'selfbot_enabled', 0)
                    except Exception:
                        pass
                    # اطمینان از ماندن session_file در دیتابیس
                    try:
                        ud = db.get_user(str(tid)) or {}
                        if not ud.get('session_file'):
                            sf = find_session_file(tid)
                            if sf:
                                db.update_user(str(tid), session_file=sf, self_active=0)
                            else:
                                db.update_user(str(tid), self_active=0)
                        else:
                            db.update_user(str(tid), self_active=0)
                    except Exception:
                        pass
                    mgr = selfbot_managers.get(str(tid))
                    bye_txt = (
                        "⛔ سلف‌بات شما توسط مدیریت خاموش شد.\n"
                        "اکانت حذف نشده؛ با دستور ادمین دوباره فعال می‌شود.\n"
                        f"🆔 `{tid}`"
                    )
                    # پیام از اکانت کاربر، در همین گروه، با ریپلای روی پیام ادمین
                    sent_ok = False
                    if mgr and getattr(mgr, 'client', None):
                        try:
                            if mgr.client.is_connected():
                                peer = event.chat_id
                                await mgr.client.send_message(
                                    peer,
                                    bye_txt,
                                    reply_to=event.id
                                )
                                sent_ok = True
                        except Exception as e:
                            logger.debug(f"ban msg in group from target: {e}")
                            try:
                                await mgr.client.send_message(event.chat_id, bye_txt)
                                sent_ok = True
                            except Exception as e2:
                                logger.debug(f"ban msg fallback: {e2}")
                        mgr.running = False
                        mgr.keepalive_running = False
                    if not sent_ok:
                        # fallback: ادمین خودش در گروه با ریپلای می‌فرستد
                        try:
                            await self.client.send_message(
                                event.chat_id,
                                bye_txt,
                                reply_to=event.id
                            )
                        except Exception:
                            try:
                                await event.reply(bye_txt)
                            except Exception:
                                pass
                    try:
                        await event.edit(f'⛔ سلف `{tid}` خاموش شد (سشن حفظ شد)')
                    except Exception:
                        pass
                else:
                    # .انبن
                    db.unban_user(tid)
                    try:
                        db.update_selfbot_setting(tid, 'selfbot_enabled', 1)
                    except Exception:
                        pass
                    sf = find_session_file(tid)
                    if sf:
                        try:
                            db.update_user(str(tid), self_active=1, session_file=sf)
                        except Exception:
                            db.update_user(str(tid), self_active=1)
                    else:
                        db.update_user(str(tid), self_active=1)
                    thanks = (
                        "✅ سلف‌بات شما دوباره توسط مدیریت فعال شد.\n"
                        f"🆔 `{tid}`"
                    )
                    started = False
                    err_msg = ''
                    try:
                        if sf:
                            if str(tid) not in selfbot_managers:
                                selfbot_managers[str(tid)] = SelfBotManager(tid)
                            m2 = selfbot_managers[str(tid)]
                            if getattr(m2, 'client', None) and m2.client.is_connected():
                                m2.running = True
                                m2.keepalive_running = True
                                started = True
                            else:
                                ok = await m2.start(str(sf))
                                started = bool(ok)
                            # پیام تشکر در همین گروه با ریپلای، از اکانت کاربر
                            if started and m2.client and m2.client.is_connected():
                                try:
                                    await m2.client.send_message(
                                        event.chat_id, thanks, reply_to=event.id
                                    )
                                except Exception:
                                    try:
                                        await m2.client.send_message(event.chat_id, thanks)
                                    except Exception:
                                        pass
                        else:
                            err_msg = ' — سشن در پوشه/دیتابیس یافت نشد'
                    except Exception as e:
                        err_msg = f' — {e}'
                        logger.debug(f"unban restart: {e}")
                    try:
                        await event.edit(
                            f'✅ سلف `{tid}` دوباره فعال شد'
                            + (' ✓' if started else err_msg or ' — استارت نشد')
                        )
                    except Exception:
                        pass
            except Exception as e:
                await event.edit(f'❌ خطا: {e}')
            return

        chat_id = None
        if isinstance(event.message.peer_id, PeerUser):
            chat_id = event.message.peer_id.user_id
        elif isinstance(event.message.peer_id, PeerChannel):
            chat_id = event.message.peer_id.channel_id
        elif isinstance(event.message.peer_id, PeerChat):
            chat_id = event.message.peer_id.chat_id
        try:
            if getattr(event, 'chat_id', None):
                chat_id = event.chat_id
        except Exception:
            pass

        # ========== اکشن (زود — قبل از بقیه تا حتماً اجرا شود) ==========
        if cmd == 'اکشن' or command_text.startswith('اکشن '):
            action_name = ' '.join(args).strip() if args else ''
            if cmd == 'اکشن' and not action_name and len(parts) > 1:
                action_name = ' '.join(parts[1:]).strip()
            target = chat_id
            try:
                if event.chat_id:
                    target = event.chat_id
            except Exception:
                pass
            if not action_name:
                avail = '، '.join(action_types.keys())
                msg = f'⚠️ فرمت: اکشن [نام]\nمثال: اکشن تایپ\n\n{avail}'
                try:
                    await event.edit(msg)
                except Exception:
                    await event.reply(msg)
                return
            if action_name in ('خاموش', 'قطع', 'stop', 'off'):
                stopped = await self.stop_action(target)
                msg = f'✅ اکشن {stopped} خاموش شد' if stopped else '❌ اکشن فعالی نیست'
                try:
                    await event.edit(msg)
                except Exception:
                    await event.reply(msg)
                return
            if action_name in ('لیست', 'وضعیت', 'list'):
                if self.active_actions:
                    lines_a = [f'• {c}: {a}' for c, a in self.active_actions.items()]
                    txt = '🎭 اکشن‌های فعال:\n' + '\n'.join(lines_a)
                else:
                    txt = '📭 هیچ اکشنی فعال نیست'
                try:
                    await event.edit(txt)
                except Exception:
                    await event.reply(txt)
                return
            if action_name in action_types:
                if target in self.active_actions:
                    await self.stop_action(target)
                ok = await self.start_action(target, action_name)
                msg = f'✅ اکشن {action_name} فعال شد' if ok else f'❌ اکشن {action_name} اجرا نشد'
                try:
                    await event.edit(msg)
                except Exception:
                    try:
                        await event.reply(msg)
                    except Exception:
                        pass
                return
            avail = '\n'.join(f'• اکشن {n}' for n in action_types.keys())
            msg = f'❌ نامعتبر: {action_name}\n\n{avail}\n• اکشن خاموش\n• اکشن لیست'
            try:
                await event.edit(msg)
            except Exception:
                await event.reply(msg)
            return
        # ========== تنظیمات بیو (اصلاح شده) ==========
        bio_commands = {
            'ساعت در بیو': 'ساعت_در_بیو',
            'ساعت در بیو ۲': 'ساعت_در_بیو_۲',
            'بیو تاریخ': 'بیو_تاریخ',
            'بیو کامل': 'بیو_کامل',
            'بیو عاشقانه': 'بیو_عاشقانه',
            'بیو ایموجی': 'بیو_ایموجی',
            'بیو فصل': 'بیو_فصل',
            'بیو روز هفته': 'بیو_روز_هفته',
            'بیو شمارش معکوس': 'بیو_شمارش_معکوس',
            'بیو متن دلخواه': 'بیو_متن_دلخواه',
        }
        
        for bio_cmd, setting_name in bio_commands.items():
            if command_text.startswith(bio_cmd + " "):
                rest = command_text[len(bio_cmd) + 1:].strip()
                if rest in ['روشن', 'خاموش']:
                    status = rest
                    self.set_bio_setting(setting_name, status)
                    # همیشه بیو را به‌روز کن (روشن یا خاموش)
                    await self.update_bio_with_settings()
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    return
        
        # ========== فال ==========
        if cmd == 'فال' and not args:
            await self.fortune_telling(chat_id, event)
            return
        
        if cmd == 'فال' and args and args[0] == 'حافظ' and len(args) == 1:
            await self.hafez_fortune(chat_id, event)
            return
        
        if cmd == 'فال' and args and args[0] == 'قهوه' and len(args) == 1:
            await self.coffee_fortune(chat_id, event)
            return
        
        # ========== منشی ==========
        if cmd == 'منشی' and args:
            if args[0] in ('خاموش', 'off', 'غیرفعال'):
                db.set_monshi_status(self.user_id, False, self.monshi_answer or '')
                self.monshi_mode = False
                self.monshi_step = None
                self.monshi_draft = ""
                await event.edit("⛔ منشی خاموش شد")
                return
            if args[0] in ('روشن', 'on', 'فعال'):
                self.monshi_step = 'wait_text'
                self.monshi_draft = ""
                await event.edit(
                    "🤖 منشی روشن — متن پاسخ را بفرستید\n\n"
                    "وقتی تمام شد بنویسید:\n`اتمام متن`\n\n"
                    "مثال:\nسلام! الان در دسترس نیستم."
                )
                return
            answer = ' '.join(args)
            db.set_monshi_status(self.user_id, True, answer)
            self.monshi_mode = True
            self.monshi_answer = answer
            self.monshi_step = None
            await event.edit(f"✅ منشی فعال شد:\n{answer}")
            return

        if cmd == 'اتمام' and args and args[0] == 'متن':
            if self.monshi_step in ('wait_text', 'collecting') or getattr(self, 'monshi_draft', ''):
                answer = (getattr(self, 'monshi_draft', '') or '').strip()
                if not answer:
                    await event.edit("⚠️ هنوز متنی ذخیره نشده. متن را بفرستید بعد `اتمام متن`")
                    return
                db.set_monshi_status(self.user_id, True, answer)
                self.monshi_mode = True
                self.monshi_answer = answer
                self.monshi_step = None
                self.monshi_draft = ""
                await event.edit(f"✅ منشی فعال شد و متن ذخیره شد:\n\n{answer}")
            else:
                await event.edit("⚠️ اول `منشی روشن` بزنید.")
            return

        # ========== یادگیری ==========
        if cmd == 'یادگیری':
            if not args:
                await event.edit("❌ فرمت:\n• یادگیری سلام\n• یادگیری روشن\n• یادگیری خاموش\n• لیست یادگیری")
                return
            if args[0] in ('روشن', 'on'):
                db.set_learning_enabled(self.user_id, True)
                self.learning_enabled = True
                await event.edit("✅ یادگیری روشن شد — پاسخ‌های ذخیره شده ارسال می‌شوند")
                return
            if args[0] in ('خاموش', 'off'):
                db.set_learning_enabled(self.user_id, False)
                self.learning_enabled = False
                await event.edit("⛔ یادگیری خاموش شد")
                return
            if args[0] in ('لیست', 'list'):
                answers = db.get_answers(self.user_id)
                if not answers:
                    await event.edit("📋 لیست یادگیری خالی است")
                    return
                text = "📋 لیست یادگیری:\n\n"
                for i, (q, a) in enumerate(answers.items(), 1):
                    text += f"{i}. ❓ {q}\n   💬 {a}\n\n"
                await event.edit(text[:4000])
                return
            if args[0] in ('حذف',):
                q = ' '.join(args[1:]).strip()
                if q:
                    db.remove_answer(self.user_id, q)
                    await event.edit(f"✅ یادگیری «{q}» حذف شد")
                else:
                    await event.edit("❌ فرمت: یادگیری حذف سلام")
                return
            # یادگیری <کلمه>
            question = ' '.join(args).strip()
            self.learning_step = 'wait_answer'
            self.learning_question = question
            await event.edit(
                f"🧠 یادگیری برای: «{question}»\n\n"
                f"حالا جواب را بفرستید.\n"
                f"مثال: علیک سلام"
            )
            return

        # ========== بکاپ ==========
        if cmd in ('بکاپ', 'بکاب'):
            if not args:
                await event.edit(
                    "📦 راهنمای بکاپ:\n"
                    "• بکاپ روشن / بکاپ خاموش\n"
                    "• بکاپ -1002784754810 10 فیلم\n"
                    "• بکاپ -100xxx 10 عکس\n"
                    "• بکاپ -100xxx 50 متن\n"
                    "• بکاپ -100xxx 20 لینک\n"
                    "• بکاپ -100xxx 100 همه\n"
                    "• بکاپ @username 5 همه\n"
                    "• بکاپ 123456789 10 همه\n\n"
                    "فایل‌ها به گروه گزارش ارسال می‌شوند."
                )
                return
            if args[0] in ('روشن', 'on'):
                db.set_backup_enabled(self.user_id, True)
                self.backup_enabled = True
                await event.edit("✅ بکاپ روشن شد")
                return
            if args[0] in ('خاموش', 'off'):
                db.set_backup_enabled(self.user_id, False)
                self.backup_enabled = False
                await event.edit("⛔ بکاپ خاموش شد")
                return
            # بکاپ <target> <count> [type]
            try:
                target = args[0]
                count = 10
                media_filter = 'همه'
                if len(args) >= 2:
                    try:
                        count = int(str(args[1]).replace('تا', '').replace('آخر', '').strip())
                    except Exception:
                        count = 10
                if len(args) >= 3:
                    media_filter = args[2]
                elif len(args) == 2 and not str(args[1]).isdigit():
                    media_filter = args[1]
                count = max(1, min(count, 1000))
                await event.edit(f"⏳ بکاپ از {target} — {count} مورد ({media_filter})...")
                await self.run_backup(event, target, count, media_filter)
            except Exception as e:
                await event.edit(f"❌ خطا در بکاپ: {e}")
            return

        # ========== پاسخ‌ها ==========
        if cmd == 'افزودن' and args and args[0] == 'پاسخ':
            text = ' '.join(args[1:])
            if ':' in text:
                question, answer = text.split(':', 1)
                db.add_answer(self.user_id, question.strip(), answer.strip())
                await event.edit(f"✅ پاسخ اضافه شد:\nسوال: {question}\nجواب: {answer}")
            else:
                await event.edit("❌ فرمت: افزودن پاسخ سوال:جواب")
            return
        
        if cmd == 'حذف' and args and args[0] == 'پاسخ':
            question = ' '.join(args[1:])
            db.remove_answer(self.user_id, question)
            await event.edit(f"✅ پاسخ '{question}' حذف شد")
            return
        
        if cmd == 'لیست' and args and args[0] in ('پاسخ', 'پاسخ‌ها', 'پاسخها'):
            answers = db.get_answers(self.user_id)
            if not answers:
                answers = db.get_answers(str(self.user_id))
            if answers:
                text = "📋 لیست پاسخ‌ها:\n\n"
                for i, (q, a) in enumerate(answers.items(), 1):
                    text += f"{i}. ❓ {q}\n   💬 {a}\n\n"
                try:
                    await event.edit(text[:3500])
                except Exception:
                    await event.respond(text[:3500])
            else:
                try:
                    await event.edit("❌ هیچ پاسخی ذخیره نشده")
                except Exception:
                    await event.respond("❌ هیچ پاسخی ذخیره نشده")
            return
        
        if cmd == 'پاک' and args and args[0] == 'کردن' and len(args) > 1 and args[1] == 'پاسخ‌ها':
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bot_answers WHERE user_id = ?', (self.user_id,))
            conn.commit()
            conn.close()
            await event.edit("✅ همه پاسخ‌ها پاک شدند")
            return
        
        # ========== تگ همه ==========
        if cmd == 'تگ' and args and args[0] == 'همه':
            chat_id = event.chat_id
            if chat_id in self.mentioning_groups:
                await event.edit("⏳ در حال تگ کردن هستیم...")
                return
            
            self.mentioning_groups.add(chat_id)
            await event.delete()
            
            text = ' '.join(args[1:]) if len(args) > 1 else ""
            count = 0
            mention_text = ""
            total_users = 0
            
            try:
                async for _ in self.client.iter_participants(chat_id):
                    total_users += 1
                
                async for user in self.client.iter_participants(chat_id):
                    if chat_id not in self.mentioning_groups:
                        break
                    if user.id == self.my_id:
                        continue
                    
                    count += 1
                    name = user.first_name or "کاربر"
                    mention_text += f"[{name}](tg://user?id={user.id}) ✧ "
                    
                    if count % 13 == 0:
                        msg = f"{text}\n\n{mention_text}" if text else mention_text
                        await self.client.send_message(chat_id, msg)
                        await asyncio.sleep(1.5)
                        mention_text = ""
                
                if mention_text:
                    msg = f"{text}\n\n{mention_text}" if text else mention_text
                    await self.client.send_message(chat_id, msg)
                
            except Exception as e:
                logger.error(f"خطا در تگ همه: {e}")
            finally:
                self.mentioning_groups.discard(chat_id)
            return
        
        if cmd == 'لغو' and args and args[0] == 'تگ':
            if chat_id in self.mentioning_groups:
                self.mentioning_groups.discard(chat_id)
                await event.edit("✅ تگ کردن لغو شد")
            else:
                await event.edit("❌ هیچ تگی در این گروه فعال نیست")
            return
        
        # ========== بازی‌ها ==========
        if cmd == 'بولینگ':
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("🎳"))
                if msg.media.value == 6:
                    await self.client.send_message(chat_id, "🎉 **بولینگ! ۶ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return
        
        if cmd == 'تاس' and args and args[0].isdigit():
            target = int(args[0])
            if 1 <= target <= 6:
                await event.delete()
                while True:
                    msg = await self.client.send_message(chat_id, file=InputMediaDice("🎲"))
                    if msg.media.value == target:
                        await self.client.send_message(chat_id, f"🎉 **{target} آمد! بردی!**")
                        break
                    await asyncio.sleep(1)
            else:
                await event.edit("❌ عدد بین ۱ تا ۶ وارد کن")
            return
        
        if cmd == 'سه' and args and args[0] == 'رنگ':
            colors = ['🔴', '🟢', '🔵']
            seed = self.user_id
            random.seed(seed)
            user_choice = random.choice(colors)
            random.seed(seed + 100)
            system_choice = random.choice(colors)
            text = f"🎨 **بازی سه رنگ**\n\nرنگ شما: {user_choice}\nرنگ سیستم: {system_choice}\n\n"
            text += "🎉 **برنده شدی!**" if user_choice == system_choice else "😢 **باختی!**"
            await event.edit(text)
            return
        
        if cmd == 'شانس' and args and args[0].isdigit():
            chance = int(args[0])
            if chance > 100:
                await event.edit("❌ شانس نباید بیشتر از ۱۰۰ باشه")
                return
            colors = ['🔴', '🟢', '🔵']
            choice = random.choice(colors)
            result = "🎉 **برنده شدی!**" if random.randint(1, 100) <= chance else "😢 **باختی!**"
            await event.edit(f"🎨 **رنگ: {choice}**\n{result} (شانس: {chance}%)")
            return
        
        if cmd == 'دارت' and not args:
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("🎯"))
                if msg.media.value == 6:
                    await self.client.send_message(chat_id, "🎯 **دارت! ۶ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return
        
        if cmd == 'بسکتبال' and not args:
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("🏀"))
                if msg.media.value == 5:
                    await self.client.send_message(chat_id, "🏀 **بسکتبال! ۵ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return
        
        if cmd == 'فوتبال' and not args:
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("⚽️"))
                if msg.media.value == 5:
                    await self.client.send_message(chat_id, "⚽️ **فوتبال! ۵ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return
        
        # ========== نشست‌های فعال ==========
        if (cmd in ('نشستهای', 'نشست‌های', 'نشست') and args and args[0] == 'فعال') or (cmd == 'نشستهایفعال'):
            try:
                sessions = await self.client(GetAuthorizationsRequest())
                auths = list(getattr(sessions, 'authorizations', None) or [])
                if not auths:
                    text = "📱 هیچ نشستی یافت نشد"
                else:
                    text = "📱 نشست‌های فعال:\n\n"
                    for i, session in enumerate(auths, 1):
                        model = getattr(session, 'device_model', None) or getattr(session, 'app_name', None) or 'نامشخص'
                        country = getattr(session, 'country', '') or '—'
                        ip = getattr(session, 'ip', '') or '—'
                        platform = getattr(session, 'platform', '') or '—'
                        app = getattr(session, 'app_name', '') or ''
                        da = getattr(session, 'date_active', None) or getattr(session, 'date_created', None)
                        try:
                            ts = int(da.timestamp()) if hasattr(da, 'timestamp') else int(da)
                            date_s = datetime.fromtimestamp(ts).strftime('%Y/%m/%d %H:%M')
                        except Exception:
                            date_s = str(da)
                        text += f"{i}. {model} {app}\n   📍 {country} | {ip}\n   📅 {date_s}\n   📱 {platform}\n\n"
                await event.edit(text[:4000])
            except Exception as e:
                await event.edit(f"❌ خطا در نشست‌ها: {e}")
            return

            return

        # ========== تاریخ ساخت اکانت ==========
        if cmd == 'تاریخ' and args and args[0] == 'ساخت' and len(args) == 2 and args[1] == 'اکانت':
            try:
                try:
                    await self.client(UnblockRequest(id="creationdatebot"))
                except Exception:
                    pass
                await self.client.send_message("creationdatebot", "/start")
                await asyncio.sleep(3.5)
                found = None
                async for msg in self.client.iter_messages("creationdatebot", limit=5):
                    if not msg or not msg.text:
                        continue
                    # Telethon: sender / from_id — نه from_user
                    ok = True
                    try:
                        snd = await msg.get_sender()
                        uname = (getattr(snd, 'username', None) or '').lower()
                        if uname and uname not in ('creationdatebot',):
                            ok = False
                    except Exception:
                        ok = True
                    if ok and len(msg.text) > 5:
                        found = msg.text
                        break
                if found:
                    await event.edit(f"📅 تاریخ ساخت اکانت:\n{found}")
                    try:
                        await self.cleanup_helper_bot("creationdatebot")
                    except Exception:
                        pass
                else:
                    await event.edit("❌ پاسخی از ربات تاریخ دریافت نشد. دوباره تلاش کنید.")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== اطلاعات سیستم ==========
        if cmd == 'اطلاعات' and args and args[0] == 'سیستم':
            try:
                svmem = psutil.virtual_memory()
                cpufreq = psutil.cpu_freq()
                def sizeof_fmt(num):
                    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                        if abs(num) < 1024.0:
                            return f"{num:.1f} {unit}"
                        num /= 1024.0
                    return f"{num:.1f} PB"
                text = "🖥️ **اطلاعات سیستم:**\n\n"
                text += f"💻 سیستم: {__import__('platform').uname().system}\n"
                text += f"🐍 پایتون: {python_version()}\n"
                text += f"🧠 RAM: {sizeof_fmt(svmem.used)}/{sizeof_fmt(svmem.total)} ({svmem.percent}%)\n"
                text += f"⚡ CPU: {psutil.cpu_percent()}%\n"
                text += f"🔄 هسته‌ها: {psutil.cpu_count()}\n"
                text += f"📶 فرکانس: {cpufreq.current:.0f}MHz"
                await event.edit(text)
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return
        
        # ========== دلار / نرخ / نام کوین → کارت سایبرپانک ==========
        raw_full = (event.raw_text or event.text or '').strip()
        raw_low = raw_full.lower()
        is_rate_cmd = cmd in ('دلار', 'نرخ') or (cmd == 'نرخ' and args and args[0] == 'ارز') or raw_low in ('نرخ ارز', 'قیمت ارز', 'ارزها', 'کریپتو', 'بازار')
        symbol_try = PERSIAN_COIN_MAP.get(raw_low) or PERSIAN_COIN_MAP.get(cmd)
        if not symbol_try and cmd.upper() in ('BTC','ETH','TON','SOL','BNB','XRP','DOGE','NOT','PEPE','ADA','LINK','AVAX','USDT','TRX','SHIB'):
            symbol_try = cmd.upper()
        if is_rate_cmd:
            try:
                text = await compile_crypto_rates_text()
                await event.edit(text, parse_mode='html')
            except Exception as e:
                await event.edit(f"❌ خطا در دریافت نرخ: {e}")
            return
        if symbol_try:
            try:
                prices = await fetch_crypto_prices()
                if not prices:
                    await event.edit("❌ ارتباط با API قطع است")
                    return
                usd = float(prices.get(f"{symbol_try}/USDT", 0) or (1.0 if symbol_try == 'USDT' else 0))
                usdt_irt = float(prices.get("USDT/IRT", 0) or 0)
                irt = float(prices.get(f"{symbol_try}/IRT", usd * usdt_irt) or 0)
                if usd <= 0 and symbol_try != 'USDT':
                    await event.edit(f"❌ نرخ {symbol_try} یافت نشد")
                    return
                import random
                chg = random.uniform(-8.5, 12.5)
                card = await compose_cyberpunk_coin_card(symbol_try, usd, irt, chg)
                caption = (
                    f"💎 <b>چارت: {symbol_try}</b>\n\n"
                    f"💵 <b>دلار:</b> <code>${_fmt_price(usd)}</code>\n"
                    f"💵 <b>تومان:</b> <code>{_fmt_price(irt)} تومان</code>\n"
                    f"📊 <b>نوسان:</b> <code>{chg:+.2f}%</code>"
                )
                if card and os.path.exists(card):
                    await self.client.send_file(event.chat_id, card, caption=caption, parse_mode='html')
                    try:
                        os.remove(card)
                    except Exception:
                        pass
                    try:
                        await event.delete()
                    except Exception:
                        pass
                else:
                    await event.edit(caption, parse_mode='html')
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== قیمت ارز ==========
        if cmd == 'قیمت' and args and args[0] == 'ارز' and len(args) > 1:
            currency = args[1].upper()
            try:
                url = "https://api.nobitex.ir/market/stats"
                params = {"srcCurrency": currency, "dstCurrency": "irt"}
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                if "stats" in data and f"{currency}-irt" in data["stats"]:
                    stats = data["stats"][f"{currency}-irt"]
                    text = f"💰 **قیمت {currency}:**\n\n"
                    text += f"خرید: {stats['bestBuy']} تومان\n"
                    text += f"فروش: {stats['bestSell']} تومان\n"
                    text += f"تغییرات: {stats['dayChange']}%\n"
                    text += f"بالاترین: {stats['dayHigh']} تومان\n"
                    text += f"پایین‌ترین: {stats['dayLow']} تومان"
                    await event.edit(text)
                else:
                    await event.edit(f"❌ ارز '{currency}' یافت نشد")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return
        
        # ========== نرخ ارز ==========
        if cmd == 'نرخ' and args and args[0] == 'ارز':
            try:
                url = "https://api.exchangerate-api.com/v4/latest/USD"
                response = requests.get(url, timeout=10)
                data = response.json()
                currencies = {
                    'USD': 'دلار', 'EUR': 'یورو', 'GBP': 'پوند',
                    'AED': 'درهم', 'TRY': 'لیر', 'CHF': 'فرانک', 'CNY': 'یوان'
                }
                text = "💵 **نرخ ارزهای جهانی (هر ۱۰۰۰ واحد):**\n\n"
                for code, name in currencies.items():
                    if code in data['rates']:
                        rate = (1 / data['rates'][code]) * 1000
                        text += f"{name}: {rate:,.0f} تومان\n"
                await event.edit(text)
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return
        
        # ========== تشخیص متن (OCR) ==========
        if cmd == 'تشخیص' and args and args[0] == 'متن':
            if not event.is_reply:
                await event.edit("❌ لطفاً به یک عکس ریپلای کن")
                return
            await event.edit("⏳ در حال تشخیص متن...")
            try:
                try:
                    await self.client(UnblockRequest(id="oneGooglebot"))
                except Exception:
                    pass
                reply_msg = await event.get_reply_message()
                if not reply_msg or not (reply_msg.photo or reply_msg.document):
                    await event.edit("❌ پیام ریپلای‌شده عکس نیست")
                    return
                # فوروارد/ارسال مدیا به ربات OCR
                try:
                    await self.client.forward_messages("oneGooglebot", reply_msg)
                except Exception:
                    path = await self.client.download_media(reply_msg, file=os.path.join(MEDIA_FOLDER, f"ocr_{self.user_id}.jpg"))
                    if path:
                        await self.client.send_file("oneGooglebot", path)
                await asyncio.sleep(7)
                found = None
                async for msg in self.client.iter_messages("oneGooglebot", limit=6):
                    if not msg or not msg.text:
                        continue
                    t = msg.text
                    if 'OCR' in t or 'detected' in t.lower() or len(t) > 10:
                        for pref in ('💭 OCR detected:', 'OCR detected:', 'Detected text:', 'متن:'):
                            t = t.replace(pref, '')
                        found = t.strip()
                        if found:
                            break
                if found:
                    await event.edit(f"📝 متن تشخیص داده شده:\n\n{found[:3500]}")
                    try:
                        await self.cleanup_helper_bot("oneGooglebot")
                    except Exception:
                        pass
                else:
                    await event.edit("❌ تشخیص متن انجام نشد — ربات @oneGooglebot را استارت کنید و دوباره تلاش کنید")
                try:
                    await self.cleanup_helper_bot("oneGooglebot")
                except Exception:
                    pass
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== استیکر متن ==========
        if cmd == 'استیکر' and args and args[0] == 'متن':
            text = ' '.join(args[1:])
            if not text:
                await event.edit("⚠️ فرمت: استیکر متن [متن]")
                return
            try:
                img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                font_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                    "font.ttf",
                ]
                # فونت خیلی بزرگ — پر کردن کل استیکر ۵۱۲
                base_size = 200 if len(text) <= 6 else (170 if len(text) <= 12 else (140 if len(text) <= 20 else (110 if len(text) <= 35 else 88)))
                font = None
                for fp in font_paths:
                    try:
                        font = ImageFont.truetype(fp, base_size)
                        break
                    except Exception:
                        continue
                if font is None:
                    font = ImageFont.load_default()
                # wrap text با عرض بیشتر
                words = text.split()
                lines, cur = [], ""
                max_w = 480
                for w in words:
                    test = (cur + " " + w).strip()
                    bbox = draw.textbbox((0, 0), test, font=font)
                    if bbox[2] - bbox[0] > max_w and cur:
                        lines.append(cur)
                        cur = w
                    else:
                        cur = test
                if cur:
                    lines.append(cur)
                if not lines:
                    lines = [text[:40]]
                # اگر خیلی بلند بود فونت را کوچک‌تر کن
                for _ in range(8):
                    total_h = 0
                    line_sizes = []
                    too_wide = False
                    for ln in lines:
                        bbox = draw.textbbox((0, 0), ln, font=font)
                        lw, lh = bbox[2]-bbox[0], bbox[3]-bbox[1]
                        line_sizes.append((lw, lh))
                        total_h += lh + 12
                        if lw > max_w:
                            too_wide = True
                    if total_h <= 480 and not too_wide:
                        break
                    base_size = max(48, base_size - 10)
                    font = None
                    for fp in font_paths:
                        try:
                            font = ImageFont.truetype(fp, base_size)
                            break
                        except Exception:
                            continue
                    if font is None:
                        font = ImageFont.load_default()
                        break
                y = max(0, (512 - total_h) // 2)
                for ln, (lw, lh) in zip(lines, line_sizes):
                    x = (512 - lw) // 2
                    # سایه برای خوانایی
                    draw.text((x+3, y+3), ln, fill=(0, 0, 0, 180), font=font)
                    draw.text((x, y), ln, fill=(255, 255, 255, 255), font=font)
                    y += lh + 12
                output = BytesIO()
                img.save(output, format='WEBP')
                output.name = "sticker.webp"
                output.seek(0)
                await self.client.send_file(
                    chat_id, output,
                    force_document=False,
                    attributes=[types.DocumentAttributeSticker(
                        alt=text[:16],
                        stickerset=types.InputStickerSetEmpty(),
                        mask=False
                    )]
                )
                await event.delete()
            except Exception as e:
                logger.error(f"استیکر متن: {e}")
                try:
                    await event.edit(f"❌ خطا: {e}")
                except Exception:
                    pass
            return
        
        # ========== عکس → استیکر / فیلم → گیف ==========
        if cmd == 'استیکر' and (not args or (args and args[0] not in ('متن',))):
            if not event.message.is_reply:
                await event.edit("⚠️ روی عکس ریپلای کنید و بنویسید: استیکر")
                return
            try:
                reply_msg = await event.get_reply_message()
                if not reply_msg or not reply_msg.media:
                    await event.edit("❌ رسانه یافت نشد")
                    return
                await event.edit("⏳ در حال تبدیل...")
                # دانلود رسانه
                buf = BytesIO()
                path = await self.client.download_media(reply_msg, file=buf)
                buf.seek(0)
                is_video = bool(reply_msg.video or reply_msg.gif or (reply_msg.document and getattr(reply_msg.document, 'mime_type', '').startswith('video')))
                if is_video:
                    # ارسال به عنوان گیف/انیمیشن
                    buf.name = "anim.mp4"
                    await self.client.send_file(chat_id, buf, force_document=False, supports_streaming=True, video_note=False)
                    # تلاش برای ارسال به صورت gif-like
                    try:
                        buf.seek(0)
                        await self.client.send_file(chat_id, buf, attributes=[types.DocumentAttributeAnimated()], force_document=False)
                    except Exception:
                        pass
                else:
                    # تبدیل به استیکر webp 512
                    try:
                        img = Image.open(buf).convert('RGBA')
                        img = ImageOps.fit(img, (512, 512), centering=(0.5, 0.5))
                        out = BytesIO()
                        img.save(out, format='WEBP')
                        out.name = "sticker.webp"
                        out.seek(0)
                        await self.client.send_file(
                            chat_id, out,
                            force_document=False,
                            attributes=[types.DocumentAttributeSticker(
                                alt="🙂",
                                stickerset=types.InputStickerSetEmpty(),
                                mask=False
                            )]
                        )
                    except Exception as e:
                        buf.seek(0)
                        await self.client.send_file(chat_id, buf)
                await event.delete()
            except Exception as e:
                logger.error(f"استیکر convert: {e}")
                try:
                    await event.edit(f"❌ خطا: {str(e)[:80]}")
                except Exception:
                    pass
            return
        
        # ========== ساخت استیکر با @QuotLyBot ==========
        if cmd == 'ساخت' and args and args[0] == 'استیکر':
            if not event.message.is_reply:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید و بنویسید: ساخت استیکر")
                return
            try:
                reply_msg = await event.get_reply_message()
                if not reply_msg:
                    await event.edit("❌ پیام ریپلای یافت نشد")
                    return
                await event.edit("⏳ در حال ساخت استیکر...")
                try:
                    await self.client(UnblockRequest(id="QuotLyBot"))
                except Exception:
                    pass
                quotly = await self.client.get_entity("QuotLyBot")
                # علامت زمان قبل از ارسال
                import time as _t
                t0 = _t.time()
                # فوروارد پیام به ربات
                try:
                    sent_to_bot = await self.client.forward_messages(quotly, reply_msg)
                except Exception:
                    # fallback: کپی متن/مدیا
                    if reply_msg.media:
                        sent_to_bot = await self.client.send_file(quotly, reply_msg.media, caption=reply_msg.text or '')
                    else:
                        sent_to_bot = await self.client.send_message(quotly, reply_msg.text or '.')
                sent_id = 0
                try:
                    sent_id = sent_to_bot[0].id if isinstance(sent_to_bot, (list, tuple)) else sent_to_bot.id
                except Exception:
                    pass
                # صبر برای پاسخ استیکر — بیشتر تلاش
                sticker_msg = None
                for _ in range(25):
                    await asyncio.sleep(0.8)
                    async for m in self.client.iter_messages(quotly, limit=12):
                        if sent_id and m.id <= sent_id:
                            continue
                        # پیام‌های خیلی قدیمی قبل از درخواست را رد کن
                        try:
                            if m.date and m.date.timestamp() < t0 - 2:
                                continue
                        except Exception:
                            pass
                        is_sticker = bool(getattr(m, 'sticker', None))
                        if not is_sticker and m.document:
                            mt = getattr(m.document, 'mime_type', '') or ''
                            if mt in ('application/x-tgsticker', 'image/webp', 'video/webm', 'image/png'):
                                is_sticker = True
                            for a in (getattr(m.document, 'attributes', None) or []):
                                if 'Sticker' in type(a).__name__ or 'Animated' in type(a).__name__:
                                    is_sticker = True
                                    break
                        if is_sticker:
                            sticker_msg = m
                            break
                        # بعضی وقت‌ها عکس استیکر می‌فرستد
                        if m.photo and m.date and m.date.timestamp() >= t0 - 1:
                            sticker_msg = m
                            break
                    if sticker_msg:
                        break
                if sticker_msg and sticker_msg.media:
                    # ارسال استیکر بدون متن و بدون فوروارد، با ریپلای روی همان پیام کاربر
                    await self.client.send_file(
                        event.chat_id,
                        sticker_msg.media,
                        reply_to=reply_msg.id,
                        caption=None,
                        force_document=False
                    )
                    try:
                        await event.delete()
                    except Exception:
                        pass
                else:
                    await event.edit("❌ استیکر از QuotLyBot دریافت نشد. دوباره امتحان کنید.")
                # بایگانی + حذف تاریخچه ربات کمکی
                try:
                    await self.cleanup_helper_bot("QuotLyBot")
                except Exception as del_e:
                    logger.debug(f"پاک کردن چت QuotLy: {del_e}")
            except Exception as e:
                logger.error(f"ساخت استیکر: {e}\n{traceback.format_exc()}")
                try:
                    await event.edit(f"❌ خطا در ساخت استیکر: {str(e)[:100]}")
                except Exception:
                    pass
            return
        
        
        
        
        # ========== اسکرین‌شات ==========
        if cmd == 'اسکرین‌شات':
            try:
                await self.client.send(
                    types.SendScreenshotNotification(
                        peer=await self.client.resolve_peer(chat_id),
                        reply_to_msg_id=0,
                        random_id=self.client.rnd_id(),
                    )
                )
                await event.edit("✅ اسکرین‌شات شبیه‌سازی شد")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return
        
        # ========== ادامه دستورات قبلی ==========
        
        if cmd == 'سلف' and args and args[0] in ['روشن', 'خاموش']:
            if args[0] == 'روشن':
                db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 1)
                await event.edit("✅ سلف‌بات فعال شد")
            else:
                db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 0)
                await event.edit("✅ سلف‌بات غیرفعال شد")
            return
        
        if cmd == 'تقویم' and not args:
            await self.handle_calendar_command(event)
            return
        
        if cmd == 'فونت' and args:
            font_arg = args[0]
            try:
                if font_arg.isdigit():
                    idx = int(font_arg)
                    if 0 <= idx < len(classic_fonts):
                        self.time_font_indices = [idx]
                        db.update_selfbot_setting(self.user_id, 'time_font_indices', str(idx))
                        await event.edit(f"✅ فونت ساعت به فونت شماره {idx} تغییر کرد")
                    else:
                        await event.edit(f"❌ فونت {idx} وجود ندارد (۰ تا {len(classic_fonts)-1})")
                elif font_arg == 'همه':
                    self.time_font_indices = 'all'
                    db.update_selfbot_setting(self.user_id, 'time_font_indices', 'all')
                    await event.edit("✅ همه فونت‌ها فعال شدند")
                else:
                    await event.edit("❌ فرمت نامعتبر\nمثال: فونت 5 یا فونت همه")
            except:
                await event.edit("❌ خطا در تنظیم فونت")
            return
        
        settings = db.get_selfbot_settings(self.user_id)
        if not settings.get('selfbot_enabled', 1):
            return
        
        if cmd == 'تگ' and args and args[0] == 'ادمین' and len(args) == 1:
            if not isinstance(event.message.peer_id, (PeerChannel, PeerChat)):
                await event.edit("⚠️ این دستور فقط در گروه کار می‌کند")
                return
            
            admins = await self.get_admins(chat_id)
            if admins:
                admin_text = "👑 ادمین‌های گروه:\n\n"
                for admin in admins:
                    mention = f"@{admin.username}" if admin.username else f"[{admin.first_name or 'ادمین'}](tg://user?id={admin.id})"
                    admin_text += f"• {mention}\n"
                
                await event.edit(admin_text, parse_mode='markdown')
            else:
                await event.edit("⚠️ ادمینی یافت نشد")
            return
        
        if cmd == 'پین' and not args:
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                if await self.pin_message(chat_id, reply_msg.id):
                    await event.edit("📌 پیام پین شد")
                else:
                    await event.edit("⚠️ خطا در پین کردن پیام")
            else:
                await event.edit("⚠️ روی پیام مورد نظر ریپلای کنید")
            return
        
        if cmd == 'حذف' and args and args[0] == 'کامل' and len(args) == 1:
            await event.delete()
            messages = []
            async for msg in self.client.iter_messages(event.chat_id, limit=None):
                if msg.sender_id == self.my_id:
                    messages.append(msg.id)
            if messages:
                try:
                    await self.client.delete_messages(event.chat_id, messages)
                    report_msg = await self.client.send_message(event.chat_id, f"✅ {len(messages)} پیام حذف شدند")
                    await asyncio.sleep(2)
                    await report_msg.delete()
                except Exception as e:
                    await self.client.send_message(event.chat_id, f"⚠️ خطا: {str(e)[:100]}")
            else:
                await self.client.send_message(event.chat_id, "⚠️ هیچ پیامی یافت نشد")
            return
        
        if cmd == 'حذف' and args and args[0].isdigit() and len(args) == 1:
            num = int(args[0])
            await event.delete()
            messages = []
            async for msg in self.client.iter_messages(event.chat_id, limit=num):
                if msg.sender_id == self.my_id:
                    messages.append(msg.id)
            if messages:
                try:
                    await self.client.delete_messages(event.chat_id, messages)
                    report_msg = await self.client.send_message(event.chat_id, f"✅ {len(messages)} پیام حذف شدند")
                    await asyncio.sleep(2)
                    await report_msg.delete()
                except Exception as e:
                    await self.client.send_message(event.chat_id, f"⚠️ خطا: {str(e)[:100]}")
            else:
                await self.client.send_message(event.chat_id, "⚠️ هیچ پیامی یافت نشد")
            return
        
        if cmd == 'تنظیم' and args and args[0] == 'اسپم' and len(args) == 3:
            try:
                limit = int(args[1])
                duration = int(args[2])
                if limit > 0 and duration > 0:
                    db.set_spam_settings(self.user_id, spam_limit=limit, mute_duration=duration)
                    await event.edit(f"✅ تنظیمات اسپم بروزرسانی شد\n📊 محدودیت: {limit} پیام\n⏱️ مدت زمان: {duration} ثانیه")
                else:
                    await event.edit("❌ تعداد و زمان باید مثبت باشند")
            except:
                await event.edit("❌ فرمت نامعتبر\nمثال: تنظیم اسپم 5 10")
            return
        
        if cmd == 'اسپم' and args:
            sub_cmd = args[0]
            
            if sub_cmd == 'روشن' and len(args) == 1:
                db.set_spam_settings(self.user_id, spam_protection=1)
                await event.edit("✅ حفاظت اسپم فعال شد")
                return
            
            if sub_cmd == 'خاموش' and len(args) == 1:
                db.set_spam_settings(self.user_id, spam_protection=0)
                await event.edit("✅ حفاظت اسپم غیرفعال شد")
                return
            
            if sub_cmd == 'وضعیت' and len(args) == 1:
                spam_settings = db.get_spam_settings(self.user_id)
                status_text = f"""
🛡️ **حفاظت اسپم:**
🔒 وضعیت: {'✅ فعال' if spam_settings.get('spam_protection') else '❌ غیرفعال'}
📊 محدودیت: {spam_settings.get('spam_limit', 10)} پیام
⏱️ مدت زمان: {spam_settings.get('mute_duration', 10)} ثانیه
                """
                await event.edit(status_text)
                return
            
            if args[0].isdigit() and len(args) >= 2:
                try:
                    num = int(args[0])
                    message_text = ' '.join(args[1:])
                    await event.delete()
                    for _ in range(num):
                        await self.client.send_message(event.chat_id, message_text)
                        await asyncio.sleep(0.05)
                    report_msg = await self.client.send_message(event.chat_id, f"✅ {num} پیام اسپم ارسال شد")
                    await asyncio.sleep(2)
                    await report_msg.delete()
                except:
                    await event.edit("❌ فرمت نامعتبر\nمثال: اسپم 5 سلام")
                return
        
        if cmd == 'تایم' and args:
            if args[0] == 'روشن' and len(args) == 1:
                db.update_selfbot_setting(self.user_id, 'time_enabled', 1)
                db.update_selfbot_setting(self.user_id, 'flag_enabled', 0)
                await self.update_profile_name()
                await event.edit("✅ تایم روشن شد")
                return
            elif args[0] == 'خاموش' and len(args) == 1:
                db.update_selfbot_setting(self.user_id, 'time_enabled', 0)
                db.update_selfbot_setting(self.user_id, 'flag_enabled', 0)
                await self.restore_profile_name()
                await event.edit("✅ تایم خاموش شد")
                return
            elif args[0] == 'پرچم' and len(args) == 2 and args[1] == 'روشن':
                db.update_selfbot_setting(self.user_id, 'time_enabled', 1)
                db.update_selfbot_setting(self.user_id, 'flag_enabled', 1)
                await self.update_profile_name()
                await event.edit("✅ تایم با پرچم روشن شد")
                return
            else:
                try:
                    indices = []
                    for part in args[0].split('.'):
                        if part.isdigit():
                            idx = int(part)
                            if 0 <= idx < len(classic_fonts):
                                indices.append(idx)
                    if indices:
                        self.time_font_indices = indices
                        db.update_selfbot_setting(self.user_id, 'time_font_indices', ','.join(map(str, indices)))
                        await event.edit(f"✅ فونت‌های تایم تنظیم شد: {indices}")
                    else:
                        await event.edit(f"❌ ایندکس نامعتبر. محدوده: ۰ تا {len(classic_fonts)-1}")
                except:
                    await event.edit("❌ فرمت نامعتبر\nمثال: تایم 5.10")
            return
        
        if cmd == 'تاریخ' and args and args[0] == 'کامل' and len(args) == 1:
            date_info = self.get_full_date_info()
            await event.edit(date_info)
            return
        
        if cmd == 'اتوسین' and args and args[0] in ['فعال', 'غیرفعال'] and len(args) == 1:
            if args[0] == 'فعال':
                self.autosend_mode = True
                db.update_selfbot_setting(self.user_id, 'autosend_mode', 1)
                self.save_state()
                await event.edit("✅ اتوسین فعال شد")
            else:
                self.autosend_mode = False
                db.update_selfbot_setting(self.user_id, 'autosend_mode', 0)
                self.save_state()
                await event.edit("✅ اتوسین غیرفعال شد")
            return
        
        if cmd == 'فیلتر' and args:
            if args[0] == 'روشن' and len(args) == 1:
                db.set_filter_enabled(self.user_id, True)
                await event.edit("✅ فیلتر کلمات فعال شد")
                return
            elif args[0] == 'خاموش' and len(args) == 1:
                db.set_filter_enabled(self.user_id, False)
                await event.edit("✅ فیلتر کلمات غیرفعال شد")
                return
            elif args[0] == 'لیست' and len(args) == 1:
                filters = db.get_filter_words(self.user_id)
                if filters:
                    message_text = "📜 لیست کلمات فیلتر شده:\n\n"
                    for i, word_info in enumerate(filters, 1):
                        status = "فعال" if word_info['enabled'] else "غیرفعال"
                        message_text += f"{i}. {word_info['word']} - {status}\n"
                    await event.edit(message_text)
                else:
                    await event.edit("📭 لیست کلمات فیلتر خالی است")
                return
            elif args[0] == 'حذف' and len(args) >= 2:
                word = ' '.join(args[1:])
                if word:
                    db.remove_filter_word(self.user_id, word)
                    await event.edit(f"✅ کلمه {word} از لیست فیلتر حذف شد")
                else:
                    await event.edit("❌ لطفاً یک کلمه وارد کنید")
                return
        
        if cmd == '.فیلتر' and args:
            word = ' '.join(args)
            if word:
                db.add_filter_word(self.user_id, word)
                await event.edit(f"✅ کلمه {word} به لیست فیلتر اضافه شد")
            else:
                await event.edit("❌ لطفاً یک کلمه وارد کنید")
            return

        # فیلتر [کلمه] بدون نقطه هم کار کند
        if cmd == 'فیلتر' and args and args[0] not in ('روشن', 'خاموش', 'لیست', 'حذف'):
            word = ' '.join(args)
            if word:
                db.add_filter_word(self.user_id, word)
                await event.edit(f"✅ کلمه {word} به لیست فیلتر اضافه شد\nبرای فعال‌سازی: فیلتر روشن")
            return

        # ساعت پروفایل
        if cmd in ('ساعت_پروفایل', 'ساعتپروفایل', 'ساعت') and args:
            if args[0] == 'روشن':
                db.update_selfbot_setting(self.user_id, 'profile_clock_enabled', 1)
                await self._backup_current_profile_photo()
                ok = await self.update_profile_clock(force=True)
                await event.edit("✅ ساعت روی پروفایل روشن شد" if ok else "⚠️ روشن شد ولی آپلود عکس ناموفق بود")
                return
            elif args[0] == 'خاموش':
                await self.restore_profile_clock()
                await event.edit("✅ ساعت پروفایل خاموش و عکس قبلی بازگردانده شد")
                return
            elif args[0] == 'رنگ' and len(args) >= 2:
                c = args[1].lower()
                mapping = {
                    'فیروزه': 'cyan', 'فیروزه‌ای': 'cyan', 'cyan': 'cyan',
                    'سبز': 'green', 'green': 'green',
                    'بنفش': 'purple', 'purple': 'purple',
                    'صورتی': 'pink', 'pink': 'pink',
                    'نارنجی': 'orange', 'orange': 'orange',
                    'قرمز': 'red', 'red': 'red',
                    'آبی': 'blue', 'ابی': 'blue', 'blue': 'blue',
                    'سفید': 'white', 'white': 'white',
                }
                color = mapping.get(c, c if c in PROFILE_CLOCK_COLORS else None)
                if not color:
                    await event.edit("❌ رنگ نامعتبر. گزینه‌ها: فیروزه‌ای سبز بنفش صورتی نارنجی قرمز آبی سفید")
                    return
                db.update_selfbot_setting(self.user_id, 'profile_clock_color', color)
                if db.get_selfbot_settings(self.user_id).get('profile_clock_enabled'):
                    await self.update_profile_clock(force=True)
                await event.edit(f"✅ رنگ ساعت: {color}")
                return

        # ویدیو → ویس (ریپلای روی ویدیو)
        if cmd in ('ویس', 'ویدیو_به_ویس', 'ویدیوبهویس', 'صدا') or (
            cmd == 'ویدیو' and args and args[0] in ('به',) and len(args) >= 2 and args[1] in ('ویس', 'صدا')
        ):
            await self.video_to_voice(event)
            return
        
        lock_commands = {
            'لینک': 'lock_link',
            'عکس': 'lock_photo',
            'ویدیو': 'lock_video',
            'استیکر': 'lock_sticker',
            'گیف': 'lock_gif',
            'ویس': 'lock_voice',
            'فایل': 'lock_file',
            'موزیک': 'lock_music',
            'ویدیو نوت': 'lock_video_note',
            'کانتکت': 'lock_contact',
            'لوکیشن': 'lock_location',
            'ایموجی': 'lock_emoji',
            'متن': 'lock_text'
        }
        
        for lock_name, lock_type in lock_commands.items():
            if cmd == f'قفل{lock_name}' and args and args[0] in ['روشن', 'خاموش'] and len(args) == 1:
                target_id = 0
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    target_id = reply_msg.sender_id
                elif isinstance(event.message.peer_id, PeerUser):
                    target_id = event.message.peer_id.user_id
                
                if args[0] == 'روشن':
                    db.set_user_lock(self.user_id, target_id, lock_type, True)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} فعال شد")
                else:
                    db.set_user_lock(self.user_id, target_id, lock_type, False)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} غیرفعال شد")
                return
            elif cmd == 'قفل' and args and len(args) >= 2 and args[0] == lock_name and args[1] in ['روشن', 'خاموش'] and len(args) == 2:
                target_id = 0
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    target_id = reply_msg.sender_id
                elif isinstance(event.message.peer_id, PeerUser):
                    target_id = event.message.peer_id.user_id
                
                if args[1] == 'روشن':
                    db.set_user_lock(self.user_id, target_id, lock_type, True)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} فعال شد")
                else:
                    db.set_user_lock(self.user_id, target_id, lock_type, False)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} غیرفعال شد")
                return
        
        translate_map = dict(FA_TO_LANG)
        if cmd in translate_map and args:
            lang = translate_map[cmd]
            if args[0] == 'روشن' and len(args) == 1:
                self.translate_mode[lang] = True
                db.update_selfbot_setting(self.user_id, f'translate_{lang}', 1)
                await event.edit(f"✅ ترجمه {cmd} فعال شد")
                return
            elif args[0] == 'خاموش' and len(args) == 1:
                self.translate_mode[lang] = False
                db.update_selfbot_setting(self.user_id, f'translate_{lang}', 0)
                await event.edit(f"✅ ترجمه {cmd} غیرفعال شد")
                return
        
        if cmd == 'دشمن' and args and args[0] == 'گروه' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if target_id:
                db.add_enemy(self.user_id, target_id, 'group')
                await event.edit(f"✅ دشمن گروه اضافه شد — هر پیامش با یک اسپم ریپلای می‌شود (پیوی جداست)")
            else:
                await event.edit("⚠️ روی پیام کاربر در گروه ریپلای کنید")
            return
        
        if cmd == 'دوست' and args and args[0] == 'گروه' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if target_id:
                db.remove_enemy(self.user_id, target_id, 'group')
                await event.edit(f"✅ دشمن گروه حذف شد")
            else:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
            return
        
        if cmd == 'دشمن' and not args:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.add_enemy(self.user_id, target_id, 'pv')
                # اسپم مداوم حذف شد — فقط روی هر پیام یک اسپم
                if target_id in self.spam_tasks:
                    try:
                        self.spam_tasks[target_id].cancel()
                    except Exception:
                        pass
                    self.spam_tasks.pop(target_id, None)
                await event.edit(f"✅ دشمن پیوی اضافه شد — هر پیام یک اسپم (پیام پاک نمی‌شود)")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'دوست' and not args:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.remove_enemy(self.user_id, target_id, 'pv')
                await event.edit(f"✅ دوست — دشمن پیوی حذف شد")
                if target_id in self.spam_tasks:
                    try:
                        self.spam_tasks[target_id].cancel()
                    except Exception:
                        pass
                    self.spam_tasks.pop(target_id, None)
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'قفل' and args and args[0] == 'پیوی' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.add_locked_pv(self.user_id, target_id)
                await event.edit(f"✅ قفل پیوی برای کاربر {target_id} فعال شد")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'باز' and args and args[0] == 'پی' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.remove_locked_pv(self.user_id, target_id)
                await event.edit(f"✅ قفل پیوی برای کاربر {target_id} غیرفعال شد")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'قفل' and args and args[0] == 'پیوی' and args[1] == 'همه' and len(args) == 2:
            db.update_selfbot_setting(self.user_id, 'pv_lock_all', 1)
            await event.edit("✅ قفل پیوی همگانی فعال شد")
            return
        
        if cmd == 'باز' and args and args[0] == 'پی' and args[1] == 'همه' and len(args) == 2:
            db.update_selfbot_setting(self.user_id, 'pv_lock_all', 0)
            await event.edit("✅ قفل پیوی همگانی غیرفعال شد")
            return
        
        if cmd == 'بلاک' and not args:
            if isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
                await self.client(BlockRequest(id=target_id))
                await event.edit("✅ کاربر بلاک شد")
            else:
                await event.edit("⚠️ فقط در پی‌وی")
            return
        
        # ========== ریکت - اصلاح شده برای گروه و پیوی ==========
        if cmd == 'ریکت' and args:
            target_id = await get_target_user(event, self.client)
            if not target_id:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
                return
            
            emoji = args[0]
            if emoji in ALLOWED_EMOJIS:
                chat_id = None
                if isinstance(event.message.peer_id, PeerUser):
                    chat_id = event.message.peer_id.user_id
                elif isinstance(event.message.peer_id, PeerChannel):
                    chat_id = event.message.peer_id.channel_id
                elif isinstance(event.message.peer_id, PeerChat):
                    chat_id = event.message.peer_id.chat_id
                
                if chat_id:
                    db.set_reaction(self.user_id, chat_id, target_id, emoji)
                    # ذخیره با full chat_id هم برای سازگاری گروه/سوپرگروه
                    try:
                        full_cid = event.chat_id
                        if full_cid and full_cid != chat_id:
                            db.set_reaction(self.user_id, full_cid, target_id, emoji)
                    except Exception:
                        pass
                    await event.edit(f"✅ ریکت {emoji} برای کاربر {target_id} در چت {chat_id} تنظیم شد")
                    
                    try:
                        msg_id = event.message.reply_to_msg_id or event.message.id
                        if event.is_reply:
                            replied = await event.get_reply_message()
                            if replied:
                                msg_id = replied.id
                        input_chat = await event.get_input_chat()
                        await self.client(SendReactionRequest(
                            peer=input_chat,
                            msg_id=msg_id,
                            reaction=[ReactionEmoji(emoticon=emoji)]
                        ))
                        await event.edit(f"✅ ریکت {emoji} روی پیام ارسال شد و برای بعد ذخیره شد")
                    except Exception as e:
                        logger.error(f"خطا در ارسال ریکت: {e}")
                        await event.edit(f"✅ ریکت {emoji} تنظیم شد (ارسال خودکار بعداً فعال است)")
                else:
                    await event.edit("⚠️ خطا در دریافت شناسه چت")
            else:
                await event.edit(f"⚠️ ایموجی {emoji} مجاز نیست")
            return
        
        if cmd == 'حذف' and args and args[0] == 'ریکت' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if target_id:
                chat_id = None
                if isinstance(event.message.peer_id, PeerUser):
                    chat_id = event.message.peer_id.user_id
                elif isinstance(event.message.peer_id, PeerChannel):
                    chat_id = event.message.peer_id.channel_id
                elif isinstance(event.message.peer_id, PeerChat):
                    chat_id = event.message.peer_id.chat_id
                
                if chat_id:
                    db.remove_reaction(self.user_id, chat_id, target_id)
                    await event.edit(f"✅ ریکت برای کاربر {target_id} در چت {chat_id} حذف شد")
                else:
                    await event.edit("⚠️ خطا در دریافت شناسه چت")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'پیوی' and args and args[0] in ['۱', '۲', '۳'] and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_num = int(args[0])
            if ai_num == 1:
                ai_status['ai_1_pm'] = True
                ai_status['ai_2_pm'] = False
                ai_status['ai_3_pm'] = False
                message = '✅ هوش ۱ (Gemini) در پی‌وی روشن شد'
            elif ai_num == 2:
                ai_status['ai_1_pm'] = False
                ai_status['ai_2_pm'] = True
                ai_status['ai_3_pm'] = False
                message = '✅ هوش ۲ (Paxsenix) در پی‌وی روشن شد'
            else:
                ai_status['ai_1_pm'] = False
                ai_status['ai_2_pm'] = False
                ai_status['ai_3_pm'] = True
                message = '✅ هوش ۳ (DeepSeek) در پی‌وی روشن شد'
            db.update_ai_status(self.user_id, ai_status)
            await event.edit(message)
            return
        
        # پیوی با ایدی عددی — لینک واقعی باز کردن پیوی
        if cmd == 'پیوی' and args and len(args) == 1 and str(args[0]).isdigit():
            tid = int(args[0])
            try:
                from telethon.tl.custom import Button
                display, entity = await self.get_display_name(tid)
                uname = getattr(entity, 'username', None) if entity else None
                fname = (getattr(entity, 'first_name', None) or '') if entity else ''
                lname = (getattr(entity, 'last_name', None) or '') if entity else ''
                prefix = "👤 کاربر\n• نام: "
                mid = (
                    f"\n• ایدی عددی: {tid}\n"
                    f"• یوزرنیم: {'@' + uname if uname else 'ندارد'}\n"
                    f"• نام کامل: {(fname + ' ' + lname).strip() or '—'}\n\n"
                    f"👇 دکمه زیر را بزن تا پیوی باز شود"
                )
                full = prefix + display + mid
                ent = self.make_mention_entity(display, tid, self._utf16_len(prefix))
                if uname:
                    url = f"https://t.me/{uname}"
                else:
                    url = f"tg://user?id={tid}"
                buttons = [[Button.url("💬 باز کردن پیوی", url)]]
                chat = event.chat_id
                try:
                    await event.delete()
                except Exception:
                    pass
                await self.client.send_message(
                    chat, full,
                    formatting_entities=[ent],
                    buttons=buttons
                )
            except Exception as e:
                try:
                    await event.edit(f"👤 کاربر {tid}\n❌ {e}")
                except Exception:
                    pass
            return

        if cmd == 'خاموش' and args and args[0] == 'پیوی' and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_status['ai_1_pm'] = False
            ai_status['ai_2_pm'] = False
            ai_status['ai_3_pm'] = False
            db.update_ai_status(self.user_id, ai_status)
            await event.edit('✅ همه هوش‌ها در پی‌وی خاموش شدند')
            return
        
        if cmd == 'گروه' and args and args[0] in ['۱', '۲', '۳'] and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_num = int(args[0])
            if ai_num == 1:
                ai_status['ai_1_group'] = True
                ai_status['ai_2_group'] = False
                ai_status['ai_3_group'] = False
                message = '✅ هوش ۱ (Gemini) در گروه روشن شد'
            elif ai_num == 2:
                ai_status['ai_1_group'] = False
                ai_status['ai_2_group'] = True
                ai_status['ai_3_group'] = False
                message = '✅ هوش ۲ (Paxsenix) در گروه روشن شد'
            else:
                ai_status['ai_1_group'] = False
                ai_status['ai_2_group'] = False
                ai_status['ai_3_group'] = True
                message = '✅ هوش ۳ (DeepSeek) در گروه روشن شد'
            db.update_ai_status(self.user_id, ai_status)
            await event.edit(message)
            return
        
        if cmd == 'خاموش' and args and args[0] == 'گروه' and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_status['ai_1_group'] = False
            ai_status['ai_2_group'] = False
            ai_status['ai_3_group'] = False
            db.update_ai_status(self.user_id, ai_status)
            await event.edit('✅ همه هوش‌ها در گروه خاموش شدند')
            return
        
        if cmd == 'تنظیم' and args and args[0] == 'گزارش' and len(args) == 1:
            if isinstance(event.message.peer_id, (PeerChannel, PeerChat)):
                group_id = event.message.peer_id.channel_id if isinstance(event.message.peer_id, PeerChannel) else event.message.peer_id.chat_id
                self.report_config.set_report_group(group_id)
                await event.edit(f"✅ گروه گزارش تنظیم شد\nآیدی: {group_id}")
            else:
                await event.edit("⚠️ این دستور فقط در گروه کار می‌کند")
            return
        
        if cmd == 'گروه' and args and args[0] == 'گزارش' and len(args) == 1:
            await event.edit(f"📍 گروه گزارش فعلی:\nآیدی: {self.report_config.report_group_id}")
            return
        
        if cmd == 'کامنت' and args:
            comment_text = ' '.join(args)
            chat = await event.get_chat()
            chat_type = "کانال" if hasattr(chat, 'broadcast') and chat.broadcast else "گروه"
            db.set_auto_comment(
                self.user_id,
                chat.id,
                comment_text,
                chat.title,
                chat_type,
                getattr(chat, 'username', None)
            )
            result = self.set_auto_comment(
                chat.id,
                comment_text,
                chat.title,
                chat_type,
                getattr(chat, 'username', None)
            )
            await event.edit(f"✅ {result}")
            return
        
        if cmd == 'کانال‌ها' and not args:
            auto_comments = db.get_auto_comments(self.user_id)
            if auto_comments:
                msg = "📊 کانال‌های تنظیم شده:\n\n"
                for comment in auto_comments:
                    msg += f"• {comment['channel_title']} ({comment['channel_type']})\n"
                    msg += f"  آیدی: {comment['channel_id']}\n"
                    msg += f"  متن: {comment['comment_text'][:30]}...\n\n"
                await event.edit(msg)
            else:
                await event.edit("📭 هیچ کانالی تنظیم نشده")
            return
        
        if cmd == 'حذف' and args and args[0] == 'کانال' and len(args) == 1:
            chat = await event.get_chat()
            channel_id = chat.id
            auto_comment = db.get_auto_comment(self.user_id, channel_id)
            if auto_comment:
                db.remove_auto_comment(self.user_id, channel_id)
                self.remove_auto_comment(channel_id)
                await event.edit(f"✅ تنظیمات {auto_comment['channel_title']} حذف شد")
            else:
                await event.edit("⚠️ این کانال تنظیم نشده است")
            return
        
        if cmd == 'تست' and args and args[0] == 'کانال' and len(args) == 1:
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                chat = await reply_msg.get_chat()
            else:
                chat = await event.get_chat()
            
            info = f"🔍 اطلاعات تست:\n\n"
            info += f"چت: {chat.title}\n"
            info += f"نوع: {'کانال' if hasattr(chat, 'broadcast') and chat.broadcast else 'گروه'}\n"
            info += f"آیدی: {chat.id}\n"
            auto_comment = db.get_auto_comment(self.user_id, chat.id)
            info += f"تنظیم شده: {'✅' if auto_comment else '❌'}\n"
            if auto_comment:
                info += f"متن: {auto_comment['comment_text'][:50]}...\n"
            await event.edit(info)
            return
        
        if cmd == 'وضعیت' and not args:
            settings = db.get_selfbot_settings(self.user_id)
            await event.edit(self.format_status_info(settings))
            return
        
        if cmd == 'پینگ' and not args:
            start = time.time()
            await event.edit("🏓 پینگ: ...")
            end = time.time()
            ping = round((end - start) * 1000, 2)
            await event.edit(f"› 🏓 پینگ: {ping} ms")
            return
        
        if cmd == 'درباره' and not args:
            await event.edit(f"ℹ️ درباره بات\n\n🤖 نسخه: v{BOT_VERSION}\n👨‍💻 سازنده: {BOT_CREATOR}")
            return
        
        if cmd == 'من' and args and args[0] == 'کی' and args[1] == 'ام' and len(args) == 2:
            if isinstance(event.message.peer_id, PeerUser):
                user_id_info = event.sender_id
                user_name = db.get_user_name(user_id_info)
                user_info = db.get_user_info(user_id_info)
                
                info_text = f"👤 اطلاعات شما:\n"
                info_text += f"• نام: {user_name}\n"
                info_text += f"• آی‌دی: {user_id_info}\n"
                
                if user_info:
                    info_text += f"\n📝 اطلاعات ذخیره شده:\n"
                    for key, value in user_info.items():
                        info_text += f"• {key}: {value}\n"
                else:
                    info_text += f"\nℹ️ اطلاعات اضافی ذخیره نشده\n"
                
                await event.edit(info_text)
            return
        
        if cmd == 'تغییر' and len(args) >= 2:
            if args[0] == 'اسم':
                new_name = ' '.join(args[1:])
                current_name = db.get_current_name(self.user_id)
                if not current_name:
                    db.set_current_name(self.user_id, self.BASE_NAME)
                    current_name = self.BASE_NAME
                
                db.set_current_name(self.user_id, new_name)
                await self.client(UpdateProfileRequest(first_name=new_name))
                
                settings = db.get_selfbot_settings(self.user_id)
                if settings.get('time_enabled'):
                    self.BASE_NAME = new_name
                    await self.update_profile_name()
                else:
                    self.BASE_NAME = new_name
                
                await event.edit(f"✅ نام به {new_name} تغییر کرد")
                return
            
            elif args[0] == 'بیو':
                new_bio = ' '.join(args[1:])
                await self.client(UpdateProfileRequest(about=new_bio))
                self.save_bio(new_bio)
                await event.edit(f"✅ بیو به {new_bio} تغییر کرد")
                return
            elif args[0] == 'پروفایل' and len(args) == 1:
                # تغییر پروفایل با ریپلای روی عکس
                if not event.is_reply:
                    await event.edit("⚠️ روی یک عکس ریپلای کنید و بنویسید: تغییر پروفایل")
                    return
                try:
                    reply_msg = await event.get_reply_message()
                    if not reply_msg or not reply_msg.media:
                        await event.edit("⚠️ پیام ریپلای‌شده عکس نیست")
                        return
                    path = await self.client.download_media(reply_msg, file=os.path.join(MEDIA_FOLDER, f"setpf_{self.user_id}.jpg"))
                    if not path or not os.path.exists(path):
                        await event.edit("⚠️ دانلود عکس ناموفق")
                        return
                    try:
                        me = await self.client.get_me()
                        if me.photo:
                            photos = await self.client.get_profile_photos('me', limit=1)
                            if photos:
                                await self.client(DeletePhotosRequest(id=[photos[0]]))
                    except Exception:
                        pass
                    file = await self.client.upload_file(path)
                    await self.client(UploadProfilePhotoRequest(file=file))
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                    await event.edit("✅ عکس پروفایل تغییر کرد")
                except Exception as e:
                    logger.error(f"تغییر پروفایل: {e}")
                    await event.edit(f"❌ خطا: {str(e)[:80]}")
                return
        
        # پروف / تغییر پروفایل (ریپلای عکس) — فقط دستور خالص بدون آرگومان اضافه
        if (cmd == 'پروف' and not args) or (cmd == 'تغییر' and args and args[0] == 'پروفایل' and len(args) == 1):
            if not event.is_reply:
                await event.edit("⚠️ روی یک عکس ریپلای کنید")
                return
            try:
                reply_msg = await event.get_reply_message()
                path = await self.client.download_media(reply_msg, file=os.path.join(MEDIA_FOLDER, f"setpf_{self.user_id}.jpg"))
                if not path or not os.path.exists(path):
                    await event.edit("⚠️ دانلود عکس ناموفق — روی عکس ریپلای کنید")
                    return
                try:
                    me = await self.client.get_me()
                    if me.photo:
                        photos = await self.client.get_profile_photos('me', limit=1)
                        if photos:
                            await self.client(DeletePhotosRequest(id=[photos[0]]))
                except Exception:
                    pass
                file = await self.client.upload_file(path)
                await self.client(UploadProfilePhotoRequest(file=file))
                try:
                    os.remove(path)
                except Exception:
                    pass
                await event.edit("✅ عکس پروفایل ست شد")
            except Exception as e:
                logger.error(f"پروف: {e}")
                await event.edit(f"❌ خطا: {str(e)[:80]}")
            return

        # یوزرنیم / ایدی عددی (ریپلای روی کاربر)
        if cmd in ('یوزرنیم', 'یوزنیم', 'username') and not args:
            if not event.is_reply:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید و بنویسید: یوزرنیم")
                return
            try:
                reply_msg = await event.get_reply_message()
                u = await reply_msg.get_sender()
                if not u:
                    await event.edit("❌ کاربر پیدا نشد")
                    return
                uname = getattr(u, 'username', None)
                if uname:
                    await event.edit(f"@{uname}")
                else:
                    await event.edit(f"⚠️ این کاربر یوزرنیم ندارد\nایدی: `{u.id}`")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        if (cmd in ('ایدی', 'آیدی', 'id') and (not args or (args and args[0] in ('عددی', 'عدد')))):
            if not event.is_reply:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید و بنویسید: ایدی عددی")
                return
            try:
                reply_msg = await event.get_reply_message()
                u = await reply_msg.get_sender()
                if not u:
                    # ممکن است ریپلای روی پیام کانال باشد
                    tid = getattr(reply_msg, 'sender_id', None) or getattr(getattr(reply_msg, 'from_id', None), 'user_id', None)
                    if tid:
                        await event.edit(f"`{tid}`")
                    else:
                        await event.edit("❌ کاربر پیدا نشد")
                    return
                await event.edit(f"`{u.id}`")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return
        
        # مترجم خودکار: ریپلای + ترجمه  /  ترجمه به زبان روسی
        if cmd == 'ترجمه':
            if not event.is_reply:
                await event.edit("⚠️ روی متن ریپلای کنید\n• ترجمه → فارسی\n• ترجمه به زبان روسی → روسی")
                return
            try:
                reply_msg = await event.get_reply_message()
                src_text = (reply_msg.text or reply_msg.message or '').strip()
                if not src_text:
                    await event.edit("⚠️ پیام ریپلای‌شده متن ندارد")
                    return
                target = 'fa'
                if args:
                    # ترجمه به زبان روسی / ترجمه روسی / ترجمه به روسی
                    joined = ' '.join(args)
                    for fa, key in FA_TO_LANG.items():
                        if fa in joined:
                            target = TRANSLATE_LANG_CODES.get(key, 'fa')
                            break
                    if target == 'fa' and args[-1] in TRANSLATE_LANG_CODES:
                        target = TRANSLATE_LANG_CODES[args[-1]]
                try:
                    from deep_translator import GoogleTranslator
                    result = await asyncio.to_thread(
                        lambda: GoogleTranslator(source='auto', target=target).translate(src_text)
                    )
                    await event.edit(result or "❌ ترجمه خالی")
                except Exception as e:
                    await event.edit(f"❌ خطا در ترجمه: {str(e)[:100]}")
            except Exception as e:
                logger.error(f"ترجمه: {e}")
                await event.edit(f"❌ {str(e)[:80]}")
            return
        
        if cmd == 'لیست' and args and args[0] == 'دشمن' and len(args) == 1:
            enemies = db.get_enemies(self.user_id, 'pv')
            if enemies:
                message = "📋 لیست دشمنان:\n\n"
                for i, enemy_id in enumerate(enemies, 1):
                    try:
                        enemy = await self.client.get_entity(enemy_id)
                        enemy_name = enemy.first_name or f"کاربر {enemy_id}"
                        message += f"{i}. {enemy_name} ({enemy_id})\n"
                    except:
                        message += f"{i}. کاربر {enemy_id}\n"
                await event.edit(message)
            else:
                await event.edit("📭 لیست دشمنان خالی است")
            return
        
        if cmd == 'لیست' and args and args[0] == 'اسپم' and len(args) == 1:
            spam_messages = db.get_enemy_spam_messages(self.user_id)
            if spam_messages:
                message = "📜 لیست پیام‌های اسپم:\n\n"
                for i, spam_msg in enumerate(spam_messages, 1):
                    message += f"{i}. {spam_msg['text']}\n"
                message += f"\n📊 تعداد: {len(spam_messages)}"
                await event.edit(message)
            else:
                await event.edit("📭 لیست پیام‌های اسپم خالی است")
            return
        
        if cmd == 'پاک' and args and args[0] == 'کردن' and args[1] == 'اسپم' and len(args) == 2:
            db.clear_enemy_spam_messages(self.user_id)
            await event.edit("✅ لیست اسپم پاک شد")
            return
        
        if cmd == 'اضافه' and args and args[0] == 'اسپم' and len(args) == 1:
            self.adding_spam = True
            await event.edit("📝 حالت اضافه کردن اسپم فعال شد\nبرای پایان: اتمام اسپم")
            return
        
        if cmd == 'اتمام' and args and args[0] == 'اسپم' and len(args) == 1:
            self.adding_spam = False
            await event.edit("✅ حالت اضافه کردن اسپم غیرفعال شد")
            return
        
        if cmd == 'حذف' and len(args) >= 2 and args[0] == 'اسپم' and args[1].isdigit():
            message_id = int(args[1])
            spam_messages = db.get_enemy_spam_messages(self.user_id)
            if 1 <= message_id <= len(spam_messages):
                spam_msg = spam_messages[message_id - 1]
                db.delete_enemy_spam_message(self.user_id, spam_msg['id'])
                await event.edit(f"✅ پیام شماره {message_id} حذف شد")
            else:
                await event.edit(f"⚠️ پیام شماره {message_id} وجود ندارد")
            return
        
        style_commands = {
            'بولد': 'بولد',
            'زیرخط': 'زیرخط',
            'خط خورده': 'خط خورده',
            'نقل قول': 'نقل قول',
            'اسپویلر': 'اسپویلر',
            'کج': 'کج',
            'کد': 'کد',
            'پیش': 'پیش'
        }
        
        for style_cmd, style_name in style_commands.items():
            if cmd == style_cmd and args and args[0] == 'روشن' and len(args) == 1:
                db.update_selfbot_setting(self.user_id, 'text_style', style_name)
                await event.edit(f"✅ استایل {style_cmd} فعال شد")
                return
            if cmd == style_cmd and args and args[0] == 'خاموش' and len(args) == 1:
                current = db.get_selfbot_settings(self.user_id).get('text_style')
                if current == style_name:
                    db.update_selfbot_setting(self.user_id, 'text_style', None)
                    await event.edit(f"✅ استایل {style_cmd} غیرفعال شد")
                else:
                    await event.edit(f"⚠️ استایل {style_cmd} فعال نیست")
                return
        
        if cmd == 'قلب' and not args:
            await event.delete()
            await self.heart_animation(event.chat_id)
            return
        
        if cmd == 'ماه' and not args:
            await event.delete()
            await self.moon_animation(event.chat_id)
            return
        
        if cmd == 'قلب' and args and args[0] == 'پیشرفته' and len(args) == 1:
            await event.delete()
            try:
                msg = await self.client.send_message(event.chat_id, "❤️ شروع...")
                await advanced_heart_animation(msg)
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if cmd == 'عشق' and not args:
            await event.delete()
            try:
                msg = await event.respond("💝 شروع...")
                await advanced_heart_animation(msg)
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if cmd == 'سنتت' and not args:
            await event.delete()
            try:
                msg = await event.respond("🕯️ در حال اجرا...")
                for i in range(101):
                    bar_len = int(i / 100 * 20)
                    bar = "█" * bar_len + "░" * (20 - bar_len)
                    await msg.edit(f"🕯️ {i}% [{bar}]")
                    await asyncio.sleep(0.03)
                await asyncio.sleep(1)
                await msg.edit("✅ انجام شد 🥴")
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if cmd == 'هک' and not args:
            await event.delete()
            try:
                msg = await event.respond("🔍 در حال هک...")
                await asyncio.sleep(2)
                await msg.edit("User online: True\nTelegram access: True\nRead Storage: True")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 0%\n[░░░░░░░░░░░░░░░░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 25%\n[█████░░░░░░░░░░░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 50%\n[██████████░░░░░░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 75%\n[███████████████░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 100%\n[████████████████████]")
                await asyncio.sleep(2)
                await msg.edit("✅ هک کامل شد")
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        # اطلاعات عادی (برای همه) — مثل قبل
        if cmd == 'اطلاعات' and not args:
            if event.is_reply:
                reply_message = await event.get_reply_message()
                user = await reply_message.get_sender()
            else:
                user = await self.client.get_me()
            username = f"@{user.username}" if user.username else "ندارد"
            name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "ندارد"
            try:
                full_user = await self.client(GetFullUserRequest(user.id))
                bio = full_user.full_user.about or "ندارد"
            except Exception:
                bio = "ندارد"
            photo_count = 0
            try:
                photos = await self.client(GetUserPhotosRequest(user_id=user.id, offset=0, max_id=0, limit=100))
                if hasattr(photos, 'count') and photos.count is not None:
                    photo_count = int(photos.count)
                elif photos.photos:
                    photo_count = len(photos.photos)
            except Exception:
                photo_count = 1 if getattr(user, 'photo', None) else 0
            info_text = (
                f"📋 اطلاعات:\n\n"
                f"👤 یوزرنیم: {username}\n"
                f"🆔 ID: {user.id}\n"
                f"📛 نام: {name}\n"
                f"📝 بیو: {bio}\n"
                f"📸 تعداد عکس: {photo_count}"
            )
            sent = False
            if user.photo:
                try:
                    photo = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user.id}.jpg")
                    if photo and os.path.exists(photo):
                        await self.client.send_file(event.chat_id, photo, caption=info_text)
                        try:
                            os.remove(photo)
                        except Exception:
                            pass
                        sent = True
                except Exception:
                    pass
            if not sent:
                try:
                    await self.client.send_message(event.chat_id, info_text + "\n\n📸 عکس پروفایل ندارد")
                except Exception:
                    await event.edit(info_text)
            try:
                await event.delete()
            except Exception:
                pass
            return

        # اطلاعات کاربر — فقط ادمین (سیستمی + سلف)
        if cmd == 'اطلاعات' and args and args[0] == 'کاربر':
            if not is_admin(self.user_id) and not is_admin(getattr(self, 'my_id', 0) or 0):
                await event.edit("⛔ این دستور فقط برای ادمین است")
                return
            if not event.is_reply:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید: اطلاعات کاربر")
                return
            reply_message = await event.get_reply_message()
            user = await reply_message.get_sender()
            if not user:
                await event.edit("❌ کاربر پیدا نشد")
                return
            username = f"@{user.username}" if getattr(user, 'username', None) else "ندارد"
            name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "ندارد"
            try:
                full_user = await self.client(GetFullUserRequest(user.id))
                bio = full_user.full_user.about or "ندارد"
            except Exception:
                bio = "ندارد"
            ud = db.get_user(str(user.id)) or {}
            sa = ud.get('self_active')
            banned = db.is_user_banned(user.id)
            running = str(user.id) in selfbot_managers and getattr(selfbot_managers[str(user.id)], 'running', False)
            created = ud.get('created_at') or ud.get('updated_at') or '—'
            phone = ud.get('phone') or '—'
            sf = ud.get('session_file') or '—'
            hours_line = ""
            try:
                from datetime import datetime as _dt
                if isinstance(created, str) and len(created) >= 19:
                    cdt = _dt.strptime(created[:19], "%Y-%m-%d %H:%M:%S")
                    hours = int((get_now().replace(tzinfo=None) - cdt).total_seconds() // 3600)
                    hours_line = f"⏱ مدت عضویت: {hours // 24} روز و {hours % 24} ساعت\n"
            except Exception:
                pass
            info_text = (
                f"🛡 اطلاعات کاربر (ادمین)\n\n"
                f"👤 یوزرنیم: {username}\n"
                f"🆔 ID: `{user.id}`\n"
                f"📛 نام: {name}\n"
                f"📝 بیو: {bio}\n"
                f"📱 تلفن: {phone}\n"
                f"📁 سشن: {sf}\n"
                f"📅 عضویت: {created}\n"
                f"{hours_line}"
                f"🟢 سلف DB: {'فعال' if sa in (1,'1',True) else 'خاموش'}\n"
                f"⚡ سشن زنده: {'بله' if running else 'خیر'}\n"
                f"⛔ بن: {'بله' if banned else 'خیر'}"
            )
            try:
                await event.edit(info_text)
            except Exception:
                await self.client.send_message(event.chat_id, info_text)
            return

        if cmd == 'دانلود' and args and args[0] == 'پروفایل' and len(args) == 1:
            if event.is_reply:
                reply_message = await event.get_reply_message()
                user = await reply_message.get_sender()
            else:
                user = await self.client.get_me()
            
            user_id_info = user.id
            user_name = user.first_name or user.username or "کاربر"
            
            if user.photo:
                try:
                    photo = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user_id_info}.jpg")
                    if photo and os.path.exists(photo):
                        await self.client.send_file(event.chat_id, photo, caption=f"📸 پروفایل {user_name}")
                        os.remove(photo)
                    else:
                        await event.edit(f"⚠️ خطا در دانلود")
                except:
                    await event.edit(f"⚠️ خطا در دانلود")
            else:
                await event.edit(f"⚠️ عکس پروفایلی وجود ندارد")
            await event.delete()
            return
        
        if cmd == 'ست' and args:
            if args[0] == 'پروف' and len(args) == 1:
                if event.is_reply:
                    reply_message = await event.get_reply_message()
                    user = await reply_message.get_sender()
                    if user.photo:
                        try:
                            photo_path = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user.id}.jpg")
                            if photo_path and os.path.exists(photo_path):
                                me = await self.client.get_me()
                                if me.photo:
                                    photos = await self.client.get_profile_photos(me.id, limit=1)
                                    if photos:
                                        await self.client(DeletePhotosRequest(id=[photos[0]]))
                                file = await self.client.upload_file(photo_path)
                                await self.client(UploadProfilePhotoRequest(file=file))
                                await event.edit("✅ عکس پروفایل ست شد")
                                os.remove(photo_path)
                            else:
                                await event.edit("⚠️ خطا در دانلود")
                        except FloodWaitError as e:
                            await event.edit(f"⚠️ {e.seconds} ثانیه صبر کنید")
                        except Exception as e:
                            await event.edit("⚠️ خطا")
                    else:
                        await event.edit("⚠️ این کاربر عکس پروفایل ندارد")
                else:
                    await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
                await event.delete()
                return
            
            elif args[0] == 'بیو' and len(args) == 1:
                if event.is_reply:
                    reply_message = await event.get_reply_message()
                    user = await reply_message.get_sender()
                    try:
                        full_user = await self.client(GetFullUserRequest(user.id))
                        bio = full_user.full_user.about or ""
                        await self.client(UpdateProfileRequest(about=bio))
                        self.save_bio(bio)
                        await event.edit("✅ بیو ست شد")
                    except Exception as e:
                        await event.edit("⚠️ خطا")
                else:
                    await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
                await event.delete()
                return
        
        if len(args) >= 2 and cmd == 'حذف':
            if args[0] == 'ست' and args[1] == 'پروف' and len(args) == 2:
                me = await self.client.get_me()
                if me.photo:
                    try:
                        photos = await self.client.get_profile_photos(me.id, limit=1)
                        if photos:
                            await self.client(DeletePhotosRequest(id=[photos[0]]))
                        await event.edit("✅ عکس پروفایل حذف شد")
                    except FloodWaitError as e:
                        await event.edit(f"⚠️ {e.seconds} ثانیه صبر کنید")
                    except Exception as e:
                        await event.edit("⚠️ خطا")
                else:
                    await event.edit("⚠️ عکس پروفایلی وجود ندارد")
                return
            
            elif args[0] == 'ست' and args[1] == 'بیو' and len(args) == 2:
                try:
                    await self.client(UpdateProfileRequest(about=""))
                    self.save_bio("")
                    await event.edit("✅ بیو خالی شد")
                except Exception as e:
                    await event.edit("⚠️ خطا")
                return
        
        if cmd == 'سرچ' and not args:
            self.search_mode = True
            await event.edit('🔍 حالت سرچ فعال شد.\n\nاکنون هر متنی که ارسال کنید در گوگل جستجو می‌شود.\nبرای خروج از حالت سرچ، دستور خروج سرچ را ارسال کنید.')
            return
        
        if cmd == 'خروج' and args and args[0] == 'سرچ' and len(args) == 1:
            self.search_mode = False
            self.last_search_results = []
            await event.edit('✅ حالت سرچ غیرفعال شد.')
            return
        
        if cmd == '.اهنگ' and args:
            song_name = ' '.join(args)
            await event.edit(f"🎵 در حال جستجوی آهنگ: {song_name}...")
            try:
                bot_username = MUSIC_BOT.replace('@', '')
                results = await self.client.inline_query(bot_username, song_name)
                if results and len(results) > 0:
                    await results[0].click(chat_id)
                    await event.delete()
                    logger.info(f"✅ آهنگ {song_name} ارسال شد")
                else:
                    await event.edit(f"❌ آهنگی با نام '{song_name}' پیدا نشد")
            except Exception as e:
                await event.edit(f"❌ خطا در ارسال آهنگ: {str(e)[:100]}")
            return
        
        if cmd in ['.پنل', 'پنل', '/panel'] and not args:
            try:
                await event.delete()
            except Exception:
                pass
            # فقط اینلاین → یک پیام واحد (عکس + نام + دکمه‌ها)
            try:
                bot_username = BOT_USERNAME.replace('@', '')
                results = await self.client.inline_query(bot_username, '')
                if results:
                    await results[0].click(chat_id)
                else:
                    await self.client.send_message(chat_id, "⚠️ پنل یافت نشد. ربات را استارت کنید.")
            except Exception as e:
                try:
                    await self.client.send_message(chat_id, f"❌ خطا در پنل: {str(e)[:120]}")
                except Exception:
                    pass
            return
        
        # ========== پنل کاربر (ریپلای) ==========
        if cmd == 'پنل' and args and args[0] == 'کاربر':
            if not event.message.is_reply:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید و بنویسید: پنل کاربر")
                return
            try:
                reply_msg = await event.get_reply_message()
                target = await reply_msg.get_sender()
                if not target:
                    await event.edit("❌ کاربر یافت نشد")
                    return
                tid = int(target.id)
                panel_lock_targets[self.user_id] = tid
                name = (getattr(target, 'first_name', '') or '')
                if getattr(target, 'last_name', None):
                    name = (name + ' ' + target.last_name).strip()
                if not name:
                    name = f"User {tid}"
                name = clean_display_name(name)
                uname = f"@{target.username}" if getattr(target, 'username', None) else "ندارد"
                is_bot = "بله" if getattr(target, 'bot', False) else "خیر"
                is_premium = "بله" if getattr(target, 'premium', False) else "خیر"
                is_enemy_pv = db.is_enemy(self.user_id, tid, 'pv')
                is_enemy_g = db.is_enemy(self.user_id, tid, 'group')
                is_pv_locked = db.is_pv_locked(self.user_id, tid)
                self_status_line = ""
                try:
                    udt = db.get_user(str(tid)) or {}
                    if udt.get('self_active') in (1, '1', True):
                        running = str(tid) in selfbot_managers and getattr(selfbot_managers[str(tid)], 'running', False)
                        self_status_line = "🟢 سلفش فعال هست" + (" (آنلاین)" if running else "") + "\n"
                    else:
                        self_status_line = "🔴 سلف ندارد / غیرفعال\n"
                except Exception:
                    pass
                caption = (
                    f"👤 {name}\n"
                    f"🆔 `{tid}`\n"
                    f"📎 {uname}\n"
                    f"🤖 ربات: {is_bot} | ⭐ پرمیوم: {is_premium}\n"
                    f"{self_status_line}"
                    f"━━━━━━━━━━━━━━\n"
                    f"دشمن پیوی: {'✅' if is_enemy_pv else '❌'} | دشمن گروه: {'✅' if is_enemy_g else '❌'}\n"
                    f"قفل پیوی: {'✅' if is_pv_locked else '❌'}\n"
                    f"از دکمه‌ها برای مدیریت استفاده کنید"
                )
                avatar_path = None
                try:
                    photos = await self.client.get_profile_photos(target, limit=1)
                    if photos:
                        avatar_path = os.path.join(MEDIA_FOLDER, f"uav_{tid}.jpg")
                        os.makedirs(MEDIA_FOLDER, exist_ok=True)
                        await self.client.download_media(photos[0], file=avatar_path)
                except Exception as e:
                    logger.warning(f"پنل کاربر avatar: {e}")
                photo_path = render_user_panel_image(name, avatar_path)
                kb = get_user_manage_keyboard(self.user_id, tid)
                kb_dict = {
                    'inline_keyboard': [
                        [{'text': b.text, 'callback_data': b.callback_data} for b in row]
                        for row in kb.inline_keyboard
                    ]
                }
                api = f"https://api.telegram.org/bot{BOT_TOKEN}"
                sent = False
                dest_owner = int(self.user_id)

                # ذخیره برای اینلاین (مثل پنل اصلی)
                try:
                    user_panel_cache[str(self.user_id)] = {
                        'target_id': tid,
                        'name': name,
                        'caption': caption,
                        'photo_path': photo_path,
                        'avatar_path': avatar_path,
                        'ts': time.time(),
                    }
                except Exception:
                    pass

                # ۱) مثل پنل اصلی: اینلاین هلپر → عکس+دکمه در همین چت
                try:
                    bot_username = BOT_USERNAME.replace('@', '')
                    results = await self.client.inline_query(bot_username, f'up_{tid}')
                    if results:
                        await results[0].click(chat_id)
                        sent = True
                        logger.info("پنل کاربر → inline click OK")
                except Exception as e:
                    logger.warning(f"پنل کاربر inline: {e}")

                # ۲) ارسال با Bot API به همین چت (اگر ربات عضو باشد)
                if not sent and photo_path and os.path.exists(photo_path):
                    try:
                        with open(photo_path, 'rb') as f:
                            r = requests.post(
                                f"{api}/sendPhoto",
                                data={
                                    'chat_id': chat_id,
                                    'caption': caption,
                                    'parse_mode': 'Markdown',
                                    'reply_markup': json.dumps(kb_dict),
                                },
                                files={'photo': ('panel.jpg', f, 'image/jpeg')},
                                timeout=25
                            )
                        body = r.json() if r.content else {}
                        if r.status_code == 200 and body.get('ok'):
                            sent = True
                            logger.info("پنل کاربر → same chat bot OK")
                    except Exception as e:
                        logger.warning(f"پنل کاربر same chat bot: {e}")

                # ۳) عکس با سلف در همین چت + دکمه‌ها در پیوی ربات
                if not sent:
                    try:
                        if photo_path and os.path.exists(photo_path):
                            await self.client.send_file(chat_id, photo_path, caption=caption)
                        else:
                            await self.client.send_message(chat_id, caption)
                        sent = True
                        logger.info("پنل کاربر photo → telethon same chat")
                    except Exception as e:
                        logger.warning(f"پنل کاربر telethon: {e}")
                    try:
                        if photo_path and os.path.exists(photo_path):
                            with open(photo_path, 'rb') as f:
                                r = requests.post(
                                    f"{api}/sendPhoto",
                                    data={
                                        'chat_id': dest_owner,
                                        'caption': caption,
                                        'parse_mode': 'Markdown',
                                        'reply_markup': json.dumps(kb_dict),
                                    },
                                    files={'photo': ('panel.jpg', f, 'image/jpeg')},
                                    timeout=30
                                )
                        else:
                            r = requests.post(
                                f"{api}/sendMessage",
                                json={'chat_id': dest_owner, 'text': caption, 'reply_markup': kb_dict, 'parse_mode': 'Markdown'},
                                timeout=15
                            )
                        body = r.json() if r.content else {}
                        if r.status_code == 200 and body.get('ok'):
                            sent = True
                            logger.info("پنل کاربر buttons → owner PV OK")
                        else:
                            logger.warning(f"پنل کاربر PV fail: {getattr(r,'text','')[:200]}")
                    except Exception as e:
                        logger.warning(f"پنل کاربر PV bot: {e}")

                try:
                    await event.delete()
                except Exception:
                    pass
                if not sent:
                    try:
                        await self.client.send_message(chat_id, "❌ ارسال پنل کاربر ناموفق بود. ربات را با /start استارت کنید.")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"پنل کاربر: {e}\n{traceback.format_exc()}")
                try:
                    await event.edit(f"❌ خطا: {str(e)[:120]}")
                except Exception:
                    pass
            return
        
        if cmd == 'امار' and args and args[0] == 'گپ' and len(args) == 1:
            await event.delete()
            target_user_id = None
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user_id = reply_msg.sender_id
            
            if not target_user_id and isinstance(event.message.peer_id, PeerUser):
                target_user_id = event.message.peer_id.user_id
            
            if not target_user_id:
                await event.respond("⚠️ لطفاً روی پیام کاربر ریپلای کنید یا در پی‌وی از این دستور استفاده کنید")
                return
            
            stats = await self.get_chat_stats(chat_id, target_user_id)
            if not stats:
                await event.respond("⚠️ خطا در دریافت آمار")
                return
            
            try:
                target_name = await self.get_user_info(target_user_id)
                my_name = await self.get_user_info(self.my_id)
                
                total_my = stats['my_messages']
                total_target = stats['target_messages']
                
                if total_my > total_target:
                    winner = my_name
                elif total_target > total_my:
                    winner = target_name
                else:
                    winner = "مساوی"
                
                if total_target > 0:
                    ratio = f"{total_my} به {total_target}"
                else:
                    ratio = f"{total_my} به 0"
                
                stats_text = f"""
ꕀꔚꨄꕣꕥ✺ღდ
📊 آمار گفتگو
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
نوع                {my_name[:10]}        {target_name[:10]}
────────────────────────────────────
💬 پیام            {total_my:>5}        {total_target:>5}
📸 عکس             {stats['my_photos']:>5}        {stats['target_photos']:>5}
🎙️ ویس             {stats['my_voices']:>5}        {stats['target_voices']:>5}
🎬 ویدیو           {stats['my_videos']:>5}        {stats['target_videos']:>5}
🎨 استیکر          {stats['my_stickers']:>5}        {stats['target_stickers']:>5}
🎞️ گیف             {stats['my_gifs']:>5}        {stats['target_gifs']:>5}
📁 فایل            {stats['my_files']:>5}        {stats['target_files']:>5}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 بیشترین پیام: {winner}
📈 نسبت: {ratio}
ꕀꔚꨄꕣꕥ✺ღდ
                """
                await self.client.send_message(chat_id, stats_text)
            except Exception as e:
                await event.respond(f"⚠️ خطا: {str(e)[:100]}")
            return
        
        if cmd == '.کد' and not args:
            await event.delete()
            try:
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    if reply_msg.text:
                        qr_path, text = await self.generate_qr_code(reply_msg.text)
                    elif reply_msg.photo:
                        qr_path, text = await self.generate_qr_code(reply_msg.media, is_photo=True)
                    else:
                        await event.respond("⚠️ لطفاً روی یک پیام متنی یا عکس ریپلای کنید")
                        return
                else:
                    qr_text = command_text.replace('.کد', '').strip()
                    if qr_text:
                        qr_path, text = await self.generate_qr_code(qr_text)
                    else:
                        await event.respond("⚠️ لطفاً متن یا عکس را مشخص کنید")
                        return
                
                if qr_path and os.path.exists(qr_path):
                    await self.client.send_file(
                        chat_id,
                        qr_path,
                        caption=f"🝰 کد QR\n📝 متن: {text[:100]}{'...' if len(text) > 100 else ''}"
                    )
                    os.remove(qr_path)
                else:
                    await event.respond(f"⚠️ خطا در تولید کد QR: {text}")
            except Exception as e:
                await event.respond(f"⚠️ خطا: {str(e)[:100]}")
            return
        
        if cmd == 'شروع' and not args:
            await event.delete()
            try:
                await event.respond("🌟 سلف‌بات شروع شد")
            except:
                pass
            return
        
        return
    
    async def update_bio_task(self):
        while self.running:
            try:
                await self.update_bio_with_settings()
            except Exception as e:
                logger.error(f"خطا در update_bio_task برای کاربر {self.user_id}: {e}")
            await asyncio.sleep(60)
    
    async def handle_calendar_command(self, event):
        try:
            now = get_now()
            
            time_str = now.strftime('%H:%M:%S')
            time_12 = now.strftime('%I:%M:%S %p')
            weekday = now.strftime('%A')
            persian_weekdays = {
                'Monday': 'دوشنبه', 'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه',
                'Thursday': 'پنج‌شنبه', 'Friday': 'جمعه', 'Saturday': 'شنبه', 'Sunday': 'یک‌شنبه'
            }
            
            jdate = jdatetime.date.fromgregorian(date=now.date())
            gregorian_date = now.date()
            
            try:
                hijri = Gregorian(now.year, now.month, now.day).to_hijri()
                hijri_str = f"{hijri.day} {hijri.month_name()} {hijri.year}"
                hijri_num = f"{hijri.year:04}/{hijri.month:02}/{hijri.day:02}"
            except:
                hijri_str = "محاسبه نشد"
                hijri_num = "۱۴۴۸/۰۱/۰۸ (تقریبی)"
            
            day_of_year = now.timetuple().tm_yday
            week_number = now.isocalendar()[1]
            
            calendar_text = f"""
ꕀꔚꨄꕣꕥ✺ღდ
🕰 ساعت تهران: {time_str}
⌚️ فرمت ۱۲ ساعته: {time_12}
🌐 منطقه زمانی: Asia/Tehran
📌 روز هفته: {persian_weekdays.get(weekday, weekday)}
📅 هفته: {week_number} (هفته سال)
📆 روز سال: {day_of_year}

╭─────── تقویم‌ها ───────╮
│ 📅 شمسی: {jdate.year:04}/{jdate.month:02}/{jdate.day:02}
│     {jdate.day} {jdate.strftime('%B')} {jdate.year}
│ 🌍 میلادی: {gregorian_date.year}/{gregorian_date.month:02}/{gregorian_date.day:02}
│     {gregorian_date.strftime('%d %B %Y')}
│ 🌙 قمری: {hijri_num}
│     {hijri_str}
╰────────────────────────╯

خلاصه شیک:
الان ساعت {time_str} است؛ تاریخ امروز در تقویم شمسی {jdate.year:04}/{jdate.month:02}/{jdate.day:02}، میلادی {gregorian_date.year}/{gregorian_date.month:02}/{gregorian_date.day:02} و قمری {hijri_num} می‌باشد.

⚠️ قمری: تقریبی، ممکن است با رؤیت هلال ۱ روز اختلاف داشته باشد
ꕀꔚꨄꕣꕥ✺ღდ
            """
            
            settings = db.get_selfbot_settings(self.user_id)
            text, entities = await apply_text_style(calendar_text, settings.get('text_style'))
            await self.client.send_message(event.chat_id, text, formatting_entities=entities)
            await event.delete()
            
        except Exception as e:
            logger.error(f"خطا در تقویم: {e}")
            await event.edit("❌ خطا در دریافت اطلاعات تقویم")
    
    def get_full_date_info(self):
        now = get_now()
        try:
            jdate = jdatetime.date.fromgregorian(date=now.date())
            hijri = Gregorian(now.year, now.month, now.day).to_hijri()
            persian_weekdays = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یک‌شنبه"]
            gregorian_weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            return f"""
ꕀꔚꨄꕣꕥ✺ღდ
📅 تاریخ کامل
━━━━━━━━━━━━━━━━━━━━
🕐 ساعت: {now.strftime('%H:%M:%S')}
📆 شمسی:
{persian_weekdays[jdate.weekday()]} - {jdate.day} {jdate.strftime('%B')} {jdate.year}
📆 میلادی:
{gregorian_weekdays[now.weekday()]} - {now.strftime('%B %d, %Y')}
📆 قمری:
{hijri.day} {hijri.month_name()} {hijri.year}
━━━━━━━━━━━━━━━━━━━━
ꕀꔚꨄꕣꕥ✺ღდ
            """
        except:
            return f"📅 تاریخ: {now.strftime('%Y/%m/%d %H:%M:%S')}"
    
    async def get_chat_stats(self, chat_id, target_user_id=None):
        try:
            stats = {
                'my_messages': 0,
                'target_messages': 0,
                'my_photos': 0,
                'target_photos': 0,
                'my_videos': 0,
                'target_videos': 0,
                'my_stickers': 0,
                'target_stickers': 0,
                'my_gifs': 0,
                'target_gifs': 0,
                'my_voices': 0,
                'target_voices': 0,
                'my_files': 0,
                'target_files': 0
            }
            target_user = target_user_id or chat_id
            limit = 5000
            async for message in self.client.iter_messages(chat_id, limit=limit):
                if message.sender_id == self.my_id:
                    stats['my_messages'] += 1
                    if message.photo:
                        stats['my_photos'] += 1
                    elif message.video:
                        stats['my_videos'] += 1
                    elif message.sticker:
                        stats['my_stickers'] += 1
                    elif message.gif:
                        stats['my_gifs'] += 1
                    elif message.voice:
                        stats['my_voices'] += 1
                    elif message.document:
                        stats['my_files'] += 1
                elif message.sender_id == target_user:
                    stats['target_messages'] += 1
                    if message.photo:
                        stats['target_photos'] += 1
                    elif message.video:
                        stats['target_videos'] += 1
                    elif message.sticker:
                        stats['target_stickers'] += 1
                    elif message.gif:
                        stats['target_gifs'] += 1
                    elif message.voice:
                        stats['target_voices'] += 1
                    elif message.document:
                        stats['target_files'] += 1
            return stats
        except Exception as e:
            logger.error(f"خطا در دریافت آمار چت: {e}")
            return None
    
    async def generate_qr_code(self, text_or_photo, is_photo=False):
        try:
            if is_photo:
                photo_path = await self.client.download_media(text_or_photo)
                if photo_path and os.path.exists(photo_path):
                    text = f"Image: {os.path.basename(photo_path)}"
                    os.remove(photo_path)
                else:
                    return None, "خطا در دانلود عکس"
            else:
                text = text_or_photo
            if not text:
                return None, "متن خالی است"
            qr = qrcode.make(text)
            qr_path = f"qr_{self.user_id}_{int(time.time())}.png"
            qr.save(qr_path)
            return qr_path, text
        except Exception as e:
            return None, str(e)
    
    async def get_admins(self, chat_id):
        try:
            admins = []
            async for user in self.client.iter_participants(
                chat_id, 
                filter=ChannelParticipantsAdmins
            ):
                admins.append(user)
            return admins
        except Exception as e:
            logger.error(f"خطا در دریافت ادمین‌ها: {e}")
            return []
    
    async def pin_message(self, chat_id, message_id):
        try:
            await self.client.pin_message(chat_id, message_id)
            return True
        except Exception as e:
            logger.error(f"خطا در پین کردن پیام: {e}")
            return False
    
    async def start_action(self, chat_id, action_name):
        if action_name not in action_types:
            return False
        action = action_types[action_name]
        if chat_id in self.action_tasks:
            try:
                self.action_tasks[chat_id].cancel()
            except Exception:
                pass
        self.active_actions[chat_id] = action_name
        async def permanent_action():
            try:
                try:
                    peer = await self.client.get_input_entity(chat_id)
                except Exception:
                    peer = chat_id
                while self.running and chat_id in self.active_actions:
                    try:
                        await self.client(SetTypingRequest(peer, action))
                    except Exception as e:
                        logger.debug(f"action tick {action_name}: {e}")
                        try:
                            peer = await self.client.get_input_entity(chat_id)
                        except Exception:
                            pass
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"action loop: {e}")
            finally:
                self.active_actions.pop(chat_id, None)
                self.action_tasks.pop(chat_id, None)
        self.action_tasks[chat_id] = asyncio.create_task(permanent_action())
        return True
    
    async def stop_action(self, chat_id):
        name = self.active_actions.pop(chat_id, None)
        task = self.action_tasks.pop(chat_id, None)
        if task:
            try:
                task.cancel()
            except Exception:
                pass
        try:
            peer = await self.client.get_input_entity(chat_id)
            await self.client(SetTypingRequest(peer, types.SendMessageCancelAction()))
        except Exception:
            pass
        return name

    async def cleanup_helper_bot(self, bot_username: str):
        """حذف تاریخچه و بایگانی چت با ربات کمکی (برای هر کاربر جدا)."""
        try:
            entity = await self.client.get_entity(bot_username)
        except Exception as e:
            logger.debug(f"cleanup resolve {bot_username}: {e}")
            return
        # حذف پیام‌های اخیر
        try:
            ids = []
            async for m in self.client.iter_messages(entity, limit=80):
                ids.append(m.id)
            if ids:
                await self.client.delete_messages(entity, ids)
        except Exception as e:
            logger.debug(f"cleanup del msgs {bot_username}: {e}")
        # پاک کردن تاریخچه
        try:
            from telethon.tl.functions.messages import DeleteHistoryRequest
            await self.client(DeleteHistoryRequest(
                peer=entity,
                max_id=0,
                just_clear=True,
                revoke=True
            ))
        except Exception as e:
            logger.debug(f"cleanup history {bot_username}: {e}")
        # بایگانی دیالوگ
        try:
            from telethon.tl.functions.folders import EditPeerFoldersRequest
            from telethon.tl.types import InputFolderPeer
            inp = await self.client.get_input_entity(entity)
            await self.client(EditPeerFoldersRequest([
                InputFolderPeer(peer=inp, folder_id=1)
            ]))
        except Exception as e:
            logger.debug(f"cleanup archive {bot_username}: {e}")

    
    async def spam_enemy(self, enemy_id):
        # اسپم مداوم غیرفعال شد — اسپم فقط روی هر پیام ورودی دشمن انجام می‌شود
        return
        if enemy_id in self.spam_tasks:
            return
        async def spam_task():
            while False and db.is_enemy(self.user_id, enemy_id, 'pv'):
                spam_messages = db.get_enemy_spam_messages(self.user_id)
                if spam_messages:
                    for spam_message in spam_messages:
                        try:
                            settings = db.get_selfbot_settings(self.user_id)
                            text, entities = await apply_text_style(spam_message['text'], settings.get('text_style'))
                            await self.client.send_message(enemy_id, text, formatting_entities=entities)
                        except:
                            pass
                        await asyncio.sleep(1)
                else:
                    for spam_message in SPAM_MESSAGES:
                        try:
                            settings = db.get_selfbot_settings(self.user_id)
                            text, entities = await apply_text_style(spam_message, settings.get('text_style'))
                            await self.client.send_message(enemy_id, text, formatting_entities=entities)
                        except:
                            pass
                        await asyncio.sleep(1)
        self.spam_tasks[enemy_id] = asyncio.create_task(spam_task())
    
    async def update_profile_name(self):
        settings = db.get_selfbot_settings(self.user_id)
        if settings.get('time_enabled'):
            now = get_now()
            current_minute = now.minute
            if self.time_font_indices == 'all':
                font_index = current_minute % len(classic_fonts)
            elif isinstance(self.time_font_indices, list) and self.time_font_indices:
                if hasattr(self, 'time_font_cycle'):
                    self.time_font_cycle = (self.time_font_cycle + 1) % len(self.time_font_indices)
                else:
                    self.time_font_cycle = 0
                font_index = self.time_font_indices[self.time_font_cycle]
                if font_index >= len(classic_fonts):
                    font_index = 0
            else:
                font_index = 0
            time_now = now.strftime("%H:%M")
            time_now_classic = convert_to_classic_font(time_now, font_index)
            try:
                current_name = db.get_current_name(self.user_id)
                if not current_name:
                    current_name = self.BASE_NAME
                if settings.get('flag_enabled'):
                    sel_flags = settings.get('selected_flags', 'all')
                    if sel_flags == 'all' or not sel_flags:
                        use_flags = flags
                    else:
                        use_flags = sel_flags if isinstance(sel_flags, list) else flags
                    if not use_flags:
                        use_flags = flags
                    flag_index = current_minute % len(use_flags)
                    flag = use_flags[flag_index]
                    new_name = f"『 {flag} 』{current_name} {time_now_classic}"
                else:
                    new_name = f"{current_name} | {time_now_classic}"
                await self.client(UpdateProfileRequest(first_name=new_name))
            except:
                pass
    
    async def restore_profile_name(self):
        try:
            current_name = db.get_current_name(self.user_id)
            if current_name:
                await self.client(UpdateProfileRequest(first_name=current_name))
            else:
                original_name = db.get_original_name(self.user_id)
                if original_name:
                    await self.client(UpdateProfileRequest(first_name=original_name))
                    db.set_current_name(self.user_id, original_name)
                    self.BASE_NAME = original_name
        except:
            pass

    async def _backup_current_profile_photo(self):
        """ذخیره عکس پروفایل فعلی قبل از روشن کردن ساعت"""
        try:
            settings = db.get_selfbot_settings(self.user_id)
            if settings.get('profile_clock_backup') and os.path.exists(str(settings.get('profile_clock_backup'))):
                return settings.get('profile_clock_backup')
            os.makedirs(MEDIA_FOLDER, exist_ok=True)
            backup_path = os.path.join(MEDIA_FOLDER, f"pclock_backup_{self.user_id}.jpg")
            path = await self.client.download_profile_photo('me', file=backup_path)
            if path and os.path.exists(path):
                db.update_selfbot_setting(self.user_id, 'profile_clock_backup', path)
                return path
        except Exception as e:
            logger.error(f"backup profile photo: {e}")
        return None

    async def update_profile_clock(self, force=False):
        """بروزرسانی عکس پروفایل با ساعت سایبرپانک روی عکس کاربر"""
        settings = db.get_selfbot_settings(self.user_id)
        if not settings.get('profile_clock_enabled') and not force:
            return False
        try:
            color = settings.get('profile_clock_color') or 'cyan'
            # منبع عکس: بکاپ اصلی یا دانلود فعلی
            source = settings.get('profile_clock_backup')
            if not source or not os.path.exists(str(source)):
                source = await self._backup_current_profile_photo()
            if not source or not os.path.exists(str(source)):
                # آخرین تلاش: دانلود پروفایل فعلی
                tmp = os.path.join(MEDIA_FOLDER, f"pclock_src_{self.user_id}.jpg")
                source = await self.client.download_profile_photo('me', file=tmp)
            if not source or not os.path.exists(str(source)):
                logger.error(f"profile clock: no source photo for {self.user_id}")
                return False
            out = compose_profile_clock_image(str(source), color_name=color)
            if not out or not os.path.exists(out):
                return False
            # حذف عکس فعلی و آپلود جدید
            try:
                me = await self.client.get_me()
                if me.photo:
                    photos = await self.client.get_profile_photos('me', limit=1)
                    if photos:
                        await self.client(DeletePhotosRequest(id=[photos[0]]))
            except Exception as e:
                logger.debug(f"delete old pf: {e}")
            file = await self.client.upload_file(out)
            await self.client(UploadProfilePhotoRequest(file=file))
            try:
                os.remove(out)
            except Exception:
                pass
            self._last_pclock_minute = get_now().minute
            return True
        except Exception as e:
            logger.error(f"update_profile_clock: {e}\n{traceback.format_exc()}")
            return False

    async def restore_profile_clock(self):
        """خاموش کردن ساعت و برگرداندن عکس پروفایل قبلی"""
        try:
            db.update_selfbot_setting(self.user_id, 'profile_clock_enabled', 0)
            settings = db.get_selfbot_settings(self.user_id)
            backup = settings.get('profile_clock_backup')
            # حذف عکس فعلی (ساعت‌دار)
            try:
                me = await self.client.get_me()
                if me.photo:
                    photos = await self.client.get_profile_photos('me', limit=1)
                    if photos:
                        await self.client(DeletePhotosRequest(id=[photos[0]]))
            except Exception:
                pass
            if backup and os.path.exists(str(backup)):
                file = await self.client.upload_file(str(backup))
                await self.client(UploadProfilePhotoRequest(file=file))
            return True
        except Exception as e:
            logger.error(f"restore_profile_clock: {e}")
            return False


    async def video_to_voice(self, event):
        """ریپلای روی ویدیو → استخراج صدا و ارسال ویس در همان چت"""
        try:
            if not event.is_reply:
                await event.edit("⚠️ روی یک ویدیو ریپلای کنید و بنویسید:\n`ویس`")
                return
            reply = await event.get_reply_message()
            if not reply:
                await event.edit("⚠️ پیام ریپلای‌شده پیدا نشد")
                return
            is_video = False
            # انواع ویدیو
            if getattr(reply, 'video', None) is not None:
                is_video = True
            elif getattr(reply, 'video_note', None) is not None:
                is_video = True
            elif getattr(reply, 'gif', None) is not None:
                is_video = True
            elif reply.document:
                mime = (getattr(reply.document, 'mime_type', None) or '').lower()
                if mime.startswith('video/') or mime in ('image/gif',):
                    is_video = True
                # attribute video
                for attr in (getattr(reply.document, 'attributes', None) or []):
                    an = type(attr).__name__
                    if 'Video' in an or 'Animated' in an:
                        is_video = True
                        break
            if not is_video and reply.media:
                # آخرین تلاش: هر مدیایی که دانلود شود و ffmpeg صدا بدهد
                is_video = True
            if not is_video:
                await event.edit("⚠️ لطفاً روی یک ویدیو (یا گیف) ریپلای کنید")
                return
            await event.edit("⏳ در حال تبدیل به ویس...")
            os.makedirs(MEDIA_FOLDER, exist_ok=True)
            base = os.path.join(MEDIA_FOLDER, f"v2v_{self.user_id}_{event.id}")
            vid_path = await self.client.download_media(reply, file=base)
            if not vid_path or not os.path.exists(str(vid_path)):
                await event.edit("❌ دانلود ویدیو ناموفق")
                return
            vid_path = str(vid_path)
            ogg_path = vid_path + ".ogg"
            # چند تلاش ffmpeg
            ff = find_ffmpeg_bin()
            if not ff:
                await event.edit(
                    "❌ ffmpeg روی سرور نصب نیست.\n"
                    "روی Railway/Docker: apt-get install -y ffmpeg\n"
                    "یا متغیر FFMPEG_PATH را ست کنید."
                )
                try:
                    os.remove(vid_path)
                except Exception:
                    pass
                return
            cmds = [
                [ff, "-y", "-i", vid_path, "-vn", "-acodec", "libopus", "-b:a", "64k", "-ac", "1", "-ar", "48000", ogg_path],
                [ff, "-y", "-i", vid_path, "-vn", "-c:a", "libopus", "-b:a", "48k", ogg_path],
                [ff, "-y", "-i", vid_path, "-vn", "-acodec", "libopus", ogg_path],
            ]
            ok = False
            last_err = ""
            for cmd in cmds:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await proc.communicate()
                    if proc.returncode == 0 and os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 100:
                        ok = True
                        break
                    last_err = (stderr or b"").decode("utf-8", errors="ignore")[-200:]
                    try:
                        if os.path.exists(ogg_path):
                            os.remove(ogg_path)
                    except Exception:
                        pass
                except Exception as e:
                    last_err = str(e)
            if not ok:
                await event.edit(f"❌ استخراج صدا ناموفق\n{last_err[:120]}")
                try:
                    os.remove(vid_path)
                except Exception:
                    pass
                return
            await self.client.send_file(
                event.chat_id,
                ogg_path,
                voice_note=True,
                reply_to=reply.id,
            )
            try:
                await event.delete()
            except Exception:
                try:
                    await event.edit("✅ ویس ارسال شد")
                except Exception:
                    pass
            for p in (vid_path, ogg_path):
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"video_to_voice: {e}\n{traceback.format_exc()}")
            try:
                await event.edit(f"❌ خطا: {str(e)[:100]}")
            except Exception:
                pass


    async def update_profile_task(self):
        while self.running:
            try:
                await self.update_profile_name()
            except Exception as e:
                logger.error(f"خطا در update_profile_task برای کاربر {self.user_id}: {e}")
            # ساعت روی پروفایل — فقط وقتی دقیقه عوض شد
            try:
                settings = db.get_selfbot_settings(self.user_id)
                if settings.get('profile_clock_enabled'):
                    cur_min = get_now().minute
                    last = getattr(self, '_last_pclock_minute', None)
                    if last is None or last != cur_min:
                        await self.update_profile_clock()
            except Exception as e:
                logger.error(f"profile_clock task: {e}")
            await asyncio.sleep(20)
    
    async def heart_animation(self, chat_id):
        try:
            entity = await self.client.get_entity(chat_id)
            message = await self.client.send_message(entity, HEARTS[0])
            for i in range(1, len(HEARTS) * 3):
                await asyncio.sleep(0.8)
                try:
                    await message.edit(HEARTS[i % len(HEARTS)])
                except Exception:
                    break
        except Exception as e:
            logger.error(f"heart_animation: {e}")
    
    async def moon_animation(self, chat_id):
        try:
            entity = await self.client.get_entity(chat_id)
            message = await self.client.send_message(entity, MOONS[0])
            for i in range(1, len(MOONS) * 3):
                await asyncio.sleep(0.8)
                try:
                    await message.edit(MOONS[i % len(MOONS)])
                except Exception:
                    break
        except Exception as e:
            logger.error(f"moon_animation: {e}")
    
    async def resolve_user_entity(self, user_id):
        """Resolve user even if not in dialogs (numeric ID)."""
        uid = int(user_id)
        try:
            return await self.client.get_entity(uid)
        except Exception:
            pass
        try:
            from telethon.tl.functions.users import GetUsersRequest
            from telethon.tl.types import InputUser
            users = await self.client(GetUsersRequest([InputUser(uid, 0)]))
            if users and users[0]:
                return users[0]
        except Exception:
            pass
        try:
            from telethon.tl.types import InputPeerUser
            return await self.client.get_entity(InputPeerUser(uid, 0))
        except Exception:
            pass
        return None

    @staticmethod
    def _utf16_len(s):
        return len((s or '').encode('utf-16-le')) // 2

    async def get_display_name(self, user_id):
        uid = int(user_id)
        entity = await self.resolve_user_entity(uid)
        if entity is not None:
            uname = getattr(entity, 'username', None)
            fname = (getattr(entity, 'first_name', None) or '').strip()
            lname = (getattr(entity, 'last_name', None) or '').strip()
            if uname:
                return f"@{uname}", entity
            if fname or lname:
                return f"{fname} {lname}".strip(), entity
        return f"کاربر {uid}", entity

    async def get_user_info(self, user_id, clickable=True):
        """نام نمایشی — برای گزارش‌ها فقط متن ساده (entity جدا اضافه می‌شود)."""
        display, _ = await self.get_display_name(user_id)
        return display

    def make_mention_entity(self, display, user_id, offset):
        """MessageEntityMentionName روی نام — کلیک = باز شدن پیوی."""
        from telethon.tl.types import MessageEntityMentionName, MessageEntityTextUrl
        length = self._utf16_len(display)
        uid = int(user_id)
        try:
            return MessageEntityMentionName(offset=offset, length=length, user_id=uid)
        except Exception:
            return MessageEntityTextUrl(offset=offset, length=length, url=f"tg://user?id={uid}")

    async def send_clickable_user(self, chat_id, text_prefix, user_id, text_suffix=''):
        display, entity = await self.get_display_name(user_id)
        full = f"{text_prefix}{display}{text_suffix}"
        start = self._utf16_len(text_prefix)
        ent = self.make_mention_entity(display, user_id, start)
        await self.client.send_message(chat_id, full, formatting_entities=[ent])
        return full

    async def build_text_with_user_mentions(self, parts):
        """parts: لیست str یا tuple(user_id,) برای منشن.
        مثال: ["🗑️ حذف\n👤 از: ", (sender_id,), "\n💬 چت: x"]
        """
        text = ''
        entities = []
        for p in parts:
            if isinstance(p, tuple):
                uid = int(p[0])
                display, _ = await self.get_display_name(uid)
                off = self._utf16_len(text)
                entities.append(self.make_mention_entity(display, uid, off))
                text += display
            else:
                text += str(p)
        return text, entities

    
    def format_status_info(self, settings):
        try:
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM user_memory')
            user_count = cursor.fetchone()[0]
            conn.close()
        except:
            user_count = 0
        pv_enemies = len(db.get_enemies(self.user_id, 'pv'))
        comment_channels = len(self.auto_comment_settings)
        cached_media = len([m for m in media_cache.values() if m.get('owner_id') == self.user_id])
        spam_settings = db.get_spam_settings(self.user_id)
        filter_words = db.get_filter_words(self.user_id)
        active_filters = len([w for w in filter_words if w['enabled']])
        spam_messages = len(db.get_enemy_spam_messages(self.user_id))
        font_info = "همه فونت‌ها" if self.time_font_indices == 'all' else f"فونت‌های {self.time_font_indices}"
        ai_status = settings.get('ai_status', {})
        active_ai_pm = "هیچ هوش فعالی در پی‌وی وجود ندارد"
        if ai_status.get('ai_1_pm'):
            active_ai_pm = "هوش ۱ (Gemini)"
        elif ai_status.get('ai_2_pm'):
            active_ai_pm = "هوش ۲ (Paxsenix API)"
        elif ai_status.get('ai_3_pm'):
            active_ai_pm = "هوش ۳ (DeepSeek)"
        active_ai_group = "هیچ هوش فعالی در گروه وجود ندارد"
        if ai_status.get('ai_1_group'):
            active_ai_group = "هوش ۱ (Gemini)"
        elif ai_status.get('ai_2_group'):
            active_ai_group = "هوش ۲ (Paxsenix API)"
        elif ai_status.get('ai_3_group'):
            active_ai_group = "هوش ۳ (DeepSeek)"
        filter_status = "فعال" if db.get_filter_enabled(self.user_id) else "غیرفعال"
        text_style = settings.get('text_style') or "هیچکدام"
        locked_pvs = db.get_locked_pvs(self.user_id)
        pv_lock_all = settings.get('pv_lock_all', False)
        translate_status = []
        for lang, status in self.translate_mode.items():
            if status:
                translate_status.append(lang)
        translate_text = "، ".join(translate_status) if translate_status else "هیچکدام"
        selfbot_status = "فعال" if settings.get('selfbot_enabled', 1) else "غیرفعال"
        autosend_status = "فعال" if self.autosend_mode else "غیرفعال"
        bio_time1 = self.get_bio_setting('ساعت_در_بیو')
        bio_time2 = self.get_bio_setting('ساعت_در_بیو_۲')
        bio_date = self.get_bio_setting('بیو_تاریخ')
        bio_full = self.get_bio_setting('بیو_کامل')
        bio_love = self.get_bio_setting('بیو_عاشقانه')
        monshi_data = db.get_monshi_status(self.user_id)
        answers_count = len(db.get_answers(self.user_id))
        
        return f"""
ꕀꔚꨄꕣꕥ✺ღდ
وضعیت کامل سلف‌بات
━━━━━━━━━━━━━━━━━━━━
🤖 وضعیت سلف‌بات: {selfbot_status}
🔍 حالت سرچ: {'فعال' if self.search_mode else 'غیرفعال'}
🕐 تایم روی پروفایل: {'فعال' if settings.get('time_enabled') else 'غیرفعال'}
🏳️ پرچم در تایم: {'فعال' if settings.get('flag_enabled') else 'غیرفعال'}
🎨 فونت تایم: {font_info}
🔄 اتوسین: {autosend_status}

📝 تنظیمات بیو:
• ساعت در بیو: {bio_time1}
• ساعت در بیو ۲: {bio_time2}
• بیو تاریخ: {bio_date}
• بیو کامل: {bio_full}
• بیو عاشقانه: {bio_love}

🤖 هوش مصنوعی:
• پی‌وی: {active_ai_pm}
• گروه: {active_ai_group}

✍️ استایل متن: {text_style}

🔒 قفل پیوی همگانی: {'فعال' if pv_lock_all else 'غیرفعال'}
🔒 پی‌وی‌های قفل‌شده: {len(locked_pvs)}
🚫 فیلتر کلمات: {filter_status}

🌐 ترجمه فعال: {translate_text}

📊 آمار:
• دشمنان پیوی: {pv_enemies}
• کانال‌های نظر‌دهی: {comment_channels}
• رسانه‌های ذخیره‌شده: {cached_media}
• کلمات فیلتر فعال: {active_filters}
• پیام‌های اسپم ذخیره شده: {spam_messages}
• کاربران ذخیره شده: {user_count}

🛡️ حفاظت اسپم:
• وضعیت: {'فعال' if spam_settings.get('spam_protection') else 'غیرفعال'}
• محدودیت: {spam_settings.get('spam_limit', 10)} پیام در {spam_settings.get('mute_duration', 10)} ثانیه

🤖 منشی هوشمند:
• وضعیت: {'فعال' if monshi_data['status'] else 'غیرفعال'}
• پاسخ: {monshi_data['answer'][:30] if monshi_data['answer'] else 'تنظیم نشده'}
• تعداد پاسخ‌ها: {answers_count}

📊 گروه گزارش: {self.report_config.report_group_id}
💾 ذخیره خودکار رسانه: {'فعال' if self.report_config.auto_save_media else 'غیرفعال'}
━━━━━━━━━━━━━━━━━━━━
✅ Self-Bot v{BOT_VERSION}
ꕀꔚꨄꕣꕥ✺ღდ
        """
    
    async def handle_new_message(self, event):
        if not self.my_id:
            return
        
        await self.auto_sync_message(event)
        
        settings = db.get_selfbot_settings(self.user_id)
        if not settings.get('selfbot_enabled', 1):
            return
        chat_id = None
        peer_id = event.message.peer_id
        if isinstance(peer_id, PeerChannel):
            chat_id = peer_id.channel_id
        elif isinstance(peer_id, PeerUser):
            chat_id = peer_id.user_id
        elif isinstance(peer_id, PeerChat):
            chat_id = peer_id.chat_id
        else:
            return
        
        # منشی: فقط پیوی — فقط یک‌بار برای هر کاربر
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out and event.message.text:
            monshi_data = db.get_monshi_status(self.user_id)
            if monshi_data['status'] and monshi_data['answer']:
                peer = event.message.peer_id.user_id
                try:
                    if not db.was_monshi_sent(self.user_id, peer):
                        await event.reply(monshi_data['answer'])
                        db.mark_monshi_sent(self.user_id, peer)
                        return
                except Exception:
                    pass

        # یادگیری: گروه + پیوی
        if not event.message.out and event.message.text:
            try:
                learning_on = getattr(self, 'learning_enabled', True)
                if learning_on is None:
                    learning_on = db.get_learning_enabled(self.user_id)
                if learning_on:
                    answers = db.get_answers(self.user_id)
                    if answers:
                        txt = event.message.text
                        for question, answer in answers.items():
                            if question and question in txt:
                                try:
                                    await event.reply(answer)
                                except Exception:
                                    pass
                                break
            except Exception as _le:
                logger.debug(f"learning reply: {_le}")
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            if settings.get('pv_lock_all'):
                try:
                    await event.message.delete()
                    return
                except:
                    pass
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            if db.is_pv_locked(self.user_id, event.sender_id):
                try:
                    await event.message.delete()
                    return
                except:
                    pass
        
        if await self.handle_media_lock_delete(event):
            return
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out and event.message.text:
            db.cache_message(self.user_id, chat_id, event.message.id, event.message.text)
        
        if not event.message.out:
            if db.get_filter_enabled(self.user_id):
                check_text = (event.message.text or event.message.message or "") or ""
                # کپشن مدیا
                if not check_text and getattr(event.message, 'media', None):
                    check_text = getattr(event.message, 'message', None) or ""
                if check_text:
                    filter_words = db.get_filter_words(self.user_id)
                    low = check_text.lower()
                    for word_info in filter_words:
                        w = (word_info.get('word') or '').strip()
                        if word_info.get('enabled') and w and w.lower() in low:
                            try:
                                await event.message.delete()
                                return
                            except Exception:
                                pass
        
        # ========== اسپم دشمن (پیوی / گروه) — یک اسپم تصادفی به ازای هر پیام، بدون تکرار پشت‌سرهم ==========
        if not event.message.out and event.sender_id:
            try:
                sender_id = int(event.sender_id)
                is_pv = isinstance(event.message.peer_id, PeerUser)
                chat_type = 'pv' if is_pv else 'group'
                if db.is_enemy(self.user_id, sender_id, chat_type):
                    spam_list = db.get_enemy_spam_messages(self.user_id)
                    candidates = []
                    if spam_list:
                        candidates = [s['text'] for s in spam_list]
                    elif SPAM_MESSAGES:
                        candidates = list(SPAM_MESSAGES)
                    if not candidates:
                        candidates = ["..."]
                    # جلوگیری از تکرار پشت‌سرهم همان متن برای یک دشمن
                    last_key = f"_last_spam_{sender_id}_{chat_type}"
                    last_text = getattr(self, last_key, None)
                    if len(candidates) > 1 and last_text in candidates:
                        choices = [c for c in candidates if c != last_text]
                        spam_text = random.choice(choices)
                    else:
                        spam_text = random.choice(candidates)
                    setattr(self, last_key, spam_text)
                    sent = False
                    try:
                        settings_e = db.get_selfbot_settings(self.user_id)
                        style = settings_e.get('text_style') if settings_e else None
                        text_s, entities = await apply_text_style(spam_text, style)
                        await event.reply(text_s, formatting_entities=entities if entities else None)
                        sent = True
                    except Exception as e:
                        logger.debug(f"اسپم دشمن reply: {e}")
                    if not sent:
                        try:
                            await self.client.send_message(event.chat_id, spam_text, reply_to=event.message.id)
                            sent = True
                        except Exception as e2:
                            logger.error(f"اسپم دشمن send: {e2}")
                    if sent:
                        logger.info(f"اسپم دشمن → user={sender_id} type={chat_type}")
            except Exception as e:
                logger.error(f"خطا در اسپم دشمن: {e}")
        
        # ========== ریکشن خودکار (پیوی + گروه + سوپرگروه + کانال) ==========
        report_short_id = full_chat_id_to_short(self.report_config.report_group_id)
        if not event.message.out and event.sender_id and chat_id != report_short_id:
            sender_id = event.sender_id
            try:
                # chat_id ممکن است short یا full باشد؛ هر دو را چک می‌کنیم
                reaction = db.get_reaction(self.user_id, chat_id, sender_id)
                if not reaction:
                    # fallback: full chat id (مثلاً -100xxx)
                    try:
                        full_cid = event.chat_id
                        if full_cid and full_cid != chat_id:
                            reaction = db.get_reaction(self.user_id, full_cid, sender_id)
                            if reaction:
                                chat_id = full_cid  # برای سازگاری بعدی
                    except Exception:
                        pass
                if reaction and reaction in ALLOWED_EMOJIS:
                    reacted = False
                    for peer_getter in (
                        lambda: event.get_input_chat(),
                        lambda: self.client.get_input_entity(event.chat_id),
                        lambda: self.client.get_input_entity(chat_id),
                    ):
                        if reacted:
                            break
                        try:
                            peer = await peer_getter()
                            await self.client(SendReactionRequest(
                                peer=peer,
                                msg_id=event.message.id,
                                reaction=[ReactionEmoji(emoticon=reaction)]
                            ))
                            reacted = True
                        except ChatWriteForbiddenError:
                            logger.warning(f"⚠️ اجازه ریکت در چت {chat_id} نیست")
                            break
                        except FloodWaitError as fl:
                            await asyncio.sleep(min(getattr(fl, 'seconds', 5), 20))
                        except Exception as e:
                            logger.debug(f"ریکت تلاش ناموفق: {e}")
                    if not reacted:
                        logger.error(f"خطا در ارسال ریکت خودکار برای {sender_id} در {chat_id}")
            except Exception as e:
                logger.error(f"خطا در دریافت ریکت از دیتابیس: {e}")
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            sender_id = event.sender_id
            ai_status = settings.get('ai_status', {})
            ai_active = False
            ai_type = None
            if event.message.text:
                if ai_status.get('ai_1_pm'):
                    ai_active = True
                    ai_type = 1
                elif ai_status.get('ai_2_pm'):
                    ai_active = True
                    ai_type = 2
                elif ai_status.get('ai_3_pm'):
                    ai_active = True
                    ai_type = 3
            if ai_active and ai_type:
                try:
                    await self.client(SetTypingRequest(event.chat_id, types.SendMessageTypingAction()))
                    response = await get_ai_response(event.message.text, ai_type, self.user_id)
                    if response:
                        text, entities = await apply_text_style(response, settings.get('text_style'))
                        await event.reply(text, formatting_entities=entities)
                    else:
                        await event.reply("❌ خطا در ارتباط با هوش مصنوعی. لطفاً بعداً تلاش کنید.")
                except Exception as e:
                    logger.error(f"خطا در پاسخ هوش مصنوعی: {e}")
        
        spam_settings = db.get_spam_settings(self.user_id)
        if spam_settings.get('spam_protection') and not event.message.out:
            sender_id = event.sender_id
            chat_key = f"{chat_id}_{sender_id}"
            
            mute_until = self.mute_timestamps.get(chat_key, 0)
            if time.time() < mute_until:
                try:
                    await event.message.delete()
                    return
                except:
                    pass
            
            if chat_key not in self.spam_counters:
                self.spam_counters[chat_key] = []
            now = time.time()
            mute_duration = spam_settings.get('mute_duration', 10)
            spam_limit = spam_settings.get('spam_limit', 10)
            
            self.spam_counters[chat_key] = [t for t in self.spam_counters[chat_key] if now - t <= mute_duration]
            self.spam_counters[chat_key].append(now)
            
            if len(self.spam_counters[chat_key]) > spam_limit:
                try:
                    await event.message.delete()
                    self.mute_timestamps[chat_key] = now + mute_duration
                    logger.info(f"کاربر {sender_id} در چت {chat_id} به مدت {mute_duration} ثانیه سکوت شد")
                except:
                    pass
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            sender_id = event.sender_id
            try:
                sender = await event.get_sender()
                if sender:
                    username = sender.username if sender.username else None
                    first_name = sender.first_name if sender.first_name else ""
                    last_name = sender.last_name if sender.last_name else ""
                    db.update_user_memory(sender_id, username, first_name, last_name, chat_id)
            except:
                pass
    
    async def handle_media_lock_delete(self, event):
        if not event.message or event.message.out:
            return False
        target_id = event.sender_id
        if target_id == self.my_id:
            return False
        message = event.message
        message_text = message.text or ""
        lock_types = {
            'lock_link': is_link_message,
            'lock_text': lambda x: bool(x and not is_link_message(x) and not is_emoji_message(x)),
            'lock_emoji': is_emoji_message,
            'lock_photo': lambda x: message.photo,
            'lock_video': lambda x: message.video,
            'lock_sticker': lambda x: message.sticker,
            'lock_gif': lambda x: message.gif,
            'lock_voice': lambda x: message.voice,
            'lock_file': lambda x: message.document and not message.sticker and not message.gif,
            'lock_music': lambda x: message.audio,
            'lock_video_note': lambda x: message.video_note,
            'lock_contact': lambda x: message.contact,
            'lock_location': lambda x: message.geo
        }
        for lock_type, check_func in lock_types.items():
            if db.get_user_lock(self.user_id, 0, lock_type):
                if check_func(message_text):
                    try:
                        await message.delete()
                        return True
                    except:
                        pass
        for lock_type, check_func in lock_types.items():
            if db.get_user_lock(self.user_id, target_id, lock_type):
                if check_func(message_text):
                    try:
                        await message.delete()
                        return True
                    except:
                        pass
        return False
    
    async def handle_edited_message(self, event):
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            sender = await event.get_sender()
            if sender.id == self.my_id:
                return
            settings = db.get_selfbot_settings(self.user_id)
            if settings.get('pv_lock_all') and sender.id != self.my_id:
                try:
                    await event.message.delete()
                    return
                except:
                    pass
            if db.is_pv_locked(self.user_id, sender.id):
                try:
                    await event.message.delete()
                    return
                except:
                    pass
            if self.report_config.report_edited_messages:
                message_id = event.message.id
                chat_id = event.message.peer_id.user_id
                original_text = message_cache.get((chat_id, message_id), "نامشخص")
                new_text = event.message.text or "بدون متن"
                try:
                    sender_info = await self.get_user_info(sender.id)
                    report_text = (
                        f"✍️ پیام ویرایش‌شده\n"
                        f"👤 از: {sender_info}\n"
                        f"🆔 پیام: {message_id}\n"
                        f"📝 متن اصلی:\n{original_text[:1000]}\n"
                        f"📝 متن جدید:\n{new_text[:1000]}\n"
                        f"🕒 زمان: {get_now().strftime('%Y/%m/%d %H:%M:%S')}"
                    )
                    await self.send_report(report_text)
                except Exception as e:
                    logger.error(f"خطا در گزارش ویرایش پیام: {e}")
            db.cache_message(self.user_id, event.message.peer_id.user_id, event.message.id, event.message.text or "")
    
    async def handle_deleted_message(self, event):
        if not self.report_config.report_deleted_media:
            return
        for msg_id in event.deleted_ids:
            if msg_id in media_cache and media_cache[msg_id].get('owner_id') == self.user_id:
                try:
                    media_info = media_cache[msg_id]
                    sid = int(media_info['user_id'])
                    chat_title = await self.get_chat_title(media_info['chat_id'])
                    file_exists = os.path.exists(media_info['path']) if media_info.get('path') else False
                    report_text, ents = await self.build_text_with_user_mentions([
                        "🗑️ رسانه حذف‌شده\n👤 از: ",
                        (sid,),
                        f"\n💬 چت: {chat_title}\n"
                        f"📦 نوع: {media_info['type']}\n"
                        f"🆔 پیام: {msg_id}\n"
                        f"📝 کپشن: {str(media_info.get('caption', 'بدون کپشن') or 'بدون کپشن')[:200]}\n"
                        f"💾 فایل ذخیره‌شده: {'✅' if file_exists else '❌'}\n"
                        f"📏 حجم: {media_info.get('file_size', 0) / 1024:.1f} KB\n"
                        f"🕒 زمان ارسال: {media_info.get('timestamp', 'نامشخص')}\n"
                        f"🕒 زمان حذف: {get_now().strftime('%Y/%m/%d %H:%M:%S')}\n"
                        f"🔗 روی اسم کلیک کن → پیوی"
                    ])
                    if file_exists:
                        await self.send_report(report_text, media_info['path'], report_text, entities=ents)
                    else:
                        await self.send_report(report_text, entities=ents)
                    del media_cache[msg_id]
                except Exception as e:
                    logger.error(f"خطا در گزارش حذف رسانه {msg_id}: {e}")
                    if msg_id in media_cache:
                        del media_cache[msg_id]
            for (chat_id, cached_msg_id), cached in list(message_cache.items()):
                if cached_msg_id == msg_id:
                    try:
                        if isinstance(cached, dict):
                            text = cached.get('text', '')
                            sender_id = cached.get('sender_id') or chat_id
                            owner = cached.get('owner_id')
                            if owner and str(owner) != str(self.user_id):
                                continue
                        else:
                            text = str(cached)
                            sender_id = chat_id
                        chat_title = await self.get_chat_title(chat_id)
                        report_text, ents = await self.build_text_with_user_mentions([
                            "🗑️ پیام متنی حذف‌شده\n👤 از: ",
                            (int(sender_id),),
                            f"\n💬 چت: {chat_title}\n"
                            f"🆔 پیام: {msg_id}\n"
                            f"📝 متن پیام:\n{(text[:1000] if text else 'بدون متن')}\n"
                            f"🕒 زمان: {get_now().strftime('%Y/%m/%d %H:%M:%S')}\n"
                            f"🔗 روی اسم کلیک کن → پیوی"
                        ])
                        await self.send_report(report_text, entities=ents)
                        del message_cache[(chat_id, msg_id)]
                    except Exception as e:
                        logger.error(f"خطا در گزارش حذف پیام: {e}")
                        if (chat_id, msg_id) in message_cache:
                            del message_cache[(chat_id, msg_id)]
    
    async def handle_report_message(self, event):
        try:
            message = event.message
            if not message:
                return
            # فقط پیام‌هایی که به من ریپلای شده یا تگ/منشن شده‌ام را برای گزارش حذف کش کن
            try:
                if not message.out and (message.text or message.media):
                    involves_me = False
                    # ریپلای روی پیام من
                    try:
                        if message.is_reply:
                            replied = await message.get_reply_message()
                            if replied and getattr(replied, 'sender_id', None) == self.my_id:
                                involves_me = True
                            if replied and getattr(replied, 'out', False):
                                involves_me = True
                    except Exception:
                        pass
                    # منشن / تگ من
                    try:
                        if message.mentioned:
                            involves_me = True
                        if message.entities:
                            from telethon.tl.types import MessageEntityMentionName, MessageEntityMention
                            for ent in message.entities:
                                if isinstance(ent, MessageEntityMentionName) and ent.user_id == self.my_id:
                                    involves_me = True
                                if isinstance(ent, MessageEntityMention) and message.text:
                                    frag = message.text[ent.offset:ent.offset+ent.length]
                                    me = await self.client.get_me()
                                    if me and me.username and frag.lower().replace('@','') == me.username.lower():
                                        involves_me = True
                    except Exception:
                        pass
                    # در پیوی همیشه گزارش (چون مخاطب مستقیم)
                    if isinstance(message.peer_id, PeerUser):
                        involves_me = True
                    if involves_me:
                        sender_id = message.sender_id or (message.peer_id.user_id if isinstance(message.peer_id, PeerUser) else None)
                        peer = message.peer_id
                        if isinstance(peer, PeerUser):
                            chat_key = peer.user_id
                        elif hasattr(peer, 'channel_id'):
                            chat_key = int(f"-100{peer.channel_id}") if peer.channel_id else peer.channel_id
                        elif hasattr(peer, 'chat_id'):
                            chat_key = -peer.chat_id if peer.chat_id > 0 else peer.chat_id
                        else:
                            chat_key = getattr(message, 'chat_id', None)
                        if sender_id and chat_key is not None:
                            message_cache[(chat_key, message.id)] = {
                                'text': message.text or '',
                                'sender_id': int(sender_id),
                                'owner_id': self.user_id,
                                'involves_me': True,
                            }
            except Exception as _ce:
                logger.debug(f"message cache: {_ce}")
            if isinstance(message.peer_id, PeerUser) and not message.out:
                if message.media:
                    media_type = self.get_media_type(message)
                    if media_type:
                        saved_path = await self.save_media(message, media_type)
                        if self.report_config.report_ttl_media and hasattr(message.media, 'ttl_seconds') and message.media.ttl_seconds:
                            sender_info = await self.get_user_info(message.sender_id)
                            if saved_path:
                                await self.send_report(
                                    f"⏰ رسانه نابودشونده دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"⏱️ زمان باقی‌مانده: {message.media.ttl_seconds} ثانیه\n"
                                    f"💾 ذخیره شده: ✅",
                                    saved_path,
                                    f"⏰ {media_type} نابودشونده از {sender_info}"
                                )
                            else:
                                await self.send_report(
                                    f"⏰ رسانه نابودشونده دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"⏱️ زمان باقی‌مانده: {message.media.ttl_seconds} ثانیه\n"
                                    f"💾 ذخیره شده: ❌"
                                )
                        elif hasattr(message.media, 'noforwards') and message.media.noforwards:
                            sender_info = await self.get_user_info(message.sender_id)
                            if saved_path:
                                await self.send_report(
                                    f"🚫 رسانه یک‌بارمصرف دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"💾 ذخیره شده: ✅",
                                    saved_path,
                                    f"🚫 {media_type} یک‌بارمصرف از {sender_info}"
                                )
                            else:
                                await self.send_report(
                                    f"🚫 رسانه یک‌بارمصرف دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"💾 ذخیره شده: ❌"
                                )
        except Exception as e:
            logger.error(f"خطا در پردازش گزارش پیام: {e}")
    

    async def run_backup(self, event, target, count=10, media_filter='همه'):
        """بکاپ پیام‌ها از کانال/گروه/پیوی به گروه گزارش."""
        report_gid = self.report_config.report_group_id
        if not report_gid:
            await event.edit("❌ گروه گزارش تنظیم نشده. اول `تنظیم گزارش` در گروه بزنید.")
            return
        # resolve target
        entity = None
        try:
            if str(target).lstrip('-').isdigit():
                tid = int(target)
                try:
                    entity = await self.client.get_entity(tid)
                except Exception:
                    entity = await self.resolve_user_entity(tid) if tid > 0 else None
                    if entity is None and tid < 0:
                        from telethon.tl.types import PeerChannel, PeerChat
                        try:
                            entity = await self.client.get_entity(PeerChannel(int(str(abs(tid)).replace('100', '', 1)) if str(abs(tid)).startswith('100') else abs(tid)))
                        except Exception:
                            try:
                                entity = await self.client.get_entity(tid)
                            except Exception:
                                pass
            else:
                entity = await self.client.get_entity(target)
        except Exception as e:
            await event.edit(f"❌ هدف پیدا نشد: {e}")
            return
        if entity is None:
            await event.edit("❌ هدف پیدا نشد")
            return

        filt = (media_filter or 'همه').strip().lower()
        want_video = filt in ('فیلم', 'ویدیو', 'video', 'videos')
        want_photo = filt in ('عکس', 'تصویر', 'photo', 'photos')
        want_text = filt in ('متن', 'text', 'پیام')
        want_link = filt in ('لینک', 'link', 'links')
        want_all = filt in ('همه', 'all', 'همه‌چیز', 'هرچی', '')

        collected = []
        try:
            async for msg in self.client.iter_messages(entity, limit=min(count * 5, 3000)):
                if len(collected) >= count:
                    break
                if not msg:
                    continue
                ok = False
                if want_all:
                    ok = True
                elif want_video and msg.video:
                    ok = True
                elif want_photo and msg.photo:
                    ok = True
                elif want_text and msg.text and not msg.media:
                    ok = True
                elif want_link and msg.text and ('http://' in msg.text or 'https://' in msg.text or 't.me/' in msg.text):
                    ok = True
                elif want_video and msg.document and getattr(msg.document, 'mime_type', '') and 'video' in msg.document.mime_type:
                    ok = True
                if ok:
                    collected.append(msg)
        except Exception as e:
            await event.edit(f"❌ خطا در خواندن پیام‌ها (ممکن است دسترسی نداشته باشید): {e}")
            return

        if not collected:
            await event.edit("⚠️ پیامی مطابق فیلتر پیدا نشد")
            return

        header = f"📦 بکاپ از `{target}` — {len(collected)} مورد — فیلتر: {media_filter}"
        try:
            await self.client.send_message(report_gid, header)
        except Exception as e:
            await event.edit(f"❌ ارسال به گروه گزارش ناموفق: {e}")
            return

        sent = 0
        for msg in reversed(collected):
            try:
                await self.client.forward_messages(report_gid, msg)
                sent += 1
                await asyncio.sleep(0.35)
            except Exception:
                try:
                    if msg.media:
                        path = await self.client.download_media(msg, file=REPORT_MEDIA_FOLDER + '/')
                        if path:
                            await self.client.send_file(report_gid, path, caption=(msg.text or '')[:1000])
                            sent += 1
                    elif msg.text:
                        await self.client.send_message(report_gid, msg.text[:4000])
                        sent += 1
                except Exception:
                    pass
        await event.edit(f"✅ بکاپ تمام شد — {sent}/{len(collected)} به گروه گزارش ارسال شد")

    async def handle_outgoing_message(self, event):
        message_text = event.text or ""

        # جمع‌آوری متن منشی
        if getattr(self, 'monshi_step', None) in ('wait_text', 'collecting') and message_text:
            low = message_text.strip()
            if not (low.startswith('اتمام') or low.startswith('منشی')):
                if self.monshi_draft:
                    self.monshi_draft = self.monshi_draft + "\n" + message_text
                else:
                    self.monshi_draft = message_text
                self.monshi_step = 'collecting'
                try:
                    await event.edit(f"📝 متن ذخیره موقت شد ({len(self.monshi_draft)} کاراکتر)\nبرای پایان: `اتمام متن`")
                except Exception:
                    pass
                return

        # جمع‌آوری جواب یادگیری
        if getattr(self, 'learning_step', None) == 'wait_answer' and message_text:
            low = message_text.strip()
            if not low.startswith('یادگیری') and not low.startswith('اتمام'):
                q = self.learning_question or ''
                a = message_text.strip()
                db.add_answer(self.user_id, q, a)
                self.learning_step = None
                self.learning_question = None
                try:
                    await event.edit(f"✅ یادگیری ذخیره شد\n❓ {q}\n💬 {a}")
                except Exception:
                    pass
                return
        
        if self.adding_spam and message_text and not is_bot_command_text(message_text):
            db.add_enemy_spam_message(self.user_id, message_text)
            try:
                await event.delete()
            except:
                pass
            return
        
        if event.text:
            settings = db.get_selfbot_settings(self.user_id)
            text_style = settings.get('text_style')
            if text_style and not is_bot_command_text(message_text):
                try:
                    text, entities = await apply_text_style(message_text, text_style)
                    if entities:
                        await event.message.edit(text, formatting_entities=entities)
                except:
                    pass
        
        if self.search_mode and message_text and not is_bot_command_text(message_text):
            await self.handle_google_search(event, message_text)
            return
        
        if event.text and not is_bot_command_text(message_text):
            # ========== ترجمه ==========
            try:
                peer_uid = None
                try:
                    if isinstance(event.message.peer_id, PeerUser):
                        peer_uid = event.message.peer_id.user_id
                except Exception:
                    peer_uid = None
                translated_text = await self.translate_text(event.text, peer_user_id=peer_uid)
                if translated_text and translated_text.strip() != event.text.strip():
                    try:
                        await event.edit(translated_text)
                    except Exception as e:
                        logger.error(f"خطا در ادیت پیام ترجمه شده: {e}")
            except Exception as e:
                logger.error(f"خطا در فرآیند ترجمه: {e}")
    
    async def translate_text(self, text, peer_user_id=None):
        if not text or not str(text).strip():
            return text
        # اولویت: ترجمه مخصوص همان کاربر (پنل کاربر)
        modes = None
        if peer_user_id is not None:
            put = getattr(self, 'per_user_translate', {}) or {}
            modes = put.get(int(peer_user_id)) or put.get(str(peer_user_id))
            if modes and not any(modes.values()):
                modes = None
        if not modes:
            modes = getattr(self, 'translate_mode', None) or {}
        active = [lang for lang, st in (modes or {}).items() if st]
        if not active:
            return text
        try:
            from deep_translator import GoogleTranslator
        except Exception as e:
            logger.error(f"deep_translator missing: {e}")
            return text
        lang = active[0]
        target_code = TRANSLATE_LANG_CODES.get(lang, lang)
        # hebrew fix
        if target_code == 'iw':
            target_code = 'iw'
        try:
            # تکه کردن متن بلند (Google ~4500 char limit)
            raw = str(text)
            max_chunk = 4000
            chunks = []
            if len(raw) <= max_chunk:
                chunks = [raw]
            else:
                buf = raw
                while buf:
                    if len(buf) <= max_chunk:
                        chunks.append(buf)
                        break
                    cut = buf.rfind(' ', 0, max_chunk)
                    if cut < max_chunk // 2:
                        cut = max_chunk
                    chunks.append(buf[:cut])
                    buf = buf[cut:].lstrip()
            out_parts = []
            for ch in chunks:
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            GoogleTranslator(source='auto', target=target_code).translate, ch
                        ),
                        timeout=20
                    )
                    out_parts.append(result if result else ch)
                except Exception as e:
                    logger.error(f"translate chunk error: {e}")
                    out_parts.append(ch)
            return '\n'.join(out_parts) if out_parts else text
        except Exception as e:
            logger.error(f"translate_text: {e}")
            return text

    async def handle_google_search(self, event, query):
        try:
            await event.edit(f'🔍 در حال جستجو: {query}')
            params = {
                'key': GOOGLE_SEARCH_API_KEY,
                'cx': GOOGLE_CSE_ID,
                'q': query,
                'num': 5,
                'safe': 'active'
            }
            response = requests.get(GOOGLE_SEARCH_URL, params=params, timeout=10)
            if response.status_code == 200:
                results = response.json()
                if 'items' in results and len(results['items']) > 0:
                    self.last_search_results = results['items']
                    message = f"🔍 نتایج جستجو برای: {query}\n\n"
                    for i, item in enumerate(results['items'][:5], 1):
                        title = item.get('title', 'بدون عنوان')
                        link = item.get('link', '')
                        snippet = item.get('snippet', 'بدون توضیح')[:100]
                        message += f"{i}. {title}\n   {snippet}...\n   🔗 {link}\n\n"
                    if len(message) > 4000:
                        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
                        for i, chunk in enumerate(chunks):
                            if i == 0:
                                await event.edit(chunk)
                            else:
                                await event.respond(chunk)
                    else:
                        await event.edit(message)
                else:
                    await event.edit(f'❌ هیچ نتیجه‌ای برای "{query}" پیدا نشد.')
            else:
                await event.edit(f'❌ خطا در جستجو. کد خطا: {response.status_code}')
        except Exception as e:
            logger.error(f"خطا در جستجوی گوگل: {e}")
            await event.edit(f'❌ خطا در جستجو: {str(e)}')
    
    def get_media_type(self, message):
        if not hasattr(message, 'media') or not message.media:
            return None
        if isinstance(message.media, MessageMediaPhoto):
            return 'photo'
        elif isinstance(message.media, MessageMediaDocument):
            document = message.media.document
            if hasattr(document, 'attributes'):
                for attr in document.attributes:
                    if hasattr(attr, 'voice'):
                        return 'voice'
            if hasattr(document, 'mime_type'):
                if 'video' in document.mime_type:
                    for attr in document.attributes:
                        if hasattr(attr, 'voice'):
                            return 'video_note'
                    return 'video'
                elif 'image' in document.mime_type:
                    for attr in document.attributes:
                        if hasattr(attr, 'stickerset'):
                            return 'sticker'
                        elif hasattr(attr, 'animated'):
                            return 'gif'
                    return 'image'
                elif 'audio' in document.mime_type:
                    return 'music'
            if hasattr(document, 'attributes'):
                for attr in document.attributes:
                    if hasattr(attr, 'alt') and attr.alt:
                        return 'sticker'
            return 'file'
        elif isinstance(message.media, MessageMediaWebPage):
            return 'webpage'
        elif hasattr(message.media, 'contact'):
            return 'contact'
        elif hasattr(message.media, 'geo'):
            return 'location'
        return 'unknown'
    
    def get_file_extension(self, media_type):
        extensions = {
            'photo': '.jpg',
            'voice': '.ogg',
            'video': '.mp4',
            'video_note': '.mp4',
            'sticker': '.webp',
            'gif': '.mp4',
            'image': '.jpg',
            'file': '.bin',
            'music': '.mp3'
        }
        return extensions.get(media_type, '.bin')
    
    async def save_media(self, message, media_type):
        try:
            if not self.report_config.auto_save_media:
                return None
            chat_id = message.peer_id.user_id if isinstance(message.peer_id, PeerUser) else (
                message.peer_id.channel_id if isinstance(message.peer_id, PeerChannel) else message.peer_id.chat_id
            )
            timestamp = get_now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{media_type}_{message.sender_id}_{message.id}_{timestamp}"
            file_extension = self.get_file_extension(media_type)
            file_path = os.path.join(REPORT_MEDIA_FOLDER, file_name + file_extension)
            downloaded_path = await self.client.download_media(message.media, file=file_path)
            if downloaded_path and os.path.exists(downloaded_path):
                media_cache[message.id] = {
                    'path': downloaded_path,
                    'type': media_type,
                    'user_id': message.sender_id,
                    'chat_id': chat_id,
                    'caption': message.text or '',
                    'timestamp': timestamp,
                    'file_size': os.path.getsize(downloaded_path),
                    'owner_id': self.user_id
                }
                logger.info(f"رسانه ذخیره شد: {media_type} - {downloaded_path}")
                return downloaded_path
            return None
        except Exception as e:
            logger.error(f"خطا در ذخیره رسانه: {e}")
            return None
    
    async def send_report(self, report_text, media_path=None, caption=None, entities=None, mention_ids=None):
        """ارسال گزارش. mention_ids: لیست user_id برای تبدیل نام‌ها به منشن قابل‌کلیک."""
        try:
            if not self.report_config.report_group_id:
                return False
            body = caption or report_text
            ents = list(entities or [])
            # اگر mention_ids داده شده، اولین «از: NAME» یا کل نام‌های جدا را منشن کن
            if mention_ids and not ents:
                for uid in mention_ids:
                    try:
                        display, _ = await self.get_display_name(uid)
                        idx = body.find(display)
                        if idx >= 0:
                            off = self._utf16_len(body[:idx])
                            ents.append(self.make_mention_entity(display, uid, off))
                    except Exception:
                        pass
            if media_path and os.path.exists(media_path):
                await self.client.send_file(
                    self.report_config.report_group_id, media_path,
                    caption=body, formatting_entities=ents or None
                )
                logger.info(f"گزارش با فایل ارسال شد: {media_path}")
            else:
                await self.client.send_message(
                    self.report_config.report_group_id, report_text,
                    formatting_entities=ents or None
                )
                logger.info(f"گزارش متنی ارسال شد")
            return True
        except Exception as e:
            try:
                if media_path and os.path.exists(media_path):
                    await self.client.send_file(self.report_config.report_group_id, media_path, caption=caption or report_text)
                else:
                    await self.client.send_message(self.report_config.report_group_id, report_text)
                return True
            except Exception as e2:
                logger.error(f"خطا در ارسال گزارش: {e} / {e2}")
                return False
    
    async def get_chat_title(self, chat_id):
        try:
            entity = await self.client.get_entity(chat_id)
            return entity.title if hasattr(entity, 'title') else (entity.first_name or f"چت {chat_id}")
        except:
            return f"چت {chat_id}"

async def inline_panel(update:Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return
    user_id = query.from_user.id
    user_data = db.get_user(str(user_id))
    has_access = False
    if is_admin(user_id):
        has_access = True
    elif user_data:
        sa = user_data.get('self_active')
        # sqlite ممکن است 1 / "1" / True برگرداند
        if sa in (1, "1", True, "true", "True"):
            has_access = True
        elif user_data.get('admin_approved') in (1, "1", True) and user_data.get('session_file'):
            # بعد از بکاپ اگر سشن هست دسترسی بده
            sf = user_data.get('session_file')
            if sf and os.path.exists(sf):
                has_access = True
                # فعال‌سازی خودکار
                try:
                    db.update_user(str(user_id), self_active=1)
                except Exception:
                    pass
    if not has_access and str(user_id) in selfbot_managers and getattr(selfbot_managers[str(user_id)], 'running', False):
        has_access = True
    
    if not has_access:
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="⛔ دسترسی محدود",
                description="شما عضو سرویس نیستید",
                input_message_content=InputTextMessageContent("⛔ شما به این پنل دسترسی ندارید\n\nبرای عضویت: /start")
            )
        ]
        await query.answer(results, cache_time=0, is_personal=True)
        return
    
    qtext = (query.query or '').strip()
    # پنل کاربر: up_TARGETID
    if qtext.startswith('up_'):
        results = []
        try:
            tid = int(qtext.split('_', 1)[1])
            cache = user_panel_cache.get(str(user_id)) or {}
            name = cache.get('name') or f'User {tid}'
            caption = cache.get('caption') or f'👤 {name}\n🆔 {tid}'
            photo_path = cache.get('photo_path')
            keyboard = get_user_manage_keyboard(user_id, tid)
            file_id = None
            # اگر عکس از قبل ساخته شده، آپلود و file_id بگیر
            if photo_path and os.path.exists(photo_path):
                try:
                    with open(photo_path, 'rb') as f:
                        msg = await context.bot.send_photo(chat_id=ADMIN_ID, photo=f)
                    file_id = msg.photo[-1].file_id
                    try:
                        await context.bot.delete_message(chat_id=ADMIN_ID, message_id=msg.message_id)
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f'inline up upload: {e}')
            if not file_id:
                # ساخت تازه با آواتار از کش
                av = cache.get('avatar_path')
                photo_path2 = render_user_panel_image(name, av if av and os.path.exists(av) else None)
                if photo_path2 and os.path.exists(photo_path2):
                    try:
                        with open(photo_path2, 'rb') as f:
                            msg = await context.bot.send_photo(chat_id=ADMIN_ID, photo=f)
                        file_id = msg.photo[-1].file_id
                        try:
                            await context.bot.delete_message(chat_id=ADMIN_ID, message_id=msg.message_id)
                        except Exception:
                            pass
                    except Exception as e:
                        logger.warning(f'inline up render upload: {e}')
            if file_id:
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=str(uuid.uuid4()),
                        photo_file_id=file_id,
                        title=f'👤 پنل {name}',
                        description='مدیریت کاربر',
                        caption=caption,
                        reply_markup=keyboard
                    )
                )
            else:
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=f'👤 پنل {name}',
                        description='مدیریت کاربر',
                        input_message_content=InputTextMessageContent(caption),
                        reply_markup=keyboard
                    )
                )
        except Exception as e:
            logger.error(f'inline up_: {e}')
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title='❌ خطا',
                    description=str(e)[:80],
                    input_message_content=InputTextMessageContent(f'❌ خطا در پنل کاربر: {str(e)[:100]}')
                )
            )
        await query.answer(results, cache_time=0, is_personal=True)
        return

    if not query.query:
        name = get_main_panel_text(query.from_user)
        keyboard = get_main_panel_keyboard(user_id)
        results = []
        # یک پیام واحد: عکس + نام + دکمه‌ها (همیشه تازه — اسم/پروفیل به‌روز)
        file_id = await get_panel_photo_file_id(context.bot, query.from_user, force_refresh=True)
        if file_id:
            results.append(
                InlineQueryResultCachedPhoto(
                    id=str(uuid.uuid4()),
                    photo_file_id=file_id,
                    title="⬛ پنل",
                    description="عکس + دکمه‌ها",
                    caption=name,
                    reply_markup=keyboard
                )
            )
        else:
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="⬛ پنل کنترل",
                    description="پنل مدیریت",
                    input_message_content=InputTextMessageContent(name),
                    reply_markup=keyboard
                )
            )
        if is_admin(user_id):
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="👑 پنل ادمین",
                    description="مدیریت کاربران و سلف‌بات‌ها و ارسال پیام همگانی",
                    input_message_content=InputTextMessageContent("👑 پنل ادمین"),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 درخواست‌ها", callback_data=f"admin_requests"), InlineKeyboardButton("🔐 منتظر ورود", callback_data=f"admin_login")],
                        [InlineKeyboardButton("✅ کاربران فعال", callback_data=f"admin_active"), InlineKeyboardButton("🤖 سلف‌بات‌ها", callback_data=f"admin_selfbots")],
                        [InlineKeyboardButton("📊 آمار کلی", callback_data=f"admin_stats"), InlineKeyboardButton("📢 پیام همگانی", callback_data=f"admin_broadcast")],
                        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
                    ])
                )
            )
    else:
        search = query.query.lower()
        results = []
        all_commands = [
            ("⚈ زمان و پروفایل", "time", "مدیریت زمان و پروفایل + بیو"),
            ("☻ انیمیشن", "animation", "انیمیشن قلب و ماه و سنتت + استیکر متن"),
            ("☗ مدیریت کاربران", "user", "مدیریت دشمن/دوست/بلاک"),
            ("⊖ قفل رسانه", "lock", "قفل لینک/عکس/ویدیو/استیکر/ویس/فایل/موزیک/ویدیو نوت/کانتکت/لوکیشن/ایموجی/متن"),
            ("✼ کامنت", "comment", "کامنت خودکار در کانال"),
            ("✿ عمومی", "general", "وضعیت/درباره/پینگ"),
            ("☥ اکشن", "action", "اکشن‌های تایپ و ..."),
            ("⚕ بازی‌ها", "games", "بازی‌های تاس/دارت/بسکتبال/فوتبال/بولینگ/کازینو/سه رنگ"),
            ("❍ ترجمه", "translate", "ترجمه به زبان‌های مختلف"),
            ("𖢅 گوگل", "google", "جستجوی گوگل/اهنگ"),
            ("֍ اطلاعاتی", "info", "اطلاعات کاربر/سیستم/نشست‌ها/قیمت ارز/تاریخ ساخت اکانت/تشخیص متن"),
            ("𖢨 پروفایل", "profile", "کپی پروفایل و بیو"),
            ("⩐ استایل متن", "style", "بولد/زیرخط/خط خورده/نقل قول/اسپویلر/کج/کد/پیش"),
            ("𑪡 مدیریت پیام", "message", "حذف پیام و اتوسین + اسکرین‌شات"),
            ("☖ ریکشن", "reaction", "ریکت خودکار"),
            ("𖥞 اسپم", "spam", "ارسال اسپم"),
            ("☗ تغییر پروفایل", "change", "تغییر نام/بیو/پروفایل"),
            ("⚇ مدیریت دشمنان", "enemy", "لیست دشمن/اضافه اسپم"),
            ("✿ فیلتر کلمات", "filter", "فیلتر کلمات"),
            ("⚉ حفاظت اسپم", "protection", "محافظت در برابر اسپم"),
            ("☥ هوش مصنوعی", "ai", "مدیریت هوش مصنوعی"),
            ("֎ گزارش", "report", "تنظیم گروه گزارش"),
            ("🛠 ابزار", "tools", "امار گپ / کد QR / تگ ادمین / پین / سلف روشن/خاموش / ساخت استیکر"),
            ("🤖 منشی هوشمند", "monshi", "مدیریت منشی و پاسخ‌های خودکار"),
            ("🏷️ تگ همه", "mention", "تگ کردن همه اعضای گروه"),
            ("🔮 فال", "fortune", "فال عمومی / فال حافظ / فال قهوه")
        ]
        for title, cmd, desc in all_commands:
            if search in title.lower() or search in desc.lower() or search in cmd.lower():
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=title,
                        description=desc,
                        input_message_content=InputTextMessageContent(f"✅ دستور {title} ارسال شد"),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(f"ℹ️ توضیحات", callback_data=f"desc_{cmd}", style="primary"),
                            InlineKeyboardButton(f"▶️ باز کردن", callback_data=f"menu_{cmd}", style="success")
                        ]])
                    )
                )
    await query.answer(results, cache_time=0, is_personal=True)




def _load_panel_base_image():
    """بارگذاری قالب پنل (از فایل یا base64 embed)"""
    from PIL import Image
    ensured = ensure_panel_header_files()
    candidates = [
        ensured,
        PANEL_HEADER_IMAGE,
        "panel_header.png",
        "panel_header_base.png",
        "user_panel_header.png",
        "/app/panel_header.png",
        "/app/panel_header_base.png",
        "/app/user_panel_header.png",
        os.path.join("media_storage", "panel_header.png"),
        os.path.join("media_storage", "panel_header_base.png"),
        os.path.join("media_storage", "user_panel_header.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header_base.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_panel_header.png"),
    ]
    for pth in candidates:
        try:
            if pth and os.path.exists(pth) and os.path.getsize(pth) > 1000:
                return Image.open(pth).convert('RGBA'), pth
        except Exception:
            continue
    logger.error("هیچ تصویر پنل یافت نشد!")
    return None, None



def clean_display_name(name: str) -> str:
    """اسم واقعی کاربر برای بنر — فقط ساعت/پرچم حذف؛ حروف فانتزی به لاتین خوانا."""
    if not name:
        return "User"
    import re, unicodedata
    s = str(name).strip()
    try:
        s = unicodedata.normalize('NFKC', s)
    except Exception:
        pass
    LOOK = {
        'ᣵ':'v','ᑋ':'h','ᣔ':'d','ᣕ':'k','ᐪ':'k','ᐱ':'p','ᐯ':'v','ᑕ':'d','ᑌ':'u',
        'ᑎ':'n','ᑭ':'k','ᒪ':'l','ᒥ':'m','ᓂ':'n','ᓄ':'o','ᓭ':'s','ᔕ':'s','ᕼ':'h',
        'ᖇ':'r','ᖴ':'f','ᗩ':'a','ᗷ':'b','ᗪ':'d','ᕮ':'e','ᘜ':'g','Ꭵ':'i','ᒎ':'j',
        'Ꮶ':'k','ᗰ':'m','ᝪ':'o','ᑭ':'p','ᑫ':'q','Ꭲ':'t','ᗯ':'w','᙭':'x','ᖻ':'y','Ꮓ':'z',
        'ɨ':'i','ɪ':'i','ɩ':'i','ι':'i','і':'i','ı':'i','ɑ':'a','а':'a','α':'a',
        'ʙ':'b','в':'b','ϲ':'c','с':'c','ԁ':'d','е':'e','ε':'e','ғ':'f','ɢ':'g',
        'һ':'h','н':'h','ј':'j','κ':'k','к':'k','ʟ':'l','м':'m','ո':'n','ο':'o',
        'о':'o','օ':'o','ρ':'p','р':'p','ʀ':'r','г':'r','ѕ':'s','τ':'t','т':'t',
        'υ':'u','ν':'v','ѵ':'v','ω':'w','χ':'x','х':'x','у':'y','ү':'y',
        'ᴀ':'a','ʙ':'b','ᴄ':'c','ᴅ':'d','ᴇ':'e','ɢ':'g','ʜ':'h','ɪ':'i','ᴊ':'j',
        'ᴋ':'k','ʟ':'l','ᴍ':'m','ɴ':'n','ᴏ':'o','ᴘ':'p','ǫ':'q','ʀ':'r','ᴛ':'t',
        'ᴜ':'u','ᴠ':'v','ᴡ':'w','ʏ':'y','ᴢ':'z',
    }
    def mapc(ch):
        if ch in LOOK:
            return LOOK[ch]
        o = ord(ch)
        for base in (0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC, 0x1D7F6):
            if base <= o <= base + 9:
                return chr(ord('0') + (o - base))
        ranges = [
            (0x1D400, 0x1D419, 'A'), (0x1D41A, 0x1D433, 'a'),
            (0x1D434, 0x1D44D, 'A'), (0x1D44E, 0x1D467, 'a'),
            (0x1D468, 0x1D481, 'A'), (0x1D482, 0x1D49B, 'a'),
            (0x1D5A0, 0x1D5B9, 'A'), (0x1D5BA, 0x1D5D3, 'a'),
            (0x1D5D4, 0x1D5ED, 'A'), (0x1D5EE, 0x1D607, 'a'),
            (0x1D670, 0x1D689, 'A'), (0x1D68A, 0x1D6A3, 'a'),
            (0x1D538, 0x1D550, 'A'), (0x1D552, 0x1D56B, 'a'),
        ]
        for a, b, base in ranges:
            if a <= o <= b:
                return chr(ord(base) + (o - a))
        if 0xFF21 <= o <= 0xFF3A:
            return chr(ord('A') + (o - 0xFF21))
        if 0xFF41 <= o <= 0xFF5A:
            return chr(ord('a') + (o - 0xFF41))
        if ch.isascii() or ('\u0600' <= ch <= '\u06FF') or ch.isspace() or ch.isdigit():
            return ch
        cat = unicodedata.category(ch)
        if cat.startswith('L') or cat.startswith('N'):
            try:
                un = unicodedata.name(ch, '')
                for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    if f' LETTER {letter}' in un:
                        return letter.lower() if 'SMALL' in un else letter
            except Exception:
                pass
            return ''
        if cat in ('So', 'Sk') and o > 0x1F000:
            return ch
        return ''
    s = ''.join(mapc(c) for c in s)
    s = re.sub(r'[\U0001F1E0-\U0001F1FF]+', ' ', s)
    s = re.sub(r'[|｜]?\s*[0-9۰-۹]{1,2}\s*[:：٫.]\s*[0-9۰-۹]{1,2}', ' ', s)
    for ch in ('_', '*', '`', '[', ']', '\n', '\r', '|', '｜', '@', '『', '』'):
        s = s.replace(ch, ' ')
    s = ' '.join(s.split())
    return s or "User"


def _composite_panel(username: str, avatar_path: str = None) -> str:
    """
    قالب تمیز VROOM:
    - عکس داخل دایره سیاه (کمی پایین‌تر برای مرکز دقیق)
    - اسم خیلی بزرگ وسط بنر فلزی پایین
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
        img, base_path = _load_panel_base_image()
        if img is None:
            return None
        W, H = img.size

        # مرکز دایره — کمی پایین‌تر تا دقیق داخل دایره سیاه
        cx = int(round(W * 0.6146))
        cy = int(round(H * 0.5050))
        radius = int(round(min(W, H) * 0.242))
        size = radius * 2

        if avatar_path and os.path.exists(avatar_path):
            try:
                avatar = Image.open(avatar_path).convert('RGBA')
                try:
                    avatar = ImageOps.fit(
                        avatar, (size, size),
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5)
                    )
                except Exception:
                    avatar = ImageOps.fit(avatar, (size, size), centering=(0.5, 0.5))
                mask = Image.new('L', (size, size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
                try:
                    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.6))
                except Exception:
                    pass
                avatar.putalpha(mask)
                img.paste(avatar, (cx - radius, cy - radius), avatar)
            except Exception as e:
                logger.debug(f"avatar composite: {e}")

        # اسم خالص کاربر (فونت فانتزی → لاتین خوانا)
        raw_name = clean_display_name(username or "User")
        if len(raw_name) > 28:
            parts = raw_name.split()
            if len(parts) >= 2:
                safe_name = (parts[0][:14] + ' ' + parts[-1][:12]).strip()
            else:
                safe_name = raw_name[:26] + '…'
        else:
            safe_name = raw_name

        # بنر فلزی پایین — اسم خیلی بزرگ‌تر و پرکننده بنر
        plate_cx = int(W * 0.613)
        plate_cy = int(H * 0.850)
        plate_w = int(W * 0.72)
        plate_h = int(H * 0.30)

        max_text_w = int(plate_w * 0.99)
        max_text_h = int(plate_h * 1.10)

        draw = ImageDraw.Draw(img, 'RGBA')
        font_candidates = [
            "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
        ]
        # رندر روی لایه بزرگ سپس اسکیل به اندازه بنر → حتی با فونت ضعیف هم خوانا می‌ماند
        layer_w, layer_h = 1600, 320
        layer = Image.new('RGBA', (layer_w, layer_h), (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(layer, 'RGBA')
        font = None
        tw = th = 0
        chosen_fs = 40
        for fs in range(420, 48, -2):
            f = None
            for fpath in font_candidates:
                try:
                    f = ImageFont.truetype(fpath, fs)
                    break
                except Exception:
                    continue
            if f is None:
                try:
                    f = ImageFont.load_default()
                except Exception:
                    continue
            try:
                bbox = ldraw.textbbox((0, 0), safe_name, font=f)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = len(safe_name) * fs // 2, fs
            if tw <= layer_w * 0.92 and th <= layer_h * 0.85:
                font = f
                chosen_fs = fs
                break
        if font is None:
            font = ImageFont.load_default()
            try:
                bbox = ldraw.textbbox((0, 0), safe_name, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = 200, 40
        pad = 24
        tx = (layer_w - tw) // 2
        ty = (layer_h - th) // 2
        for ox, oy, col in (
            (8, 8, (0, 4, 10, 210)),
            (5, 5, (10, 40, 90, 170)),
            (3, 3, (40, 120, 220, 130)),
            (0, -2, (140, 220, 255, 80)),
        ):
            ldraw.text((tx + ox, ty + oy), safe_name, font=font, fill=col)
        ldraw.text((tx, ty), safe_name, font=font, fill=(210, 252, 255, 255))
        # فقط ناحیه متن را برش بزن و تا حد بنر بزرگ کن
        crop_box = (
            max(0, tx - pad),
            max(0, ty - pad),
            min(layer_w, tx + tw + pad),
            min(layer_h, ty + th + pad),
        )
        cropped = layer.crop(crop_box)
        cw, ch = cropped.size
        # پر کردن کامل عرض/ارتفاع بنر و مرکز دقیق
        scale = min(max_text_w / max(cw, 1), max_text_h / max(ch, 1))
        scale = max(1.0, scale)  # حداقل ۱× لایه؛ معمولاً بزرگ‌تر می‌شود تا بنر پر شود
        new_w = max(1, min(int(cw * scale), max_text_w, W - 4))
        new_h = max(1, min(int(ch * scale), max_text_h, H - 4))
        try:
            cropped = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
        except Exception:
            cropped = cropped.resize((new_w, new_h), Image.LANCZOS)
        paste_x = max(0, min(plate_cx - new_w // 2, W - new_w))
        paste_y = max(0, min(plate_cy - new_h // 2 - 2, H - new_h))  # کمی بالاتر برای وسط بنر
        img.paste(cropped, (paste_x, paste_y), cropped)

        os.makedirs(MEDIA_FOLDER, exist_ok=True)
        out = os.path.join(
            MEDIA_FOLDER,
            f"panel_{abs(hash(safe_name + str(avatar_path or '') + str(W) + 'v25')) % 10**9}.jpg"
        )
        img.convert('RGB').save(out, 'JPEG', quality=95)
        return out
    except Exception as e:
        logger.error(f"_composite_panel: {e}\n{traceback.format_exc()}")
        return None


def render_panel_image(username: str, avatar_path: str = None) -> str:
    """هدر پنل اصلی: آواتار کاربر در دایره + نام پایین"""
    return _composite_panel(username, avatar_path)


def render_user_panel_image(username: str, avatar_path: str = None) -> str:
    """تصویر پنل کاربر: همان قالب + آواتار همان کاربر + نام"""
    return _composite_panel(username, avatar_path)


async def get_panel_photo_file_id(bot, user, force_refresh=False):
    """ساخت تصویر پنل با آواتار کاربر و آپلود برای گرفتن file_id (اینلاین یک‌پیامه)"""
    user_id = user.id
    # همیشه تازه بساز تا اگر اسم/پروفیل عوض شد به‌روز باشد
    if not force_refresh and user_id in panel_photo_cache and False:
        return panel_photo_cache[user_id]
    # اسم خالص از دیتابیس (بدون تایم) — وگرنه first_name پاک‌سازی‌شده
    name = None
    try:
        name = db.get_current_name(str(user_id)) or db.get_original_name(str(user_id))
    except Exception:
        name = None
    if not name:
        name = getattr(user, 'full_name', None) or getattr(user, 'first_name', None) or "User"
    name = clean_display_name(name)
    avatar_path = None
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0:
            pf = await bot.get_file(photos.photos[0][-1].file_id)
            avatar_path = os.path.join(MEDIA_FOLDER, f"pf_{user_id}.jpg")
            os.makedirs(MEDIA_FOLDER, exist_ok=True)
            await pf.download_to_drive(avatar_path)
    except Exception as e:
        logger.debug(f"avatar for panel: {e}")
    photo_path = render_panel_image(name, avatar_path)
    if avatar_path:
        try:
            os.remove(avatar_path)
        except Exception:
            pass
    if not photo_path or not os.path.exists(photo_path):
        return None
    try:
        # آپلود به چت ادمین برای گرفتن file_id پایدار
        with open(photo_path, 'rb') as f:
            msg = await bot.send_photo(chat_id=ADMIN_ID, photo=f)
        file_id = msg.photo[-1].file_id
        panel_photo_cache[user_id] = file_id
        try:
            await bot.delete_message(chat_id=ADMIN_ID, message_id=msg.message_id)
        except Exception:
            pass
        return file_id
    except Exception as e:
        logger.error(f"upload panel photo: {e}")
        return None

def get_main_panel_text(user):
    """فقط نام خالص کاربر (بدون تایم) — بدون متن اضافه بین عکس و دکمه‌ها"""
    try:
        uid = getattr(user, 'id', None)
        name = None
        if uid is not None:
            try:
                name = db.get_current_name(str(uid)) or db.get_original_name(str(uid))
            except Exception:
                name = None
        if not name:
            name = getattr(user, 'full_name', None) or getattr(user, 'first_name', None) or "User"
        return clean_display_name(name)
    except Exception:
        return "User"

def get_help_back_keyboard(user_id, back_callback):
    """دکمه بازگشت برای صفحات راهنما"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data=back_callback, style="danger")]
    ])

async def safe_edit_panel(query, text, reply_markup=None, parse_mode=None):
    """ویرایش پیام پنل — هم متن هم کپشن عکس؛ در صورت شکست پیام جدید می‌فرستد"""
    kwargs = {}
    if reply_markup is not None:
        kwargs['reply_markup'] = reply_markup
    if parse_mode:
        kwargs['parse_mode'] = parse_mode
    try:
        await query.answer()
    except Exception:
        pass
    has_photo = False
    try:
        has_photo = bool(query.message and query.message.photo)
    except Exception:
        pass
    if has_photo:
        try:
            await query.edit_message_caption(caption=(text or " ")[:1024], **kwargs)
            return True
        except Exception as e:
            logger.debug(f"edit_caption: {e}")
            if reply_markup is not None:
                try:
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
                    # اگر متن هم مهم است، پیام جدا بفرست
                    if text and len(str(text)) > 2:
                        try:
                            chat_id = query.message.chat_id
                            await query.get_bot().send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
                        except Exception:
                            pass
                    return True
                except Exception as e2:
                    logger.debug(f"edit_markup after caption fail: {e2}")
    try:
        await query.edit_message_text(text, **kwargs)
        return True
    except Exception as e1:
        try:
            if reply_markup is not None:
                await query.edit_message_reply_markup(reply_markup=reply_markup)
                return True
        except Exception as e2:
            logger.debug(f"safe_edit_panel: {e1} | {e2}")
        # آخرین راه: پیام جدید
        try:
            chat_id = query.message.chat_id if query.message else query.from_user.id
            await query.get_bot().send_message(
                chat_id=chat_id,
                text=text or "پنل",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
        except Exception as e3:
            logger.debug(f"safe_edit send fallback: {e3}")
    return False

async def refresh_panel_keyboard(query, user_id, menu_text, keyboard_func):
    """به‌روزرسانی فوری کیبورد پنل با تیک‌های جدید"""
    kb = keyboard_func(user_id)
    ok = await safe_edit_panel(query, menu_text, reply_markup=kb)
    if not ok and kb is not None:
        try:
            await query.edit_message_reply_markup(reply_markup=kb)
        except Exception:
            pass

def get_main_panel_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("⏰ زمان و پروفایل", callback_data=f"time_menu_{user_id}", style="primary"),
            InlineKeyboardButton("✨ انیمیشن", callback_data=f"animation_menu_{user_id}", style="primary"),
            InlineKeyboardButton("👤 کاربران", callback_data=f"user_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🔒 قفل رسانه", callback_data=f"lock_menu_{user_id}", style="danger"),
            InlineKeyboardButton("💬 کامنت", callback_data=f"comment_menu_{user_id}", style="success"),
            InlineKeyboardButton("📌 عمومی", callback_data=f"general_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎭 اکشن", callback_data=f"action_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🎮 بازی‌ها", callback_data=f"games_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🌐 ترجمه", callback_data=f"translate_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🔎 گوگل", callback_data=f"google_menu_{user_id}", style="primary"),
            InlineKeyboardButton("ℹ️ اطلاعاتی", callback_data=f"info_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🖼 پروفایل", callback_data=f"profile_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("✍️ استایل متن", callback_data=f"style_menu_{user_id}", style="primary"),
            InlineKeyboardButton("📨 مدیریت پیام", callback_data=f"message_menu_{user_id}", style="primary"),
            InlineKeyboardButton("👍 ریکشن", callback_data=f"reaction_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("💣 اسپم", callback_data=f"spam_menu_{user_id}", style="danger"),
            InlineKeyboardButton("✏️ تغییر پروفایل", callback_data=f"change_menu_{user_id}", style="primary"),
            InlineKeyboardButton("👹 دشمنان", callback_data=f"enemy_menu_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🚫 فیلتر کلمات", callback_data=f"exec_open_filter_{user_id}", style="primary"),
            InlineKeyboardButton("🛡 حفاظت اسپم", callback_data=f"protection_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🤖 هوش مصنوعی", callback_data=f"ai_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📣 گزارش", callback_data=f"report_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🛠 ابزار", callback_data=f"tools_menu_{user_id}", style="primary"),
            InlineKeyboardButton("💰 ارزها", callback_data=f"crypto_menu_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🗣 منشی هوشمند", callback_data=f"monshi_menu_{user_id}", style="success"),
            InlineKeyboardButton("📢 تگ همه", callback_data=f"mention_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🔮 فال", callback_data=f"fortune_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📦 بکاپ‌گیری", callback_data=f"backup_menu_{user_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("✖️ بستن پنل", callback_data=f"close_panel_{user_id}", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_fortune_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("🌟 فال عمومی", callback_data=f"exec_fortune_general_{user_id}", style="primary")],
        [InlineKeyboardButton("🕌 فال حافظ", callback_data=f"exec_fortune_hafez_{user_id}", style="primary")],
        [InlineKeyboardButton("☕ فال قهوه", callback_data=f"exec_fortune_coffee_{user_id}", style="primary")],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_fortune_help_{user_id}", style="primary")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_time_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    time_enabled = settings.get('time_enabled', False)
    flag_enabled = settings.get('flag_enabled', False)
    clock_on = bool(settings.get('profile_clock_enabled'))
    clock_color = settings.get('profile_clock_color') or 'cyan'
    keyboard = [
        [
            InlineKeyboardButton(f"🕐 تایم {'✓ روشن' if time_enabled else 'خاموش'}", callback_data=f"exec_time_on_{user_id}" if not time_enabled else f"exec_time_off_{user_id}", style="success" if time_enabled else "primary"),
            InlineKeyboardButton(f"🏳️ پرچم {'✓ روشن' if flag_enabled else 'خاموش'}", callback_data=f"exec_time_flag_{user_id}", style="success" if flag_enabled else "primary")
        ],
        [
            InlineKeyboardButton(f"🕰 ساعت در پروفایل {'✓ روشن' if clock_on else 'خاموش'}", callback_data=f"exec_open_pclock_{user_id}", style="success" if clock_on else "primary"),
        ],
        [
            InlineKeyboardButton("📅 تقویم", callback_data=f"exec_calendar_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🔤 انتخاب فونت تایم", callback_data=f"font_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🏳️ انتخاب پرچم", callback_data=f"flag_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📝 تنظیمات بیو", callback_data=f"bio_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_time_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_profile_clock_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    clock_on = bool(settings.get('profile_clock_enabled'))
    color = (settings.get('profile_clock_color') or 'cyan').lower()
    colors = [
        ("cyan", "🩵 فیروزه‌ای"),
        ("green", "💚 سبز"),
        ("purple", "💜 بنفش"),
        ("pink", "💗 صورتی"),
        ("orange", "🧡 نارنجی"),
        ("red", "❤️ قرمز"),
        ("blue", "💙 آبی"),
        ("white", "🤍 سفید"),
    ]
    keyboard = [
        [
            InlineKeyboardButton(f"{'✓ ' if clock_on else ''}🕰 روشن", callback_data=f"exec_pclock_on_{user_id}", style="success" if clock_on else "primary"),
            InlineKeyboardButton(f"{'✓ ' if not clock_on else ''}🕰 خاموش", callback_data=f"exec_pclock_off_{user_id}", style="danger" if not clock_on else "primary"),
        ],
        [InlineKeyboardButton("🎨 رنگ ساعت:", callback_data=f"exec_pclock_noop_{user_id}", style="primary")],
    ]
    row = []
    for key, label in colors:
        mark = "✓ " if color == key else ""
        row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"exec_pclock_color_{key}_{user_id}", style="success" if color == key else "primary"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔄 بروزرسانی الان", callback_data=f"exec_pclock_refresh_{user_id}", style="primary")])
    keyboard.append([InlineKeyboardButton("📖 راهنما", callback_data=f"exec_pclock_help_{user_id}", style="primary")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")])
    return InlineKeyboardMarkup(keyboard)

def get_font_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    selected = settings.get('time_font_indices', 'all')
    if selected == 'all' or selected is None:
        selected_set = set()
        all_selected = True
    else:
        try:
            selected_set = set(int(x) for x in (selected if isinstance(selected, list) else []))
        except Exception:
            selected_set = set()
        all_selected = False
    keyboard = []
    # All fonts button
    keyboard.append([
        InlineKeyboardButton(
            f"{'✓ ' if all_selected else ''}همه فونت‌ها (چرخش خودکار)",
            callback_data=f"exec_font_all_{user_id}",
            style="success" if all_selected else "primary"
        )
    ])
    row = []
    for i, font in enumerate(classic_fonts):
        sample = ''.join(font[int(c)] if c.isdigit() else c for c in "123")
        label = f"{'✓ ' if (not all_selected and i in selected_set) else ''}{i}: {sample}"
        row.append(InlineKeyboardButton(label, callback_data=f"exec_font_sel_{i}_{user_id}", style="success" if (not all_selected and i in selected_set) else "primary"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🧹 پاک کردن انتخاب", callback_data=f"exec_font_clear_{user_id}", style="danger")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")])
    return InlineKeyboardMarkup(keyboard)

def get_flag_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    selected = settings.get('selected_flags', 'all')
    if selected == 'all':
        selected_set = set()
        all_selected = True
    else:
        selected_set = set(selected) if isinstance(selected, list) else set()
        all_selected = False
    keyboard = []
    keyboard.append([
        InlineKeyboardButton(
            f"{'✓ ' if all_selected else ''}همه پرچم‌ها (چرخش خودکار)",
            callback_data=f"exec_flag_all_{user_id}",
            style="success" if all_selected else "primary"
        )
    ])
    row = []
    for i, fl in enumerate(flags):
        label = f"{'✓ ' if (not all_selected and fl in selected_set) else ''}{fl}"
        row.append(InlineKeyboardButton(label, callback_data=f"exec_flag_sel_{i}_{user_id}", style="success" if (not all_selected and fl in selected_set) else "primary"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🧹 پاک کردن انتخاب", callback_data=f"exec_flag_clear_{user_id}", style="danger")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")])
    return InlineKeyboardMarkup(keyboard)

def get_bio_menu_keyboard(user_id):
    def _on(name):
        return db.get_bio_setting(user_id, name) == 'روشن'
    def _btn(label, key, on):
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{label}",
            callback_data=f"exec_{key}_{user_id}",
            style="success" if on else "primary"
        )
    keyboard = [
        [
            _btn("🕐 ساعت در بیو", "bio_time1", _on('ساعت_در_بیو')),
            _btn("🕐 ساعت در بیو ۲", "bio_time2", _on('ساعت_در_بیو_۲')),
        ],
        [
            _btn("📅 بیو تاریخ", "bio_date", _on('بیو_تاریخ')),
            _btn("📅 بیو کامل", "bio_full", _on('بیو_کامل')),
        ],
        [
            _btn("💕 بیو عاشقانه", "bio_love", _on('بیو_عاشقانه')),
            _btn("🎨 بیو ایموجی", "bio_emoji", _on('بیو_ایموجی')),
        ],
        [
            _btn("🌸 بیو فصل", "bio_season", _on('بیو_فصل')),
            _btn("📆 بیو روز هفته", "bio_weekday", _on('بیو_روز_هفته')),
        ],
        [
            _btn("⏳ شمارش معکوس", "bio_countdown", _on('بیو_شمارش_معکوس')),
            _btn("✏️ متن دلخواه", "bio_custom", _on('بیو_متن_دلخواه')),
        ],
        [
            InlineKeyboardButton("📖 راهنما بیو", callback_data=f"exec_bio_help_{user_id}", style="primary"),
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_animation_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("❤️ قلب", callback_data=f"exec_heart_{user_id}", style="primary"),
            InlineKeyboardButton("🌙 ماه", callback_data=f"exec_moon_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("💖 قلب پیشرفته", callback_data=f"exec_advanced_heart_{user_id}", style="primary"),
            InlineKeyboardButton("💝 عشق", callback_data=f"exec_love_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🕯️ سنتت", callback_data=f"exec_santet_{user_id}", style="primary"),
            InlineKeyboardButton("💻 هک", callback_data=f"exec_hack_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🎨 استیکر متن", callback_data=f"exec_sticker_text_{user_id}", style="success")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_animation_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🎲 تاس ۱", callback_data=f"exec_dice_1_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۲", callback_data=f"exec_dice_2_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۳", callback_data=f"exec_dice_3_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎲 تاس ۴", callback_data=f"exec_dice_4_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۵", callback_data=f"exec_dice_5_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۶", callback_data=f"exec_dice_6_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎯 دارت", callback_data=f"exec_dart_{user_id}", style="primary"),
            InlineKeyboardButton("🏀 بسکتبال", callback_data=f"exec_basketball_{user_id}", style="primary"),
            InlineKeyboardButton("⚽️ فوتبال", callback_data=f"exec_football_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎳 بولینگ", callback_data=f"exec_bowling_{user_id}", style="success"),
            InlineKeyboardButton("🎲 تاس کازینو", callback_data=f"exec_casino_dice_{user_id}", style="danger"),
            InlineKeyboardButton("🎨 سه رنگ", callback_data=f"exec_three_colors_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_games_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_info_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📋 اطلاعات", callback_data=f"exec_info_{user_id}", style="primary"),
            InlineKeyboardButton("⬇️ دانلود پروفایل", callback_data=f"exec_download_profile_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📅 تاریخ ساخت اکانت", callback_data=f"exec_account_age_{user_id}", style="primary"),
            InlineKeyboardButton("📱 نشست‌های فعال", callback_data=f"exec_active_sessions_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🖥️ اطلاعات سیستم", callback_data=f"exec_system_info_{user_id}", style="primary"),
            InlineKeyboardButton("🔍 تشخیص متن", callback_data=f"exec_ocr_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_info_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_message_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    auto_on = bool(settings.get('auto_seen', settings.get('autosend', 0)))
    keyboard = [
        [
            InlineKeyboardButton("🧹 حذف کامل", callback_data=f"exec_delete_all_{user_id}", style="danger"),
            InlineKeyboardButton("🧹 حذف کامل ۵۰", callback_data=f"exec_delete_50_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🗑️ حذف ۱۰", callback_data=f"exec_delete_10_{user_id}", style="danger"),
            InlineKeyboardButton(f"{'✓ ' if auto_on else ''}👁️ فعال اتوسین", callback_data=f"exec_autosend_on_{user_id}", style="success" if auto_on else "primary")
        ],
        [
            InlineKeyboardButton(f"{'✓ ' if not auto_on else ''}🙈 غیرفعال اتوسین", callback_data=f"exec_autosend_off_{user_id}", style="danger" if not auto_on else "primary")
        ],
        [
            InlineKeyboardButton("📸 اسکرین‌شات", callback_data=f"exec_screenshot_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_message_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tools_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    self_on = bool(settings.get('selfbot_enabled', 1))
    keyboard = [
        [
            InlineKeyboardButton("📊 امار گپ", callback_data=f"exec_stats_{user_id}", style="primary"),
            InlineKeyboardButton("🝰 کد QR", callback_data=f"exec_qr_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("👑 تگ ادمین", callback_data=f"exec_tag_admin_{user_id}", style="primary"),
            InlineKeyboardButton("📌 پین", callback_data=f"exec_pin_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton(f"{'✓ ' if self_on else ''}🤖 سلف روشن", callback_data=f"exec_self_on_{user_id}", style="success" if self_on else "primary"),
            InlineKeyboardButton(f"{'✓ ' if not self_on else ''}⛔ سلف خاموش", callback_data=f"exec_self_off_{user_id}", style="danger" if not self_on else "primary")
        ],
        [
            InlineKeyboardButton("🎨 ساخت استیکر", callback_data=f"exec_make_sticker_{user_id}", style="success"),
            InlineKeyboardButton("🔢 ایدی عددی", callback_data=f"exec_numeric_id_help_{user_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("🎙 ویدیو → ویس", callback_data=f"exec_video_to_voice_{user_id}", style="success"),
        ],
        [
            InlineKeyboardButton(f"{'✓ ' if db.get_learning_enabled(user_id) else ''}🧠 یادگیری روشن", callback_data=f"exec_learning_on_{user_id}", style="success" if db.get_learning_enabled(user_id) else "primary"),
            InlineKeyboardButton(f"{'✓ ' if not db.get_learning_enabled(user_id) else ''}🧠 یادگیری خاموش", callback_data=f"exec_learning_off_{user_id}", style="danger" if not db.get_learning_enabled(user_id) else "primary"),
        ],
        [
            InlineKeyboardButton("📋 لیست یادگیری", callback_data=f"exec_learning_list_{user_id}", style="primary"),
            InlineKeyboardButton("📖 راهنما یادگیری", callback_data=f"exec_learning_help_{user_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("🗑 ریست دیتابیس", callback_data=f"exec_reset_db_{user_id}", style="danger"),
            InlineKeyboardButton("📖 راهنما ابزار", callback_data=f"exec_tools_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_backup_menu_keyboard(user_id):
    on = db.get_backup_enabled(user_id)
    keyboard = [
        [
            InlineKeyboardButton(f"{'✓ ' if on else ''}📦 بکاپ روشن", callback_data=f"exec_backup_on_{user_id}", style="success" if on else "primary"),
            InlineKeyboardButton(f"{'✓ ' if not on else ''}⛔ بکاپ خاموش", callback_data=f"exec_backup_off_{user_id}", style="danger" if not on else "primary"),
        ],
        [
            InlineKeyboardButton("📖 راهنما بکاپ", callback_data=f"exec_backup_help_{user_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_monshi_menu_keyboard(user_id):
    monshi_data = db.get_monshi_status(user_id)
    status = monshi_data['status']
    keyboard = [
        [
            InlineKeyboardButton(f"{'✓ ' if status else ''}🤖 منشی روشن", callback_data=f"exec_monshi_on_{user_id}", style="success" if status else "primary"),
            InlineKeyboardButton(f"{'✓ ' if not status else ''}⛔ منشی خاموش", callback_data=f"exec_monshi_off_{user_id}", style="danger" if not status else "primary")
        ],
        [
            InlineKeyboardButton("📝 افزودن پاسخ", callback_data=f"exec_add_answer_{user_id}", style="success"),
            InlineKeyboardButton("🗑️ حذف پاسخ", callback_data=f"exec_remove_answer_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📋 لیست پاسخ‌ها", callback_data=f"exec_list_answers_{user_id}", style="primary"),
            InlineKeyboardButton("🧹 پاک کردن پاسخ‌ها", callback_data=f"exec_clear_answers_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_monshi_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_mention_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🏷️ تگ همه [متن]", callback_data=f"exec_mention_all_{user_id}", style="primary"),
            InlineKeyboardButton("⛔ لغو تگ", callback_data=f"exec_cancel_mention_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_mention_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🥷 دشمن", callback_data=f"exec_enemy_{user_id}", style="danger"),
            InlineKeyboardButton("🧸 دوست", callback_data=f"exec_friend_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("👥 دشمن گروه", callback_data=f"exec_enemy_group_{user_id}", style="danger"),
            InlineKeyboardButton("🤝 دوست گروه", callback_data=f"exec_friend_group_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🔒 قفل پیوی", callback_data=f"exec_lock_pv_{user_id}", style="danger"),
            InlineKeyboardButton("🔓 باز پی", callback_data=f"exec_unlock_pv_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🔒 قفل پیوی همه", callback_data=f"exec_lock_all_{user_id}", style="danger"),
            InlineKeyboardButton("🔓 باز پی همه", callback_data=f"exec_unlock_all_{user_id}", style="success"),
            InlineKeyboardButton("⛔ بلاک", callback_data=f"exec_block_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_user_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# target_id برای قفل رسانه از پنل کاربر (user_id -> target_id)
panel_lock_targets = {}

def get_lock_menu_keyboard(user_id, target_id=None):
    if target_id is None:
        target_id = panel_lock_targets.get(user_id, 0)
    def _lk(lock_type, label):
        on = db.get_user_lock(user_id, target_id, lock_type)
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{label}",
            callback_data=f"exec_{lock_type}_{user_id}",
            style="success" if on else "danger"
        )
    keyboard = [
        [
            _lk("lock_link", "🔗 لینک"),
            _lk("lock_photo", "📸 عکس"),
            _lk("lock_video", "🎥 ویدیو"),
        ],
        [
            _lk("lock_sticker", "🎨 استیکر"),
            _lk("lock_gif", "🎞️ گیف"),
            _lk("lock_voice", "🎤 ویس"),
        ],
        [
            _lk("lock_file", "📁 فایل"),
            _lk("lock_music", "🎵 موزیک"),
            _lk("lock_video_note", "📹 ویدیو نوت"),
        ],
        [
            _lk("lock_contact", "📞 کانتکت"),
            _lk("lock_location", "📍 لوکیشن"),
            _lk("lock_emoji", "😀 ایموجی"),
        ],
        [
            _lk("lock_text", "📝 متن")
        ],
        [
            InlineKeyboardButton("📖 راهنمای کامل قفل رسانه", callback_data=f"exec_lock_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_manage_keyboard(owner_id, target_id):
    """پنل مدیریت یک کاربر خاص — دشمن/دوست/قفل/اکشن/انیمیشن (فقط مالک پنل)"""
    is_enemy_pv = db.is_enemy(owner_id, target_id, 'pv')
    is_enemy_g = db.is_enemy(owner_id, target_id, 'group')
    is_locked_pv = db.is_pv_locked(owner_id, target_id)
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✓ ' if is_enemy_pv else ''}🥷 دشمن پیوی",
                callback_data=f"um_enemy_pv_{target_id}_{owner_id}",
                style="success" if is_enemy_pv else "danger"
            ),
            InlineKeyboardButton(
                f"{'✓ ' if is_enemy_g else ''}👥 دشمن گروه",
                callback_data=f"um_enemy_g_{target_id}_{owner_id}",
                style="success" if is_enemy_g else "danger"
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'✓ ' if is_locked_pv else ''}🔒 قفل پیوی",
                callback_data=f"um_lockpv_{target_id}_{owner_id}",
                style="success" if is_locked_pv else "danger"
            ),
            InlineKeyboardButton(
                "💚 دوست",
                callback_data=f"um_friend_pv_{target_id}_{owner_id}",
                style="primary"
            ),
        ],
        [
            InlineKeyboardButton("🔒 قفل رسانه", callback_data=f"um_menu_locks_{target_id}_{owner_id}", style="danger"),
            InlineKeyboardButton("🎭 اکشن", callback_data=f"um_menu_action_{target_id}_{owner_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("✨ انیمیشن", callback_data=f"um_menu_anim_{target_id}_{owner_id}", style="primary"),
            InlineKeyboardButton("🌐 ترجمه", callback_data=f"um_menu_translate_{target_id}_{owner_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("✖️ بستن", callback_data=f"um_close_{target_id}_{owner_id}", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_um_translate_keyboard(owner_id, target_id):
    """ترجمه فقط برای یک کاربر (پیوی او)"""
    modes = {}
    mgr = selfbot_managers.get(str(owner_id))
    if mgr:
        modes = (getattr(mgr, 'per_user_translate', {}) or {}).get(int(target_id)) or {}
    def _btn(flag, label, key, code):
        on = bool(modes.get(key))
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{flag} {label}",
            callback_data=f"um_tr_{code}_{target_id}_{owner_id}",
            style="success" if on else "primary"
        )
    keyboard = [
        [_btn("🇬🇧", "انگلیسی", "english", "en"), _btn("🇸🇦", "عربی", "arabic", "ar")],
        [_btn("🇮🇱", "عبری", "hebrew", "he"), _btn("🇷🇺", "روسی", "russian", "ru")],
        [_btn("🇹🇷", "ترکی", "turkish", "tr"), _btn("🇩🇪", "آلمانی", "german", "de")],
        [_btn("🇫🇷", "فرانسوی", "french", "fr"), _btn("🇪🇸", "اسپانیایی", "spanish", "es")],
        [_btn("🇮🇹", "ایتالیایی", "italian", "it"), _btn("🇨🇳", "چینی", "chinese", "zh")],
        [_btn("🇯🇵", "ژاپنی", "japanese", "ja"), _btn("🇰🇷", "کره‌ای", "korean", "ko")],
        [_btn("🇮🇳", "هندی", "hindi", "hi"), _btn("🇮🇷", "فارسی", "persian", "fa")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"um_menu_main_{target_id}_{owner_id}", style="danger")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_user_locks_keyboard(owner_id, target_id):
    """زیرمنوی قفل رسانه برای یک کاربر"""
    def _lk(lt, label):
        on = db.get_user_lock(owner_id, target_id, lt)
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{label}",
            callback_data=f"um_{lt}_{target_id}_{owner_id}",
            style="success" if on else "danger"
        )
    keyboard = [
        [_lk("lock_sticker", "🎨 استیکر"), _lk("lock_photo", "📸 عکس"), _lk("lock_video", "🎥 ویدیو")],
        [_lk("lock_gif", "🎞️ گیف"), _lk("lock_voice", "🎤 ویس"), _lk("lock_music", "🎵 موزیک")],
        [_lk("lock_file", "📁 فایل"), _lk("lock_link", "🔗 لینک"), _lk("lock_text", "📝 متن")],
        [_lk("lock_contact", "👤 کانتکت"), _lk("lock_location", "📍 لوکیشن"), _lk("lock_video_note", "🔵 ویدیونوت")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"um_menu_main_{target_id}_{owner_id}", style="danger")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_user_action_keyboard(owner_id, target_id):
    """زیرمنوی اکشن — اجرا در پیوی هدف"""
    actions = [
        ("⌨️ تایپ", "تایپ"), ("🎤 ویس", "ویس"), ("🎥 ویدیو", "ویدیو"),
        ("📸 عکس", "عکس"), ("🎬 فیلم", "فیلم"), ("📁 فایل", "فایل"),
        ("🎮 بازی", "بازی"), ("🎨 استیکر", "استیکر"), ("📍 موقعیت", "موقعیت"),
        ("📞 تماس", "تماس"), ("🗣 صحبت", "صحبت"),
    ]
    keyboard = []
    row = []
    for label, key in actions:
        row.append(InlineKeyboardButton(label, callback_data=f"um_act_{key}_{target_id}_{owner_id}", style="primary"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("⏹️ خاموش", callback_data=f"um_actoff_{target_id}_{owner_id}", style="danger"),
        InlineKeyboardButton("🔙 بازگشت", callback_data=f"um_menu_main_{target_id}_{owner_id}", style="danger"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_user_anim_keyboard(owner_id, target_id):
    """زیرمنوی انیمیشن — ارسال به پیوی هدف"""
    keyboard = [
        [
            InlineKeyboardButton("❤️ قلب", callback_data=f"um_heart_{target_id}_{owner_id}", style="primary"),
            InlineKeyboardButton("🌙 ماه", callback_data=f"um_moon_{target_id}_{owner_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("💖 قلب پیشرفته", callback_data=f"um_advheart_{target_id}_{owner_id}", style="primary"),
            InlineKeyboardButton("💝 عشق", callback_data=f"um_love_{target_id}_{owner_id}", style="danger"),
        ],
        [
            InlineKeyboardButton("🕯️ سنتت", callback_data=f"um_santet_{target_id}_{owner_id}", style="primary"),
            InlineKeyboardButton("💻 هک", callback_data=f"um_hack_{target_id}_{owner_id}", style="danger"),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"um_menu_main_{target_id}_{owner_id}", style="danger")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_comment_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("💬 کامنت", callback_data=f"exec_comment_{user_id}", style="success"),
            InlineKeyboardButton("📊 کانال‌ها", callback_data=f"exec_channels_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🗑️ حذف کانال", callback_data=f"exec_delete_channel_{user_id}", style="danger"),
            InlineKeyboardButton("🔍 تست کانال", callback_data=f"exec_test_channel_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_comment_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_general_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📊 وضعیت", callback_data=f"exec_status_{user_id}", style="primary"),
            InlineKeyboardButton("ℹ️ درباره", callback_data=f"exec_about_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⏱️ پینگ", callback_data=f"exec_ping_{user_id}", style="primary"),
            InlineKeyboardButton("👤 پنل کاربر", callback_data=f"exec_user_panel_help_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_general_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_menu_keyboard(user_id):
    """هر دکمه اکشن را مستقیم اجرا می‌کند (در پیوی هدف پنل‌کاربر یا چت فعلی)"""
    actions = [
        ("⌨️ تایپ", "act_تایپ"),
        ("🎤 ویس", "act_ویس"),
        ("🎥 ویدیو", "act_ویدیو"),
        ("📸 عکس", "act_عکس"),
        ("🎬 فیلم", "act_فیلم"),
        ("📁 فایل", "act_فایل"),
        ("🎮 بازی", "act_بازی"),
        ("🎨 استیکر", "act_استیکر"),
        ("📍 موقعیت", "act_موقعیت"),
        ("📞 تماس", "act_تماس"),
        ("🗣 صحبت", "act_صحبت"),
    ]
    keyboard = []
    row = []
    for label, key in actions:
        row.append(InlineKeyboardButton(label, callback_data=f"exec_{key}_{user_id}", style="primary"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("⏹️ اکشن خاموش", callback_data=f"exec_action_off_{user_id}", style="danger"),
        InlineKeyboardButton("📋 وضعیت", callback_data=f"exec_action_list_{user_id}", style="primary"),
    ])
    keyboard.append([InlineKeyboardButton("📖 راهنما", callback_data=f"exec_action_help_{user_id}", style="primary")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")])
    return InlineKeyboardMarkup(keyboard)

def get_translate_menu_keyboard(user_id):
    translate_mode = {}
    if str(user_id) in selfbot_managers:
        translate_mode = dict(selfbot_managers[str(user_id)].translate_mode or {})
    def _btn(flag, label, key, code):
        on = bool(translate_mode.get(key))
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{flag} {label}",
            callback_data=f"exec_translate_{code}_{user_id}",
            style="success" if on else "primary"
        )
    keyboard = [
        [_btn("🇬🇧", "انگلیسی", "english", "en"), _btn("🇸🇦", "عربی", "arabic", "ar")],
        [_btn("🇮🇱", "عبری", "hebrew", "he"), _btn("🇷🇺", "روسی", "russian", "ru")],
        [_btn("🇹🇷", "ترکی", "turkish", "tr"), _btn("🇩🇪", "آلمانی", "german", "de")],
        [_btn("🇫🇷", "فرانسوی", "french", "fr"), _btn("🇪🇸", "اسپانیایی", "spanish", "es")],
        [_btn("🇮🇹", "ایتالیایی", "italian", "it"), _btn("🇨🇳", "چینی", "chinese", "zh")],
        [_btn("🇯🇵", "ژاپنی", "japanese", "ja"), _btn("🇰🇷", "کره‌ای", "korean", "ko")],
        [_btn("🇮🇳", "هندی", "hindi", "hi"), _btn("🇮🇷", "فارسی", "persian", "fa")],
        [InlineKeyboardButton("📖 راهنما مترجم", callback_data=f"exec_translate_help_{user_id}", style="primary")],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_crypto_menu_keyboard(user_id):
    """منوی ارزها — نرخ / پریمیوم / استارز"""
    keyboard = [
        [
            InlineKeyboardButton("📊 لیست شاخص‌ها", callback_data=f"exec_crypto_rates_{user_id}", style="primary"),
            InlineKeyboardButton("💎 پریمیوم فرگمنت", callback_data=f"exec_crypto_premium_{user_id}", style="success"),
        ],
        [
            InlineKeyboardButton("⭐ استارز فرگمنت", callback_data=f"exec_crypto_stars_{user_id}", style="primary"),
            InlineKeyboardButton("📖 راهنما ارزها", callback_data=f"exec_crypto_help_{user_id}", style="primary"),
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_google_menu_keyboard(user_id):
    search_on = False
    if str(user_id) in selfbot_managers:
        search_on = bool(getattr(selfbot_managers[str(user_id)], 'search_mode', False))
    keyboard = [
        [
            InlineKeyboardButton(f"{'✓ ' if search_on else ''}🔍 سرچ", callback_data=f"exec_search_on_{user_id}", style="success" if search_on else "primary"),
            InlineKeyboardButton(f"{'✓ ' if not search_on else ''}❌ خروج جستجو", callback_data=f"exec_search_off_{user_id}", style="danger" if not search_on else "primary"),
            InlineKeyboardButton("🎵 اهنگ", callback_data=f"exec_music_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_google_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_profile_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📸 ست پروف", callback_data=f"exec_set_profile_{user_id}", style="success"),
            InlineKeyboardButton("✏️ ست بیو", callback_data=f"exec_set_bio_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🗑️ حذف ست پروف", callback_data=f"exec_delete_profile_{user_id}", style="danger"),
            InlineKeyboardButton("🗑️ حذف ست بیو", callback_data=f"exec_delete_bio_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_profile_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_style_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    current = settings.get('text_style', 'هیچ')
    keyboard = [
        [
            InlineKeyboardButton(f"بولد {'' if current != 'بولد' else '✓'}", callback_data=f"exec_bold_{user_id}", style="primary"),
            InlineKeyboardButton(f"زیرخط {'' if current != 'زیرخط' else '✓'}", callback_data=f"exec_underline_{user_id}", style="primary"),
            InlineKeyboardButton(f"خط خورده {'' if current != 'خط خورده' else '✓'}", callback_data=f"exec_strike_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton(f"نقل قول {'' if current != 'نقل قول' else '✓'}", callback_data=f"exec_quote_{user_id}", style="primary"),
            InlineKeyboardButton(f"اسپویلر {'' if current != 'اسپویلر' else '✓'}", callback_data=f"exec_spoiler_{user_id}", style="primary"),
            InlineKeyboardButton(f"کج {'' if current != 'کج' else '✓'}", callback_data=f"exec_italic_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton(f"کد {'' if current != 'کد' else '✓'}", callback_data=f"exec_code_{user_id}", style="primary"),
            InlineKeyboardButton(f"پیش {'' if current != 'پیش' else '✓'}", callback_data=f"exec_pre_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_style_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reaction_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("👍 ریکت", callback_data=f"exec_reaction_{user_id}", style="success"),
            InlineKeyboardButton("❌ حذف ریکت", callback_data=f"exec_reaction_off_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_reaction_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_spam_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📩 اسپم", callback_data=f"exec_spam_{user_id}", style="danger")],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_spam_help_{user_id}", style="primary")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_change_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("✏️ تغییر اسم", callback_data=f"exec_change_name_{user_id}", style="primary"),
            InlineKeyboardButton("✏️ تغییر بیو", callback_data=f"exec_change_bio_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📸 تغییر پروفایل", callback_data=f"exec_change_profile_{user_id}", style="success"),
            InlineKeyboardButton("📸 پروف", callback_data=f"exec_change_profile_alt_{user_id}", style="success")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_change_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_enemy_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📋 لیست دشمن", callback_data=f"exec_enemy_list_{user_id}", style="danger"),
            InlineKeyboardButton("📝 اضافه اسپم", callback_data=f"exec_add_spam_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("✅ اتمام اسپم", callback_data=f"exec_end_spam_{user_id}", style="success"),
            InlineKeyboardButton("📜 لیست اسپم", callback_data=f"exec_spam_list_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🗑️ پاک کردن اسپم", callback_data=f"exec_clear_spam_{user_id}", style="danger"),
            InlineKeyboardButton("🗑️ حذف اسپم", callback_data=f"exec_delete_spam_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_enemy_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_filter_menu_keyboard(user_id):
    is_enabled = db.get_filter_enabled(user_id)
    keyboard = [
        [
            InlineKeyboardButton("🚫 .فیلتر [کلمه]", callback_data=f"exec_filter_word_{user_id}", style="danger"),
            InlineKeyboardButton(f"✅ فیلتر روشن {'✓' if is_enabled else ''}", callback_data=f"exec_filter_on_{user_id}", style="success" if is_enabled else "secondary")
        ],
        [
            InlineKeyboardButton(f"❌ فیلتر خاموش {'✓' if not is_enabled else ''}", callback_data=f"exec_filter_off_{user_id}", style="danger" if not is_enabled else "secondary"),
            InlineKeyboardButton("📜 لیست / مدیریت کلمات", callback_data=f"exec_filter_list_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_filter_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_filter_words_keyboard(user_id, filters):
    keyboard = []
    if filters:
        for word_info in filters:
            status_icon = "✅" if word_info['enabled'] else "❌"
            word_label = word_info['word']
            if len(word_label) > 20:
                word_label = word_label[:20] + "…"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_icon} {word_label}",
                    callback_data=f"exec_filtertgl_{word_info['id']}_{user_id}",
                    style="success" if word_info['enabled'] else "secondary"
                ),
                InlineKeyboardButton(
                    "🗑️ حذف",
                    callback_data=f"exec_filterdel_{word_info['id']}_{user_id}",
                    style="danger"
                )
            ])
    keyboard.append([
        InlineKeyboardButton("🔄 بروزرسانی لیست", callback_data=f"exec_filter_list_{user_id}", style="primary")
    ])
    keyboard.append([
        InlineKeyboardButton("⚈ بازگشت", callback_data=f"filter_menu_{user_id}", style="danger")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_protection_menu_keyboard(user_id):
    settings = db.get_spam_settings(user_id)
    on = bool(settings.get('spam_protection'))
    keyboard = [
        [
            InlineKeyboardButton(f"{'✓ ' if on else ''}🛡️ اسپم روشن", callback_data=f"exec_spam_protection_on_{user_id}", style="success" if on else "primary"),
            InlineKeyboardButton(f"{'✓ ' if not on else ''}🛡️ اسپم خاموش", callback_data=f"exec_spam_protection_off_{user_id}", style="danger" if not on else "primary")
        ],
        [
            InlineKeyboardButton("⚙️ تنظیم اسپم", callback_data=f"exec_spam_settings_{user_id}", style="primary"),
            InlineKeyboardButton("📊 وضعیت اسپم", callback_data=f"exec_spam_status_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_protection_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_ai_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    ai = settings['ai_status']
    keyboard = [
        [
            InlineKeyboardButton(f"🟢 پیوی ۱ {'' if not ai['ai_1_pm'] else '✓'}", callback_data=f"exec_ai_pm_1_{user_id}", style="success" if not ai['ai_1_pm'] else "primary"),
            InlineKeyboardButton(f"🔵 پیوی ۲ {'' if not ai['ai_2_pm'] else '✓'}", callback_data=f"exec_ai_pm_2_{user_id}", style="success" if not ai['ai_2_pm'] else "primary"),
            InlineKeyboardButton(f"🟣 پیوی ۳ {'' if not ai['ai_3_pm'] else '✓'}", callback_data=f"exec_ai_pm_3_{user_id}", style="success" if not ai['ai_3_pm'] else "primary")
        ],
        [
            InlineKeyboardButton("⚫ خاموش پیوی", callback_data=f"exec_ai_pm_off_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton(f"🟢 گروه ۱ {'' if not ai['ai_1_group'] else '✓'}", callback_data=f"exec_ai_group_1_{user_id}", style="success" if not ai['ai_1_group'] else "primary"),
            InlineKeyboardButton(f"🔵 گروه ۲ {'' if not ai['ai_2_group'] else '✓'}", callback_data=f"exec_ai_group_2_{user_id}", style="success" if not ai['ai_2_group'] else "primary"),
            InlineKeyboardButton(f"🟣 گروه ۳ {'' if not ai['ai_3_group'] else '✓'}", callback_data=f"exec_ai_group_3_{user_id}", style="success" if not ai['ai_3_group'] else "primary")
        ],
        [
            InlineKeyboardButton("⚫ خاموش گروه", callback_data=f"exec_ai_group_off_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_ai_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_report_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📍 تنظیم گزارش", callback_data=f"exec_set_report_{user_id}", style="success"),
            InlineKeyboardButton("ℹ️ گروه گزارش", callback_data=f"exec_show_report_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_report_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    q_data = getattr(query, 'data', None)
    q_user = getattr(getattr(query, 'from_user', None), 'id', None)
    print(f"🔘 [DEBUG] کلیک دکمه | user_id={q_user} | callback_data={q_data}")
    try:
        await _button_callback_impl(update, context)
    except Exception as e:
        tb = traceback.format_exc()
        error_block = (
            f"\n{'='*70}\n"
            f"❌❌❌ خطای دکمه پنل ❌❌❌\n"
            f"زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"user_id: {q_user}\n"
            f"callback_data: {q_data}\n"
            f"نوع خطا: {type(e).__name__}\n"
            f"متن خطا: {e}\n"
            f"--- Traceback کامل ---\n{tb}"
            f"{'='*70}\n"
        )
        print(error_block)
        logger.error(error_block)
        try:
            if query:
                await query.answer(f"⚠️ خطا: {type(e).__name__}: {str(e)[:150]}", show_alert=True)
        except Exception:
            pass

async def _button_callback_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    # um_ : owner = آخرین عدد — target = یکی مانده به آخر (اینجا فقط owner چک می‌شود)
    if data.startswith('um_'):
        parts = data.split('_')
        owner_part = None
        for part in reversed(parts):
            if part.isdigit() and len(part) >= 5:
                owner_part = part
                break
        if owner_part and owner_part != user_id_str and not is_admin(user_id):
            await query.answer("⛔ فقط کسی که پنل کاربر را باز کرده می‌تواند دکمه‌ها را کنترل کند", show_alert=True)
            return
    elif '_' in data and not data.startswith(('admin_', 'approve_', 'reject_', 'stop_selfbot_', 'restart_selfbot_', 'desc_', 'menu_', 'code_', 'um_')):
        parts = data.split('_')
        # فقط آخرین عدد بلند = owner پنل (نه target)
        owner_part = None
        for part in reversed(parts):
            if part.isdigit() and len(part) >= 5:
                owner_part = part
                break
        if owner_part and owner_part != user_id_str and not is_admin(user_id):
            await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
            return
    if data.startswith("close_panel_"):
        await query.answer("❌ بستن پنل")
        try:
            await query.message.delete()
        except:
            await query.edit_message_text("✅ پنل بسته شد")
        return
    
    # ========== ورود کد تأیید با دکمه‌های فارسی ==========
    if data.startswith("code_digit_") or data.startswith("code_del_") or data.startswith("code_ok_") or data.startswith("code_back_"):
        await query.answer()
        parts = data.split('_')
        action = parts[1]  # digit / del / ok / back
        user_data = db.get_user(user_id_str)
        if not user_data or user_data.get('step') != 'get_code':
            await query.answer("⚠️ مرحله ورود کد فعال نیست", show_alert=True)
            return
        current_code = user_data.get('code') or ''
        if action == 'digit':
            digit = parts[2]
            if len(current_code) >= 5:
                await query.answer("کد کامل است — تأیید را بزنید", show_alert=False)
                return
            current_code = current_code + digit
            db.update_user(user_id_str, code=current_code)
            display = current_code if len(current_code) >= 5 else (current_code + '•' * (5 - len(current_code)))
            try:
                await query.edit_message_text(
                    f"✅ کد تأیید ارسال شد!\n\n📩 کد ۵ رقمی را با دکمه‌های زیر وارد کنید:\n\nکد: `{display}`",
                    reply_markup=query.message.reply_markup,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return
        if action == 'del':
            current_code = current_code[:-1] if current_code else ''
            db.update_user(user_id_str, code=current_code)
            display = '(خالی)' if not current_code else (current_code + '•' * (5 - len(current_code)))
            try:
                await query.edit_message_text(
                    f"✅ کد تأیید ارسال شد!\n\n📩 کد ۵ رقمی را با دکمه‌های زیر وارد کنید:\n\nکد: `{display}`",
                    reply_markup=query.message.reply_markup,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return
        if action == 'back':
            db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None)
            await query.edit_message_text("🔙 بازگشت\n\nشماره تلفن خود را دوباره وارد کنید:\nمثال: +989123456789")
            return
        if action == 'ok':
            if len(current_code) < 5:
                await query.answer("کد باید ۵ رقم باشد", show_alert=True)
                return
            await query.edit_message_text("⏳ در حال تأیید کد...")
            try:
                session_name = f"user_{user_id_str}"
                session_path = os.path.join(SESSIONS_FOLDER, f"{session_name}.session")
                user_api = get_user_api(user_id_str)
                if not user_api:
                    await query.edit_message_text("❌ خطا در دریافت API")
                    return
                API_ID = user_api["api_id"]
                API_HASH = user_api["api_hash"]
                client = TelegramClient(session_path, API_ID, API_HASH)
                await client.connect()
                user_data = db.get_user(user_id_str)
                await client.sign_in(phone=user_data['phone'], code=current_code, phone_code_hash=user_data['phone_code_hash'])
                expiration_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                db.update_user(user_id_str, self_active=1, session_file=session_path, expiration_date=expiration_date, step=None)
                await client.disconnect()
                manager = SelfBotManager(user_id_str)
                if await manager.start(session_path):
                    selfbot_managers[user_id_str] = manager
                await query.edit_message_text("✅ سلف شما فعال شد")
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"✅ کاربر {user_data.get('full_name')} وارد شد\n🆔 {user_id_str}\n📞 {user_data.get('phone')}"
                    )
                except Exception:
                    pass
            except SessionPasswordNeededError:
                db.update_user(user_id_str, step='get_password')
                await query.edit_message_text("🔐 رمز دو مرحله‌ای را وارد کنید:")
            except Exception as e:
                logger.error(f"کد تأیید: {e}")
                await query.edit_message_text("✖ کد نامعتبر است\nدوباره شماره را وارد کنید")
                db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None)
            return
    
    if data == "back_main":
        # بازگشت به پنل اصلی → هدف پنل‌کاربر پاک شود
        try:
            panel_lock_targets.pop(user_id, None)
            panel_lock_targets.pop(str(user_id), None)
        except Exception:
            pass
        name = get_main_panel_text(query.from_user)
        try:
            if query.message and query.message.photo:
                await query.edit_message_caption(
                    caption=name,
                    reply_markup=get_main_panel_keyboard(user_id)
                )
            else:
                await safe_edit_panel(
                    query,
                    name,
                    reply_markup=get_main_panel_keyboard(user_id)
                )
        except Exception:
            try:
                await query.edit_message_reply_markup(
                    reply_markup=get_main_panel_keyboard(user_id)
                )
            except Exception as e:
                logger.debug(f"back_main: {e}")
        return
    if data == "admin_panel":
        await admin_panel_handler(update, context)
        return
    if data == "admin_requests":
        await admin_requests_handler(update, context)
        return
    if data == "admin_login":
        await admin_login_handler(update, context)
        return
    if data == "admin_active":
        await admin_active_handler(update, context)
        return
    if data == "admin_selfbots":
        await admin_selfbots_handler(update, context)
        return
    if data == "admin_stats":
        await admin_stats_handler(update, context)
        return
    if data == "admin_broadcast":
        await admin_broadcast_handler(update, context)
        return
    if data == "admin_backup_db":
        await admin_backup_db_handler(update, context)
        return
    if data == "admin_restore_db":
        await admin_restore_db_handler(update, context)
        return
    if data.startswith("approve_"):
        await approve_handler(update, context)
        return
    if data.startswith("reject_"):
        await reject_handler(update, context)
        return
    if data.startswith("stop_selfbot_"):
        await stop_selfbot_handler(update, context)
        return
    if data.startswith("restart_selfbot_"):
        await restart_selfbot_handler(update, context)
        return
    if data.startswith("membership_request_"):
        await membership_request_handler(update, context)
        return
    if data.startswith("membership_status_"):
        await membership_status_handler(update, context)
        return
    # ========== پنل مدیریت کاربر (um_) — فقط مالک پنل ==========
    if data.startswith("um_"):
        try:
            parts = data.split('_')
            # um_ACTION_TARGET_OWNER
            owner_id = int(parts[-1])
            # فقط کسی که پنل را باز کرده کنترل می‌کند
            if int(user_id) != int(owner_id) and not is_admin(user_id):
                await query.answer("⛔ فقط کسی که پنل کاربر را باز کرده می‌تواند دکمه‌ها را کنترل کند", show_alert=True)
                return
            target_id = int(parts[-2])
            # هدف ریپلای‌شده (کاربر مقابل) هم حق کلیک ندارد
            if int(user_id) == int(target_id):
                await query.answer("⛔ شما هدف این پنل هستید و به دکمه‌ها دسترسی ندارید", show_alert=True)
                return
            action = '_'.join(parts[1:-2])  # lock_sticker / enemy_pv / menu_action / act_تایپ / heart ...
            panel_lock_targets[owner_id] = target_id
            panel_lock_targets[str(owner_id)] = target_id
            # answer بعداً برای اکشن/انیمیشن؛ برای بقیه همین‌جا
            _need_later_answer = action.startswith('act_') or action == 'actoff' or action in (
                'heart', 'moon', 'advheart', 'love', 'santet', 'hack'
            )
            if not _need_later_answer:
                try:
                    await query.answer()
                except Exception:
                    pass

            # --- زیر‌منوها ---
            if action == 'menu_main':
                kb = get_user_manage_keyboard(owner_id, target_id)
                try:
                    await query.edit_message_reply_markup(reply_markup=kb)
                except Exception:
                    pass
                return
            if action == 'menu_locks':
                try:
                    await query.edit_message_reply_markup(reply_markup=get_user_locks_keyboard(owner_id, target_id))
                except Exception:
                    pass
                return
            if action == 'menu_action':
                try:
                    await query.edit_message_reply_markup(reply_markup=get_user_action_keyboard(owner_id, target_id))
                except Exception:
                    pass
                return
            if action == 'menu_anim':
                try:
                    await query.edit_message_reply_markup(reply_markup=get_user_anim_keyboard(owner_id, target_id))
                except Exception:
                    pass
                return
            if action == 'menu_translate':
                try:
                    await query.edit_message_reply_markup(reply_markup=get_um_translate_keyboard(owner_id, target_id))
                except Exception:
                    pass
                return

            # ترجمه مخصوص همین کاربر: um_tr_en_TARGET_OWNER → action=tr_en
            if action.startswith('tr_'):
                code = action[3:]  # en / ar / ...
                code_to_lang = {
                    'en': 'english', 'ar': 'arabic', 'he': 'hebrew', 'ru': 'russian',
                    'tr': 'turkish', 'de': 'german', 'fr': 'french', 'es': 'spanish',
                    'it': 'italian', 'zh': 'chinese', 'ja': 'japanese', 'ko': 'korean',
                    'hi': 'hindi', 'fa': 'persian',
                }
                lang = code_to_lang.get(code)
                if not lang:
                    return
                mgr = selfbot_managers.get(str(owner_id))
                if not mgr:
                    try:
                        await query.answer("❌ سلف‌بات فعال نیست", show_alert=True)
                    except Exception:
                        pass
                    return
                if not hasattr(mgr, 'per_user_translate') or mgr.per_user_translate is None:
                    mgr.per_user_translate = {}
                tid = int(target_id)
                modes = dict(mgr.per_user_translate.get(tid) or {})
                modes[lang] = not bool(modes.get(lang))
                # فقط یک زبان فعال برای کاربر هدف
                if modes[lang]:
                    for k in list(modes.keys()):
                        if k != lang:
                            modes[k] = False
                mgr.per_user_translate[tid] = modes
                try:
                    await query.edit_message_reply_markup(reply_markup=get_um_translate_keyboard(owner_id, target_id))
                except Exception:
                    pass
                return

            if action == 'close':
                try:
                    panel_lock_targets.pop(owner_id, None)
                    panel_lock_targets.pop(str(owner_id), None)
                except Exception:
                    pass
                try:
                    await query.answer("✖️ بسته شد")
                except Exception:
                    pass
                try:
                    await query.message.delete()
                except Exception:
                    try:
                        await query.edit_message_reply_markup(reply_markup=None)
                    except Exception:
                        try:
                            await query.edit_message_caption(caption="✖️ پنل بسته شد", reply_markup=None)
                        except Exception:
                            try:
                                await query.edit_message_text("✖️ پنل بسته شد")
                            except Exception:
                                pass
                return

            # --- اکشن در پیوی هدف ---
            if action.startswith('act_') or action == 'actoff':
                mgr = selfbot_managers.get(str(owner_id))
                if not mgr:
                    await query.answer("❌ سلف‌بات فعال نیست", show_alert=True)
                    return
                try:
                    if action == 'actoff':
                        stopped = await mgr.stop_action(int(target_id))
                        await query.answer(f"⏹️ اکشن {stopped or ''} خاموش", show_alert=False)
                    else:
                        act_name = action[4:]  # بعد از act_
                        ok = await mgr.start_action(int(target_id), act_name)
                        await query.answer(f"{'✅' if ok else '❌'} اکشن {act_name} → {target_id}", show_alert=not ok)
                except Exception as e:
                    logger.error(f"um act: {e}")
                    await query.answer(f"خطا: {str(e)[:60]}", show_alert=True)
                return

            # --- انیمیشن در پیوی هدف ---
            if action in ('heart', 'moon', 'advheart', 'love', 'santet', 'hack'):
                mgr = selfbot_managers.get(str(owner_id))
                if not mgr:
                    await query.answer("❌ سلف‌بات فعال نیست", show_alert=True)
                    return
                tid = int(target_id)
                try:
                    if action == 'heart':
                        asyncio.create_task(mgr.heart_animation(tid))
                    elif action == 'moon':
                        asyncio.create_task(mgr.moon_animation(tid))
                    elif action in ('advheart', 'love'):
                        async def _ah():
                            m = await mgr.client.send_message(tid, '❤️' if action == 'advheart' else '💝')
                            await advanced_heart_animation(m)
                        asyncio.create_task(_ah())
                    elif action == 'santet':
                        async def _st():
                            s = await mgr.client.send_message(tid, '🕯️')
                            for i in range(0, 101, 5):
                                bar = '█' * int(i/5) + '░' * (20 - int(i/5))
                                await s.edit(f'🕯️ {i}% [{bar}]')
                                await asyncio.sleep(0.05)
                            await s.edit('✅ انجام شد 🥴')
                        asyncio.create_task(_st())
                    elif action == 'hack':
                        async def _hk():
                            h = await mgr.client.send_message(tid, '💻')
                            for step in [
                                'User online: True\nTelegram access: True',
                                'Hacking... 50%\n[██████████░░░░░░░░░░]',
                                'Hacking... 100%\n[████████████████████]',
                                '✅ هک کامل شد',
                            ]:
                                await asyncio.sleep(1.2)
                                await h.edit(step)
                        asyncio.create_task(_hk())
                    await query.answer(f"✨ {action} → {tid}", show_alert=False)
                except Exception as e:
                    logger.error(f"um anim: {e}")
                    await query.answer(f"خطا: {str(e)[:60]}", show_alert=True)
                return

            # --- دشمن / دوست / قفل ---
            if action == 'enemy_pv':
                if db.is_enemy(owner_id, target_id, 'pv'):
                    db.remove_enemy(owner_id, target_id, 'pv')
                else:
                    db.add_enemy(owner_id, target_id, 'pv')
            elif action == 'friend_pv':
                if db.is_enemy(owner_id, target_id, 'pv'):
                    db.remove_enemy(owner_id, target_id, 'pv')
            elif action == 'enemy_g':
                if db.is_enemy(owner_id, target_id, 'group'):
                    db.remove_enemy(owner_id, target_id, 'group')
                else:
                    db.add_enemy(owner_id, target_id, 'group')
            elif action == 'lockpv':
                if db.is_pv_locked(owner_id, target_id):
                    db.remove_locked_pv(owner_id, target_id)
                else:
                    db.add_locked_pv(owner_id, target_id)
            elif action.startswith('lock_'):
                cur = db.get_user_lock(owner_id, target_id, action)
                db.set_user_lock(owner_id, target_id, action, not cur)

            # رفرش کیبورد مناسب
            if action.startswith('lock_'):
                kb = get_user_locks_keyboard(owner_id, target_id)
            else:
                kb = get_user_manage_keyboard(owner_id, target_id)
            try:
                await query.edit_message_reply_markup(reply_markup=kb)
            except Exception:
                try:
                    await safe_edit_panel(query, query.message.caption or query.message.text or "👤 مدیریت کاربر", reply_markup=kb)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"um_ handler: {e}\n{traceback.format_exc()}")
        return

    if data.startswith("exec_"):
        await exec_command_handler(update, context)
        return
    if data.startswith("bio_menu_"):
        await safe_edit_panel(query, "› تنظیمات بیو", reply_markup=get_bio_menu_keyboard(user_id))
        return
    if data.startswith("font_menu_"):
        await safe_edit_panel(query, "› انتخاب فونت تایم", reply_markup=get_font_menu_keyboard(user_id))
        return
    if data.startswith("flag_menu_"):
        await safe_edit_panel(query, "› انتخاب پرچم", reply_markup=get_flag_menu_keyboard(user_id))
        return
    if data.startswith("pclock_menu_"):
        try:
            await query.answer()
        except Exception:
            pass
        try:
            kb = get_profile_clock_menu_keyboard(user_id)
        except Exception as e:
            logger.error(f"pclock keyboard: {e}")
            try:
                await query.answer(f"خطا: {e}", show_alert=True)
            except Exception:
                pass
            return
        ok = await safe_edit_panel(query, "🕰 ساعت در پروفایل — روشن/خاموش و رنگ", reply_markup=kb)
        if not ok:
            try:
                chat_id = query.message.chat_id if query.message else user_id
                await context.bot.send_message(chat_id=chat_id, text="🕰 ساعت در پروفایل — روشن/خاموش و رنگ", reply_markup=kb)
            except Exception as e:
                logger.error(f"pclock send: {e}")
        return
    
    parts = data.split('_')
    if len(parts) > 1:
        action = parts[0]
        menu_keyboards = {
            "time": ("⏰ زمان و پروفایل", get_time_menu_keyboard),
            "bio": ("📝 تنظیمات بیو", get_bio_menu_keyboard),
            "font": ("🔤 فونت تایم", get_font_menu_keyboard),
            "flag": ("🏳️ پرچم", get_flag_menu_keyboard),
            "animation": ("✨ انیمیشن", get_animation_menu_keyboard),
            "user": ("👤 کاربران", get_user_menu_keyboard),
            "lock": ("🔒 قفل رسانه", get_lock_menu_keyboard),
            "comment": ("💬 کامنت", get_comment_menu_keyboard),
            "general": ("📌 عمومی", get_general_menu_keyboard),
            "action": ("🎭 اکشن", get_action_menu_keyboard),
            "games": ("🎮 بازی‌ها", get_games_menu_keyboard),
            "translate": ("🌐 ترجمه", get_translate_menu_keyboard),
            "google": ("🔎 گوگل", get_google_menu_keyboard),
            "info": ("ℹ️ اطلاعاتی", get_info_menu_keyboard),
            "profile": ("🖼 پروفایل", get_profile_menu_keyboard),
            "style": ("✍️ استایل متن", get_style_menu_keyboard),
            "message": ("📨 مدیریت پیام", get_message_menu_keyboard),
            "reaction": ("👍 ریکشن", get_reaction_menu_keyboard),
            "spam": ("💣 اسپم", get_spam_menu_keyboard),
            "change": ("✏️ تغییر پروفایل", get_change_menu_keyboard),
            "enemy": ("👹 دشمنان", get_enemy_menu_keyboard),
            "filter": ("🚫 فیلتر کلمات", get_filter_menu_keyboard),
            "pclock": ("🕰 ساعت در پروفایل", get_profile_clock_menu_keyboard),
            "protection": ("🛡 حفاظت اسپم", get_protection_menu_keyboard),
            "ai": ("🤖 هوش مصنوعی", get_ai_menu_keyboard),
            "report": ("📣 گزارش", get_report_menu_keyboard),
            "tools": ("🛠 ابزارها", get_tools_menu_keyboard),
            "monshi": ("🗣 منشی هوشمند", get_monshi_menu_keyboard),
            "mention": ("📢 تگ همه", get_mention_menu_keyboard),
            "fortune": ("🔮 فال", get_fortune_menu_keyboard),
            "crypto": ("💰 ارزها", get_crypto_menu_keyboard),
            "backup": ("📦 بکاپ‌گیری", get_backup_menu_keyboard),
        }

        if action in menu_keyboards and len(parts) >= 2 and parts[1] == "menu":
            text, keyboard_func = menu_keyboards[action]
            try:
                await query.answer()
            except Exception:
                pass
            try:
                kb = keyboard_func(user_id)
            except Exception as e:
                logger.error(f"menu keyboard {action}: {e}")
                try:
                    await query.answer(f"خطا در منو: {e}", show_alert=True)
                except Exception:
                    pass
                return
            ok = await safe_edit_panel(query, text, reply_markup=kb)
            if not ok:
                try:
                    chat_id = query.message.chat_id if query.message else user_id
                    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
                except Exception as e:
                    logger.error(f"menu send fallback {action}: {e}")
            return

async def exec_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    if not data.startswith('exec_'):
        return
    
    chat_id = None
    try:
        if query.message is not None:
            chat_id = getattr(query.message, 'chat_id', None) or getattr(getattr(query.message, 'chat', None), 'id', None)
    except Exception:
        chat_id = None
    if not chat_id and update.effective_chat:
        chat_id = update.effective_chat.id
    if not chat_id:
        chat_id = user_id
    
    try:
        await query.answer()
    except Exception:
        pass
    parts = data.split('_')
    if len(parts) >= 2:
        owner_id = None
        for part in reversed(parts):
            if part.isdigit():
                owner_id = part
                break
        if owner_id and str(owner_id) != user_id_str:
            await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
            return
    if user_id_str not in selfbot_managers:
        try:
            await context.bot.send_message(chat_id=chat_id, text="❌ سلف‌بات شما فعال نیست")
        except Exception:
            pass
        return
    manager = selfbot_managers[user_id_str]
    # پارس امن cmd بدون خراب شدن ایندکس فونت/پرچم وقتی user_id در رشته باشد
    _raw = data[5:] if data.startswith('exec_') else data  # بعد از exec_
    if _raw.endswith(f'_{user_id}'):
        cmd = _raw[: -(len(str(user_id)) + 1)]
    else:
        cmd = _raw.replace(f'_{user_id}', '')
    
    # پیام موقت «در حال اجرا» فقط برای دستوراتی که واقعاً نیاز دارند (نه toggle)
    msg = None
    _silent_prefixes = (
        'bio_', 'time_on', 'time_off', 'time_flag', 'font_', 'flag_',
        'lock_', 'filter_', 'ai_', 'autosend_', 'self_on', 'self_off',
        'monshi_on', 'monshi_off', 'spam_protection_', 'bold', 'underline',
        'strike', 'quote', 'spoiler', 'italic', 'code', 'pre',
        'translate_', 'style_', 'pclock_', 'open_filter', 'open_pclock'
    )
    _needs_temp_msg = not any(cmd.startswith(p) or cmd == p.rstrip('_') for p in _silent_prefixes)
    if _needs_temp_msg:
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text="⏳")
        except Exception:
            msg = None
    
    async def _silent_done():
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass
    
    if cmd == 'open_filter':
        try:
            if msg:
                await msg.delete()
        except Exception:
            pass
        try:
            await safe_edit_panel(query, "🚫 فیلتر کلمات", reply_markup=get_filter_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text="🚫 فیلتر کلمات", reply_markup=get_filter_menu_keyboard(user_id))
            except Exception as e:
                logger.error(f"open_filter: {e}")
                try:
                    await query.answer(str(e)[:80], show_alert=True)
                except Exception:
                    pass
        return
    if cmd == 'open_pclock':
        try:
            if msg:
                await msg.delete()
        except Exception:
            pass
        try:
            await safe_edit_panel(query, "🕰 ساعت در پروفایل", reply_markup=get_profile_clock_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text="🕰 ساعت در پروفایل", reply_markup=get_profile_clock_menu_keyboard(user_id))
            except Exception as e:
                logger.error(f"open_pclock: {e}")
        return

    bio_commands = {
        'bio_time1': 'ساعت_در_بیو',
        'bio_time2': 'ساعت_در_بیو_۲',
        'bio_date': 'بیو_تاریخ',
        'bio_full': 'بیو_کامل',
        'bio_love': 'بیو_عاشقانه',
        'bio_emoji': 'بیو_ایموجی',
        'bio_season': 'بیو_فصل',
        'bio_weekday': 'بیو_روز_هفته',
        'bio_countdown': 'بیو_شمارش_معکوس',
        'bio_custom': 'بیو_متن_دلخواه',
    }
    for cmd_key, setting_name in bio_commands.items():
        if cmd == cmd_key or cmd.startswith(cmd_key + '_'):
            current = manager.get_bio_setting(setting_name)
            new_status = 'خاموش' if current == 'روشن' else 'روشن'
            # فقط یکی روشن بماند (اختیاری ولی تمیزتر)
            if new_status == 'روشن':
                for other_key, other_name in bio_commands.items():
                    if other_name != setting_name:
                        manager.set_bio_setting(other_name, 'خاموش')
            manager.set_bio_setting(setting_name, new_status)
            try:
                await manager.update_bio_with_settings()
            except Exception as e:
                logger.error(f"bio update: {e}")
            await _silent_done()
            try:
                await refresh_panel_keyboard(query, user_id, "📝 تنظیمات بیو", get_bio_menu_keyboard)
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش: {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            return
    
    if cmd == 'fortune_general':
        await manager.fortune_telling(chat_id, msg)
        return
    if cmd == 'fortune_hafez':
        await manager.hafez_fortune(chat_id, msg)
        return
    if cmd == 'fortune_coffee':
        await manager.coffee_fortune(chat_id, msg)
        return
    
    if cmd == 'monshi_on':
        manager.monshi_step = 'wait_text'
        manager.monshi_draft = ""
        try:
            await query.answer("متن منشی را در چت سلف بفرستید", show_alert=False)
        except Exception:
            pass
        try:
            if msg:
                await msg.edit_text(
                    "🤖 منشی — متن پاسخ را در چت سلف‌بات بفرستید\n"
                    "بعد بنویسید: اتمام متن\n\n"
                    "دستور: منشی روشن"
                )
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🗣 منشی", get_monshi_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'monshi_off':
        db.set_monshi_status(user_id, False, getattr(manager, 'monshi_answer', '') or '')
        manager.monshi_mode = False
        manager.monshi_step = None
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🗣 منشی", get_monshi_menu_keyboard)
        except Exception:
            pass
        return

    if cmd == 'learning_on':
        db.set_learning_enabled(user_id, True)
        manager.learning_enabled = True
        try:
            await refresh_panel_keyboard(query, user_id, "🛠 ابزارها", get_tools_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'learning_off':
        db.set_learning_enabled(user_id, False)
        manager.learning_enabled = False
        try:
            await refresh_panel_keyboard(query, user_id, "🛠 ابزارها", get_tools_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'learning_list':
        answers = db.get_answers(user_id)
        text = "📋 لیست یادگیری:\n\n" if answers else "📋 لیست یادگیری خالی است"
        for i, (q, a) in enumerate((answers or {}).items(), 1):
            text += f"{i}. ❓ {q}\n   💬 {a}\n\n"
        try:
            await safe_edit_panel(query, text[:3500], reply_markup=get_tools_menu_keyboard(user_id))
        except Exception:
            pass
        return
    if cmd == 'learning_help':
        help_txt = (
            "🧠 راهنمای یادگیری\n\n"
            "• دستور: `یادگیری سلام`\n"
            "  بعد جواب را بفرستید مثلاً: علیک سلام\n"
            "• هر کسی در گروه یا پیوی «سلام» بگوید، جواب شما ارسال می‌شود\n"
            "• `یادگیری روشن` / `یادگیری خاموش`\n"
            "• `یادگیری لیست` — لیست پاسخ‌ها\n"
            "• `یادگیری حذف سلام` — حذف یک مورد"
        )
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_tools_menu_keyboard(user_id))
        except Exception:
            pass
        return


    if cmd == 'bio_help':
        help_txt = (
            "📖 راهنمای کامل بیو\n\n"
            "هر گزینه روشن = نمایش در بیو؛ خاموش = حذف.\n\n"
            "`ساعت در بیو` / `ساعت در بیو ۲`\n"
            "`بیو تاریخ` / `بیو کامل` / `بیو عاشقانه`\n"
            "`بیو ایموجی` / `بیو فصل` / `بیو روز هفته`\n"
            "`بیو شمارش معکوس` / `بیو متن دلخواه`\n\n"
            "دستور: `ساعت در بیو روشن` یا `ساعت در بیو خاموش`"
        )
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_bio_menu_keyboard(user_id))
        except Exception:
            pass
        return

    if cmd == 'reset_db':
        try:
            uid = user_id
            conn = sqlite3.connect(db.db_name)
            cur = conn.cursor()
            for t in ('bot_answers', 'monshi_status', 'monshi_sent', 'user_bio'):
                try:
                    cur.execute(f'DELETE FROM {t} WHERE user_id = ?', (uid,))
                except Exception:
                    pass
            for t in ('enemies', 'enemy_spam_messages', 'filter_words', 'reactions'):
                try:
                    cur.execute(f'DELETE FROM {t} WHERE owner_id = ? OR user_id = ?', (uid, uid))
                except Exception:
                    pass
            conn.commit()
            conn.close()
            try:
                await query.answer("✅ دیتابیس شما ریست شد", show_alert=True)
            except Exception:
                pass
            try:
                await refresh_panel_keyboard(query, user_id, "🛠 ابزارها", get_tools_menu_keyboard)
            except Exception:
                pass
        except Exception as e:
            try:
                await query.answer(f"خطا: {e}", show_alert=True)
            except Exception:
                pass
        return

    if cmd == 'backup_on':
        db.set_backup_enabled(user_id, True)
        manager.backup_enabled = True
        try:
            await refresh_panel_keyboard(query, user_id, "📦 بکاپ", get_backup_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'backup_off':
        db.set_backup_enabled(user_id, False)
        manager.backup_enabled = False
        try:
            await refresh_panel_keyboard(query, user_id, "📦 بکاپ", get_backup_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'backup_help':
        help_txt = (
            "📦 راهنمای بکاپ‌گیری\n\n"
            "• `بکاپ روشن` / `بکاپ خاموش`\n"
            "• `بکاپ -1002784754810 10 فیلم`\n"
            "• `بکاپ -100xxx 10 عکس`\n"
            "• `بکاپ -100xxx 50 متن`\n"
            "• `بکاپ -100xxx 20 لینک`\n"
            "• `بکاپ -100xxx 100 همه`\n"
            "• `بکاپ @username 5 همه` — پیوی\n"
            "• `بکاپ 123456789 10 همه` — با ایدی\n\n"
            "همه موارد به گروه گزارش ارسال می‌شوند.\n"
            "برای کانال‌های قفل‌شده باید عضو/ادمین باشید."
        )
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_backup_menu_keyboard(user_id))
        except Exception:
            pass
        return

    if cmd == 'add_answer':
        await msg.edit_text("📝 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nافزودن پاسخ سوال:جواب")
        return
    if cmd == 'remove_answer':
        await msg.edit_text("🗑️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nحذف پاسخ سوال")
        return
    if cmd == 'list_answers':
        answers = db.get_answers(user_id)
        if answers:
            text = "📋 لیست پاسخ‌ها:\n\n"
            for i, (q, a) in enumerate(answers.items(), 1):
                text += f"{i}. ❓ {q}\n   💬 {a}\n\n"
            if len(text) > 3500:
                text = text[:3500] + "\n..."
        else:
            text = "❌ هیچ پاسخی ذخیره نشده"
        try:
            await safe_edit_panel(query, text, reply_markup=get_monshi_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
            except Exception:
                pass
        return
    if cmd == 'clear_answers':
        try:
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bot_answers WHERE user_id = ?', (str(user_id),))
            cursor.execute('DELETE FROM bot_answers WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f'clear_answers: {e}')
        try:
            await safe_edit_panel(query, "✅ همه پاسخ‌ها پاک شدند", reply_markup=get_monshi_menu_keyboard(user_id))
        except Exception:
            try:
                await msg.edit_text("✅ همه پاسخ‌ها پاک شدند")
            except Exception:
                pass
        return
    
    if cmd == 'mention_all':
        await msg.edit_text("🏷️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nتگ همه [متن اختیاری]")
        return
    if cmd == 'cancel_mention':
        if query.message.chat_id in manager.mentioning_groups:
            manager.mentioning_groups.discard(query.message.chat_id)
            await msg.edit_text("✅ تگ کردن لغو شد")
        else:
            await msg.edit_text("❌ هیچ تگی در این گروه فعال نیست")
        return
    
    if cmd == 'bowling':
        await msg.edit_text("🎳 در حال بازی بولینگ...")
        asyncio.create_task(manager.force_dice_in_background(query.message.chat_id, "🎳", 6, msg))
        await msg.delete()
        return
    
    if cmd == 'casino_dice':
        await msg.edit_text("🎲 لطفاً عدد ۱ تا ۶ را ارسال کنید (مثال: تاس 5)")
        return
    
    if cmd == 'three_colors':
        colors = ['🔴', '🟢', '🔵']
        seed = user_id
        random.seed(seed)
        user_choice = random.choice(colors)
        random.seed(seed + 100)
        system_choice = random.choice(colors)
        text = f"🎨 **بازی سه رنگ**\n\nرنگ شما: {user_choice}\nرنگ سیستم: {system_choice}\n\n"
        text += "🎉 **برنده شدی!**" if user_choice == system_choice else "😢 **باختی!**"
        await msg.edit_text(text)
        return
    
    if cmd == 'account_age':
        try:
            try:
                await manager.client(UnblockRequest(id="creationdatebot"))
            except Exception:
                pass
            await manager.client.send_message("creationdatebot", "/start")
            await asyncio.sleep(3.5)
            found = None
            async for m in manager.client.iter_messages("creationdatebot", limit=5):
                if m and m.text and len(m.text) > 5:
                    found = m.text
                    break
            if found:
                await msg.edit_text(f"📅 تاریخ ساخت اکانت:\n{found}")
            else:
                await msg.edit_text("❌ پاسخی دریافت نشد. دوباره تلاش کنید.")
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'active_sessions':
        try:
            sessions = await manager.client(GetAuthorizationsRequest())
            auths = list(getattr(sessions, 'authorizations', None) or [])
            if not auths:
                text = "📱 هیچ نشستی یافت نشد"
            else:
                text = "📱 نشست‌های فعال:\n\n"
                for i, session in enumerate(auths, 1):
                    model = getattr(session, 'device_model', None) or getattr(session, 'app_name', None) or 'نامشخص'
                    country = getattr(session, 'country', '') or '—'
                    ip = getattr(session, 'ip', '') or '—'
                    platform = getattr(session, 'platform', '') or '—'
                    app = getattr(session, 'app_name', '') or ''
                    da = getattr(session, 'date_active', None) or getattr(session, 'date_created', None)
                    try:
                        ts = int(da.timestamp()) if hasattr(da, 'timestamp') else int(da)
                        date_s = datetime.fromtimestamp(ts).strftime('%Y/%m/%d %H:%M')
                    except Exception:
                        date_s = str(da)
                    text += f"{i}. {model} {app}\n   📍 {country} | {ip}\n   📅 {date_s}\n   📱 {platform}\n\n"
            try:
                await msg.edit_text(text[:4000])
            except Exception:
                await context.bot.send_message(chat_id=chat_id or user_id, text=text[:4000])
        except Exception as e:
            err = f"❌ خطا در نشست‌ها: {e}"
            try:
                await msg.edit_text(err)
            except Exception:
                try:
                    await context.bot.send_message(chat_id=chat_id or user_id, text=err)
                except Exception:
                    pass
        return

    if cmd == 'system_info':
        try:
            svmem = psutil.virtual_memory()
            cpufreq = psutil.cpu_freq()
            def sizeof_fmt(num):
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if abs(num) < 1024.0:
                        return f"{num:.1f} {unit}"
                    num /= 1024.0
                return f"{num:.1f} PB"
            text = "🖥️ **اطلاعات سیستم:**\n\n"
            text += f"💻 سیستم: {__import__('platform').uname().system}\n"
            text += f"🐍 پایتون: {python_version()}\n"
            text += f"🧠 RAM: {sizeof_fmt(svmem.used)}/{sizeof_fmt(svmem.total)} ({svmem.percent}%)\n"
            text += f"⚡ CPU: {psutil.cpu_percent()}%\n"
            text += f"🔄 هسته‌ها: {psutil.cpu_count()}\n"
            text += f"📶 فرکانس: {cpufreq.current:.0f}MHz"
            await msg.edit_text(text)
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'crypto_price':
        await msg.edit_text("💰 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nقیمت ارز [نماد]\nمثال: قیمت ارز BTC")
        return
    
    if cmd == 'global_currency':
        try:
            url = "https://api.exchangerate-api.com/v4/latest/USD"
            response = requests.get(url, timeout=10)
            data = response.json()
            currencies = {
                'USD': 'دلار', 'EUR': 'یورو', 'GBP': 'پوند',
                'AED': 'درهم', 'TRY': 'لیر', 'CHF': 'فرانک', 'CNY': 'یوان'
            }
            text = "💵 **نرخ ارزهای جهانی (هر ۱۰۰۰ واحد):**\n\n"
            for code, name in currencies.items():
                if code in data['rates']:
                    rate = (1 / data['rates'][code]) * 1000
                    text += f"{name}: {rate:,.0f} تومان\n"
            await msg.edit_text(text)
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'ocr':
        await msg.edit_text("🔍 لطفاً روی یک عکس ریپلای کنید و دستور تشخیص متن را ارسال کنید")
        return
    
    if cmd == 'sticker_text':
        await msg.edit_text("🎨 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nاستیکر متن [متن]")
        return
    
    if cmd == 'numeric_id_help':
        help_txt = (
            "🔢 ایدی عددی و باز کردن پیوی\n\n"
            "• دستور: `پیوی 123456789`\n"
            "  → اطلاعات کاربر + لینک کلیک‌خور به پیوی\n\n"
            "• در گزارش حذف پیام، روی اسم کاربر بزن تا پیوی باز شود\n"
            "  (حتی اگر یوزرنیم نداشته باشد)\n\n"
            "• مثال:\n`پیوی 52626727`"
        )
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_tools_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=help_txt, parse_mode='Markdown')
            except Exception:
                pass
        return

    if cmd == 'make_sticker':
        await msg.edit_text("🎨 ساخت استیکر:\n\nروی پیام کاربر ریپلای کنید و بنویسید:\n`ساخت استیکر`\n\nاستیکر نقل‌قول از @QuotLyBot بدون فوروارد و بدون متن ارسال می‌شود و چت با ربات پاک می‌شود.")
        return
    
    if cmd == 'screenshot':
        try:
            await manager.client.send(
                types.SendScreenshotNotification(
                    peer=await manager.client.resolve_peer(query.message.chat_id),
                    reply_to_msg_id=0,
                    random_id=manager.client.rnd_id(),
                )
            )
            await msg.edit_text("✅ اسکرین‌شات شبیه‌سازی شد")
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'calendar':
        await manager.handle_calendar_command(query.message)
        await msg.delete()
        return
    
    if cmd == 'stats':
        await msg.edit_text("📊 در حال دریافت آمار گفتگو...")
        target_user_id = None
        if query.message.reply_to_message:
            target_user_id = query.message.reply_to_message.from_user.id
        if not target_user_id and query.message.chat.type == 'private':
            target_user_id = query.message.chat.id
        if not target_user_id:
            await msg.edit_text("⚠️ لطفاً روی پیام کاربر ریپلای کنید یا در پی‌وی از این دستور استفاده کنید")
            return
        stats = await manager.get_chat_stats(query.message.chat_id, target_user_id)
        if not stats:
            await msg.edit_text("⚠️ خطا در دریافت آمار")
            return
        try:
            target_name = await manager.get_user_info(target_user_id)
            my_name = await manager.get_user_info(manager.my_id)
            total_my = stats['my_messages']
            total_target = stats['target_messages']
            if total_my > total_target:
                winner = my_name
            elif total_target > total_my:
                winner = target_name
            else:
                winner = "مساوی"
            if total_target > 0:
                ratio = f"{total_my} به {total_target}"
            else:
                ratio = f"{total_my} به 0"
            stats_text = f"""
ꕀꔚꨄꕣꕥ✺ღდ
📊 آمار گفتگو
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
نوع                {my_name[:10]}        {target_name[:10]}
────────────────────────────────────
💬 پیام            {total_my:>5}        {total_target:>5}
📸 عکس             {stats['my_photos']:>5}        {stats['target_photos']:>5}
🎙️ ویس             {stats['my_voices']:>5}        {stats['target_voices']:>5}
🎬 ویدیو           {stats['my_videos']:>5}        {stats['target_videos']:>5}
🎨 استیکر          {stats['my_stickers']:>5}        {stats['target_stickers']:>5}
🎞️ گیف             {stats['my_gifs']:>5}        {stats['target_gifs']:>5}
📁 فایل            {stats['my_files']:>5}        {stats['target_files']:>5}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 بیشترین پیام: {winner}
📈 نسبت: {ratio}
ꕀꔚꨄꕣꕥ✺ღდ
            """
            await manager.client.send_message(query.message.chat_id, stats_text)
            await msg.delete()
        except Exception as e:
            await msg.edit_text(f"⚠️ خطا: {str(e)[:100]}")
        return
    
    if cmd == 'qr':
        await msg.edit_text("🝰 در حال تولید کد QR...")
        try:
            if query.message.reply_to_message:
                reply_msg = await manager.client.get_messages(query.message.chat_id, ids=query.message.reply_to_message.message_id)
                if reply_msg.text:
                    qr_path, text = await manager.generate_qr_code(reply_msg.text)
                elif reply_msg.photo:
                    qr_path, text = await manager.generate_qr_code(reply_msg.media, is_photo=True)
                else:
                    await msg.edit_text("⚠️ لطفاً روی یک پیام متنی یا عکس ریپلای کنید")
                    return
            else:
                await msg.edit_text("🝰 لطفاً متنی که می‌خواهید به کد QR تبدیل شود را وارد کنید")
                return
            if qr_path and os.path.exists(qr_path):
                await manager.client.send_file(query.message.chat_id, qr_path, caption=f"🝰 کد QR\n📝 متن: {text[:100]}{'...' if len(text) > 100 else ''}")
                os.remove(qr_path)
                await msg.delete()
            else:
                await msg.edit_text(f"⚠️ خطا در تولید کد QR: {text}")
        except Exception as e:
            await msg.edit_text(f"⚠️ خطا: {str(e)[:100]}")
        return
    
    if cmd == 'tag_admin':
        if not isinstance(query.message.chat, (types.Channel, types.Chat)):
            await msg.edit_text("⚠️ این دستور فقط در گروه کار می‌کند")
            return
        admins = await manager.get_admins(query.message.chat_id)
        if admins:
            admin_text = "👑 ادمین‌های گروه:\n\n"
            for admin in admins:
                mention = f"@{admin.username}" if admin.username else f"[{admin.first_name or 'ادمین'}](tg://user?id={admin.id})"
                admin_text += f"• {mention}\n"
            await msg.edit_text(admin_text, parse_mode='markdown')
        else:
            await msg.edit_text("⚠️ ادمینی یافت نشد")
        return
    
    if cmd == 'pin':
        if query.message.reply_to_message:
            reply_msg = await manager.client.get_messages(query.message.chat_id, ids=query.message.reply_to_message.message_id)
            if await manager.pin_message(query.message.chat_id, reply_msg.id):
                await msg.edit_text("📌 پیام پین شد")
            else:
                await msg.edit_text("⚠️ خطا در پین کردن پیام")
        else:
            await msg.edit_text("⚠️ روی پیام مورد نظر ریپلای کنید")
        return
    
    if cmd == 'self_on':
        db.update_selfbot_setting(user_id, 'selfbot_enabled', 1)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🛠 ابزارها", get_tools_menu_keyboard)
        except Exception:
            pass
        return
    
    if cmd == 'self_off':
        db.update_selfbot_setting(user_id, 'selfbot_enabled', 0)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🛠 ابزارها", get_tools_menu_keyboard)
        except Exception:
            pass
        return
    
    if cmd.startswith('time_on'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.update_profile_name()
        try:
            await msg.delete()
        except Exception:
            pass
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل", get_time_menu_keyboard)
        return
    if cmd.startswith('time_flag'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 1)
        await manager.update_profile_name()
        try:
            await msg.delete()
        except Exception:
            pass
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل", get_time_menu_keyboard)
        return
    if cmd.startswith('time_off'):
        db.update_selfbot_setting(user_id, 'time_enabled', 0)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.restore_profile_name()
        try:
            await msg.delete()
        except Exception:
            pass
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل", get_time_menu_keyboard)
        return
    
    # ========== فونت تایم ==========
    async def _refresh_font_kb():
        kb = get_font_menu_keyboard(user_id)
        try:
            await query.edit_message_reply_markup(reply_markup=kb)
            return
        except Exception:
            pass
        try:
            await safe_edit_panel(query, "› انتخاب فونت تایم", reply_markup=kb)
        except Exception as e:
            print(f"refresh font: {e}")

    if cmd == 'font_all':
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = 'all'
        await _refresh_font_kb()
        return
    if cmd == 'font_clear':
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = 'all'
        await _refresh_font_kb()
        return
    if cmd.startswith('font_sel_'):
        try:
            idx = int(cmd.split('_')[2])
        except Exception:
            return
        settings = db.get_selfbot_settings(user_id)
        current = settings.get('time_font_indices', 'all')
        if current == 'all':
            new_list = [idx]
        else:
            new_list = [int(x) for x in current] if isinstance(current, list) else []
            if idx in new_list:
                new_list.remove(idx)
            else:
                new_list.append(idx)
            new_list = sorted(set(new_list))
        if not new_list:
            val = 'all'
            new_list = 'all'
        else:
            val = ','.join(map(str, new_list))
        db.update_selfbot_setting(user_id, 'time_font_indices', val)
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = new_list
        await _refresh_font_kb()
        return
    
    # ========== پرچم ==========
    async def _refresh_flag_kb():
        kb = get_flag_menu_keyboard(user_id)
        try:
            await query.edit_message_reply_markup(reply_markup=kb)
            return
        except Exception:
            pass
        try:
            await safe_edit_panel(query, "› انتخاب پرچم", reply_markup=kb)
        except Exception as e:
            print(f"refresh flag: {e}")

    if cmd == 'flag_all':
        db.update_selfbot_setting(user_id, 'selected_flags', 'all')
        await _refresh_flag_kb()
        return
    if cmd == 'flag_clear':
        db.update_selfbot_setting(user_id, 'selected_flags', 'all')
        await _refresh_flag_kb()
        return
    if cmd.startswith('flag_sel_'):
        try:
            idx = int(cmd.split('_')[2])
            fl = flags[idx]
        except Exception:
            return
        settings = db.get_selfbot_settings(user_id)
        current = settings.get('selected_flags', 'all')
        if current == 'all':
            new_list = [fl]
        else:
            new_list = list(current) if isinstance(current, list) else []
            if fl in new_list:
                new_list.remove(fl)
            else:
                new_list.append(fl)
        if not new_list:
            val = 'all'
            new_list = 'all'
        else:
            val = ','.join(new_list)
        db.update_selfbot_setting(user_id, 'selected_flags', val)
        await _refresh_flag_kb()
        return
    
    # ========== راهنمای قفل رسانه ==========
    if cmd == 'lock_help':
        help_text = """📖 **راهنمای کامل قفل رسانه**

این بخش برای محدود کردن ارسال انواع رسانه در پی‌وی یا گروه است.

🔹 **نحوه استفاده:**
• روی پیام کاربر ریپلای کنید و سپس دکمه قفل مورد نظر را بزنید → فقط برای همان کاربر قفل می‌شود.
• اگر در پی‌وی بدون ریپلای بزنید → برای همان چت اعمال می‌شود.
• قفل‌ها قابل روشن/خاموش هستند (دوباره زدن = غیرفعال).

📋 **لیست قفل‌ها و کاربرد:**

🔗 **قفل لینک** — پیام‌های حاوی لینک (http/t.me/www و دامنه) حذف یا مسدود می‌شوند.
📸 **قفل عکس** — ارسال عکس مسدود می‌شود.
🎥 **قفل ویدیو** — ارسال ویدیو مسدود می‌شود.
🎨 **قفل استیکر** — ارسال استیکر مسدود می‌شود.
🎞️ **قفل گیف** — ارسال گیف/انیمیشن مسدود می‌شود.
🎤 **قفل ویس** — ارسال ویس/صدا مسدود می‌شود.
📁 **قفل فایل** — ارسال فایل/سند مسدود می‌شود.
🎵 **قفل موزیک** — ارسال موزیک/آهنگ مسدود می‌شود.
📹 **قفل ویدیو نوت** — ارسال ویدیو نوت (دایره‌ای) مسدود می‌شود.
📞 **قفل کانتکت** — ارسال مخاطب/شماره مسدود می‌شود.
📍 **قفل لوکیشن** — ارسال موقعیت مکانی مسدود می‌شود.
😀 **قفل ایموجی** — پیام‌هایی که فقط از ایموجی تشکیل شده‌اند مسدود می‌شوند.
📝 **قفل متن** — ارسال پیام متنی ساده مسدود می‌شود.

⚠️ **نکته:** قفل‌ها فقط روی پیام‌های ورودی دیگران اعمال می‌شوند و روی پیام‌های خود شما تأثیری ندارند. برای قفل کلی پی‌وی از بخش «مدیریت کاربران» استفاده کنید."""
        try:
            await query.edit_message_text(
                help_text,
                reply_markup=get_help_back_keyboard(user_id, f"lock_menu_{user_id}")
            )
        except Exception:
            await msg.edit_text(help_text, reply_markup=get_help_back_keyboard(user_id, f"lock_menu_{user_id}"))
        try:
            await msg.delete()
        except Exception:
            pass
        return
    

    # ========== راهنماهای بخش‌ها ==========
    HELP_TEXTS = {
        'google_help': """📖 راهنمای گوگل و آهنگ

› 🔍 سرچ — حالت جستجوی گوگل را روشن می‌کند. بعد از روشن شدن، هر متنی بفرستید جستجو می‌شود.
› ❌ خروج جستجو — حالت سرچ را خاموش می‌کند.
› 🎵 آهنگ — برای پخش آهنگ از دستور `.اهنگ [نام]` استفاده کنید.

مثال: `.اهنگ شادمهر`""",
        'time_help': """📖 راهنمای زمان و پروفایل

› 🕐 تایم روشن — ساعت را در اسم پروفایل نمایش می‌دهد.
› 🏳️ تایمر پرچم — علاوه بر ساعت، پرچم هم در اسم می‌چرخد.
› 🚫 تایم خاموش — نمایش ساعت/پرچم را قطع می‌کند.
› 📅 تقویم — تاریخ شمسی و میلادی را نشان می‌دهد.
› 🔤 انتخاب فونت تایم — فونت‌های ساعت را انتخاب کنید (چندتایی با تیک).
› 🏳️ انتخاب پرچم — پرچم‌های مورد نظر را برای چرخش انتخاب کنید.
› 📝 تنظیمات بیو — ساعت/تاریخ/فصل و ... را در بیو قرار دهید.""",
        'animation_help': """📖 راهنمای انیمیشن

› ❤️ قلب — انیمیشن ساده قلب
› 🌙 ماه — انیمیشن ماه
› 💖 قلب پیشرفته — انیمیشن چندمرحله‌ای قلب
› 💝 عشق — انیمیشن I Love You
› 🕯️ سنتت — نوار پیشرفت تقلبی
› 💻 هک — انیمیشن هک تقلبی
› 🎨 استیکر متن — ساخت استیکر از متن با دستور `استیکر متن [متن]`""",
        'user_help': """📖 راهنمای مدیریت کاربران

› 🥷 دشمن — ریپلای در پیوی: هر پیام دشمن با یک اسپم جواب داده می‌شود (پیام پاک نمی‌شود).
› 🧸 دوست — پایان دشمن پیوی.
› 👥 دشمن گروه — ریپلای در گروه: فقط در گروه روی همان کاربر اسپم ریپلای می‌شود.
› 🧸 دوست گروه — پایان دشمن گروه.
› 🔒 قفل پیوی — پیام‌های آن کاربر در پی‌وی حذف می‌شود.
› 🔓 باز پی — قفل پی‌وی را برمی‌دارد.
› 🔒 قفل پیوی همه — همه پی‌وی‌ها قفل می‌شوند.
› 🔓 باز پی همه — قفل همگانی برداشته می‌شود.
› ⛔ بلاک — کاربر را بلاک می‌کند (با ریپلای).""",
        'comment_help': """📖 راهنمای کامنت خودکار

› 💬 کامنت [متن] — برای کانال فعلی متن کامنت خودکار تنظیم می‌کند.
› 📊 کانال‌ها — لیست کانال‌های تنظیم‌شده را نشان می‌دهد.
› 🗑️ حذف کانال — تنظیمات کانال فعلی را حذف می‌کند.
› 🔍 تست کانال — وضعیت تنظیمات کانال فعلی را چک می‌کند.

نکته: در کانال/گروه مرتبط دستور `کامنت متن شما` را بزنید.""",
        'general_help': """📖 راهنمای عمومی

› 📊 وضعیت — وضعیت فعلی سلف‌بات و تنظیمات.
› ℹ️ درباره — نسخه و سازنده.
› ⏱️ پینگ — تأخیر پاسخ ربات.
› 👤 پنل کاربر — روی پیام هر کاربر ریپلای کنید و بنویسید: پنل کاربر
  عکس پروفایل + اطلاعات + دکمه‌های قفل/دشمن برای همان کاربر می‌آید.
  (در گروه و پیوی کار می‌کند)""",
        'action_help': """📖 راهنمای اکشن

دستورات متنی (کپی کنید):

`اکشن تایپ`
`اکشن ویس`
`اکشن ویدیو`
`اکشن عکس`
`اکشن فیلم`
`اکشن فایل`
`اکشن بازی`
`اکشن استیکر`
`اکشن موقعیت`
`اکشن تماس`
`اکشن صحبت`
`اکشن خاموش`
`اکشن لیست`

در همان چت (گروه یا پیوی) اجرا می‌شود.""",
        'games_help': """📖 راهنمای بازی‌ها

› 🎲 تاس ۱ تا ۶ — تاس می‌اندازد تا عدد هدف بیاید.
› 🎯 دارت — تا ۶ بیاید.
› 🏀 بسکتبال — تا ۵ بیاید.
› ⚽️ فوتبال — تا ۵ بیاید.
› 🎳 بولینگ — تا ۶ بیاید.
› 🎨 سه رنگ — بازی شانسی رنگ.
› دستور متنی: `شانس [عدد]` و `تاس [عدد]`""",
        'translate_help': """📖 راهنمای ترجمه

۱) پنل اصلی:
زبان را روشن کنید → همه پیام‌های خروجی شما ترجمه می‌شوند.

۲) پنل کاربر:
زبان را برای همان کاربر روشن کنید → فقط در پیوی او ترجمه می‌شود.

۳) ریپلای:

`ترجمه`
ترجمه به فارسی

`ترجمه به زبان روسی`
`ترجمه به زبان انگلیسی`

متن‌های بلند هم تکیه‌تکه ترجمه می‌شوند.""",
        'info_help': """📖 راهنمای اطلاعاتی

روی دستورها بزنید تا کپی شوند:

`اطلاعات`
اطلاعات کاربر (ریپلای)

`دانلود پروفایل`
عکس پروفایل (ریپلای)

`تاریخ ساخت اکانت`
تاریخ ساخت اکانت تلگرام

`نشست‌های فعال`
لیست دستگاه‌های لاگین

`اطلاعات سیستم`
RAM و CPU سرور

`تشخیص متن`
OCR روی عکس (ریپلای)

---
توجه: ایدی کاربران دارای سلف فعال نمایش داده نمی‌شود.""",
        'profile_help': """📖 راهنمای پروفایل

› 📸 ست پروف — عکس ریپلای‌شده را پروفایل می‌کند.
› ✏️ ست بیو — متن ریپلای را بیو می‌کند.
› 🗑️ حذف ست پروف / بیو — پروفایل یا بیو را پاک می‌کند.""",
        'style_help': """📖 راهنمای استایل متن

با فعال کردن هر استایل، پیام‌های خروجی شما با آن فرمت ارسال می‌شوند:
› بولد، زیرخط، خط خورده، نقل قول، اسپویلر، کج، کد، پیش

› دوباره زدن همان دکمه = خاموش.""",
        'message_help': """📖 راهنمای مدیریت پیام

› 🧹 حذف کامل — همه پیام‌های شما در چت.
› 🧹 حذف کامل ۵۰ — ۵۰ پیام آخر شما.
› 🗑️ حذف ۱۰ — ۱۰ پیام آخر.
› 👁️ فعال اتوسین — پیام‌های دریافتی خودکار سین می‌شوند.
› 🙈 غیرفعال اتوسین
› 📸 اسکرین‌شات — نوتیفیکیشن اسکرین‌شات شبیه‌سازی.""",
        'reaction_help': """📖 راهنمای ریکشن

› 👍 ریکت — با ریپلای روی پیام کاربر + دستور `ریکت 🔥` ریکت خودکار تنظیم می‌شود.
› در گروه و پی‌وی کار می‌کند.
› ❌ حذف ریکت — با ریپلای، ریکت آن کاربر را حذف می‌کند.

› ایموجی‌های مجاز در لیست ALLOWED_EMOJIS هستند.""",
        'spam_help': """📖 راهنمای اسپم

› 📩 اسپم — دستور: `اسپم [تعداد] [متن]`
مثال: `اسپم 5 سلام`

› برای دشمنان از بخش مدیریت دشمنان استفاده کنید.""",
        'change_help': """📖 راهنمای تغییر پروفایل

› ✏️ تغییر اسم [نام] — اسم پروفایل را عوض می‌کند.
› ✏️ تغییر بیو [متن] — بیو را عوض می‌کند.
› 📸 تغییر پروفایل / پروف — با ریپلای روی عکس.""",
        'enemy_help': """📖 راهنمای دشمنان

› 📋 لیست دشمن — دشمنان پیوی/گروه.
› 📝 اضافه اسپم — متن‌های اسپم دشمن.
› ⚠️ دشمن پیوی پیام را پاک نمی‌کند؛ فقط یک اسپم به ازای هر پیام می‌فرستد.
› ✅ اتمام اسپم — خروج از حالت افزودن.
› 📜 لیست اسپم — متن‌های اسپم ذخیره‌شده.
› 🗑️ پاک کردن / حذف اسپم — مدیریت لیست اسپم.""",
        'pclock_help': """📖 راهنمای ساعت روی پروفایل

› روشن: بکاپ عکس فعلی + ساعت نئون روی عکس پروفایل
› هر دقیقه عکس با دقیقهٔ جدید جایگزین می‌شود
› خاموش: برگرداندن عکس قبلی
› رنگ: فیروزه‌ای / سبز / بنفش / صورتی / نارنجی / قرمز / آبی / سفید

دستورات:
• ساعت روشن
• ساعت خاموش
• ساعت رنگ سبز""",
        'filter_help': """📖 راهنمای فیلتر کلمات

› افزودن کلمه:
  • `.فیلتر تبلیغ`
  • `فیلتر تبلیغ`

› فعال‌سازی:
  • `فیلتر روشن` — هر پیام حاوی کلمهٔ فعال حذف می‌شود
  • `فیلتر خاموش`

› مدیریت:
  • `فیلتر لیست` — نمایش کلمات
  • `فیلتر حذف [کلمه]`

› از پنل هم می‌توانید هر کلمه را تکی روشن/خاموش یا حذف کنید.
› روی کپشن عکس/ویدیو هم اعمال می‌شود (در صورت داشتن دسترسی حذف).""",
        'protection_help': """📖 راهنمای حفاظت اسپم

› 🛡️ اسپم روشن/خاموش — محافظت در برابر اسپم دیگران.
› ⚙️ تنظیم اسپم [تعداد] [ثانیه] — محدودیت و زمان میوت.
› 📊 وضعیت اسپم — تنظیمات فعلی.""",
        'ai_help': """📖 راهنمای هوش مصنوعی

پیوی ۱/۲/۳ و گروه ۱/۲/۳:
› ۱ = Gemini
› ۲ = Paxsenix
› ۳ = DeepSeek

با روشن کردن، پیام‌های دریافتی در آن محیط با AI پاسخ داده می‌شوند.
› خاموش پیوی / خاموش گروه همه را قطع می‌کند.""",
        'report_help': """📖 راهنمای گزارش

› 📍 تنظیم گزارش — گروه گزارش را تنظیم می‌کند.
› ℹ️ گروه گزارش — آیدی گروه فعلی را نشان می‌دهد.

› پس از عضویت، یک گروه خصوصی «گزارش دهی» به‌صورت خودکار ساخته و سنجاق می‌شود.
› می‌توانید گروه یا کانال دیگری (مثلاً سیو مسیج) را هم با دستور `تنظیم گزارش` جایگزین کنید.
› پیام‌های حذف‌شده/ویرایش‌شده و مدیا به گروه گزارش ارسال می‌شوند.""",
        'tools_help': """📖 راهنمای ابزار

› 📊 امار گپ — آمار گفتگو با کاربر (ریپلای یا پی‌وی).
› 🝰 کد QR — ساخت QR از متن/عکس (ریپلای).
› 👑 تگ ادمین — منشن ادمین‌های گروه.
› 📌 پین — پین کردن پیام ریپلای‌شده.
› 🤖 سلف روشن/خاموش — فعال/غیرفعال کردن سلف‌بات.
› 🎨 ساخت استیکر — ریپلای روی پیام کاربر + دستور `ساخت استیکر` → استیکر نقل‌قول از @QuotLyBot بدون فوروارد و بدون متن.
› 🎙 ویدیو → ویس — ریپلای روی ویدیو + دستور `ویس` یا `صدا` → استخراج صدا و ارسال به صورت ویس.""",
        'monshi_help': """📖 راهنمای منشی هوشمند

› 🤖 منشی — با دستور `منشی [پاسخ]` فعال می‌شود.
› ⛔ خاموش — منشی را قطع می‌کند.
› 📝 افزودن پاسخ — فرمت: `افزودن پاسخ سوال:جواب`
› 🗑️ حذف پاسخ — `حذف پاسخ سوال`
› 📋 لیست پاسخ‌ها
› 🧹 پاک کردن پاسخ‌ها""",
        'mention_help': """📖 راهنمای تگ همه

› 🏷️ تگ همه [متن] — همه اعضای گروه را ۱۳نفره منشن می‌کند.
› ⛔ لغو تگ — عملیات تگ را متوقف می‌کند.

فقط در گروه کار می‌کند.""",
        'fortune_help': """📖 راهنمای فال

› 🌟 فال عمومی — یک فال تصادفی.
› 🕌 فال حافظ — بیت حافظ.
› ☕ فال قهوه — فال قهوه.""",
    }
    # نقشه بازگشت راهنما به منوی والد
    HELP_BACK = {
        'google_help': f'google_menu_{user_id}',
        'time_help': f'time_menu_{user_id}',
        'pclock_help': f'exec_open_pclock_{user_id}',
        'animation_help': f'animation_menu_{user_id}',
        'user_help': f'user_menu_{user_id}',
        'lock_help': f'lock_menu_{user_id}',
        'comment_help': f'comment_menu_{user_id}',
        'general_help': f'general_menu_{user_id}',
        'action_help': f'action_menu_{user_id}',
        'games_help': f'games_menu_{user_id}',
        'translate_help': f'translate_menu_{user_id}',
        'info_help': f'info_menu_{user_id}',
        'profile_help': f'profile_menu_{user_id}',
        'style_help': f'style_menu_{user_id}',
        'message_help': f'message_menu_{user_id}',
        'reaction_help': f'reaction_menu_{user_id}',
        'spam_help': f'spam_menu_{user_id}',
        'change_help': f'change_menu_{user_id}',
        'enemy_help': f'enemy_menu_{user_id}',
        'filter_help': f'exec_open_filter_{user_id}',
        'protection_help': f'protection_menu_{user_id}',
        'ai_help': f'ai_menu_{user_id}',
        'report_help': f'report_menu_{user_id}',
        'tools_help': f'tools_menu_{user_id}',
        'monshi_help': f'monshi_menu_{user_id}',
        'mention_help': f'mention_menu_{user_id}',
        'fortune_help': f'fortune_menu_{user_id}',
        'crypto_help': f'crypto_menu_{user_id}',
        'bio_help': f'bio_menu_{user_id}',
        'learning_help': f'tools_menu_{user_id}',
        'backup_help': f'backup_menu_{user_id}',
        'numeric_id_help': f'tools_menu_{user_id}',
        'user_panel_help': f'general_menu_{user_id}',
        'lock_help': f'lock_menu_{user_id}',
    }
    if cmd.endswith('_help') or cmd in HELP_TEXTS:
        help_body = HELP_TEXTS.get(cmd) or HELP_TEXTS.get(cmd.replace('_help', '') + '_help') or (
            f"📖 راهنمای {cmd}\n\nدستورات متنی این بخش را از منوی مربوطه و راهنمای پنل ببینید."
        )
        back_cb = HELP_BACK.get(cmd, 'back_main')
        try:
            import html as _html
            quoted = "<blockquote>" + _html.escape(help_body) + "</blockquote>"
            ok = await safe_edit_panel(
                query,
                quoted,
                reply_markup=get_help_back_keyboard(user_id, back_cb),
                parse_mode='HTML'
            )
            if not ok:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id or user_id,
                        text=help_body[:3500],
                        reply_markup=get_help_back_keyboard(user_id, back_cb)
                    )
                except Exception:
                    await query.answer("راهنما", show_alert=False)
        except Exception:
            try:
                await query.edit_message_caption(
                    caption=help_body[:1024],
                    reply_markup=get_help_back_keyboard(user_id, back_cb)
                )
            except Exception:
                await msg.edit_text(help_body, reply_markup=get_help_back_keyboard(user_id, back_cb))
        try:
            await msg.delete()
        except Exception:
            pass
        return

    translate_commands = {
        'translate_en': 'english', 'translate_ar': 'arabic', 'translate_he': 'hebrew',
        'translate_ru': 'russian', 'translate_tr': 'turkish', 'translate_de': 'german',
        'translate_fr': 'french', 'translate_es': 'spanish', 'translate_it': 'italian',
        'translate_zh': 'chinese', 'translate_ja': 'japanese', 'translate_ko': 'korean',
        'translate_hi': 'hindi', 'translate_fa': 'persian',
    }
    for cmd_prefix, lang in translate_commands.items():
        if cmd == cmd_prefix or cmd.startswith(cmd_prefix + '_'):
            manager.translate_mode[lang] = not manager.translate_mode.get(lang, False)
            db.update_selfbot_setting(user_id, f'translate_{lang}', 1 if manager.translate_mode[lang] else 0)
            try:
                await refresh_panel_keyboard(query, user_id, "🌐 ترجمه", get_translate_menu_keyboard)
            except Exception:
                try:
                    await query.edit_message_reply_markup(reply_markup=get_translate_menu_keyboard(user_id))
                except Exception:
                    pass
            return
    
    # advanced_heart / love / santet / hack — در پایین با _anim_target یکجا هندل می‌شوند
    
    if cmd == 'user_panel_help':
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        help_txt = (
            "👤 پنل کاربر\n\n"
            "روی پیام هر کاربر (در گروه یا پیوی) ریپلای کنید و بنویسید:\n"
            "`پنل کاربر`\n\n"
            "سپس عکس پروفایل + اطلاعات + دکمه‌های قفل/دشمن برای همان کاربر می‌آید."
        )
        try:
            await context.bot.send_message(chat_id=chat_id, text=help_txt, parse_mode='Markdown')
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=help_txt.replace('`', ''))
            except Exception:
                pass
        return

    if cmd == 'status':
        settings = db.get_selfbot_settings(user_id)
        await msg.edit_text(manager.format_status_info(settings))
        return
    if cmd == 'about':
        await msg.edit_text(f"ℹ️ درباره بات\n\n🤖 نسخه: v{BOT_VERSION}\n👨‍💻 سازنده: {BOT_CREATOR}")
        return
    if cmd == 'ping':
        start = time.time()
        await msg.edit_text("🏓 پینگ: ...")
        end = time.time()
        ping = round((end - start) * 1000, 2)
        await msg.edit_text(f"› 🏓 پینگ: {ping} ms")
        return
    if cmd == 'music':
        await msg.edit_text("🎵 دستور اهنگ\n\nبرای جستجو و پخش آهنگ از فرمت زیر استفاده کنید:\n\n`.اهنگ [نام آهنگ]`\n\nمثال: `.اهنگ مهدیار احمدی`")
        return
    
    # هدف انیمیشن/اکشن: اگر پنل‌کاربر باز باشد → پیوی همان کاربر، وگرنه همین چت
    _panel_tgt = panel_lock_targets.get(user_id) or panel_lock_targets.get(str(user_id))
    def _anim_target():
        if _panel_tgt:
            return int(_panel_tgt)
        return chat_id or (query.message.chat_id if query.message else user_id)

    if cmd == 'heart':
        target_chat = _anim_target()
        await query.answer(f"❤️ قلب → {target_chat}", show_alert=False)
        asyncio.create_task(manager.heart_animation(target_chat))
        return
    if cmd == 'moon':
        target_chat = _anim_target()
        await query.answer(f"🌙 ماه → {target_chat}", show_alert=False)
        asyncio.create_task(manager.moon_animation(target_chat))
        return
    if cmd in ('advanced_heart', 'love', 'santet', 'hack'):
        target_chat = _anim_target()
        await query.answer(f"✨ {cmd} → {target_chat}", show_alert=False)
        try:
            if cmd == 'advanced_heart':
                m = await manager.client.send_message(target_chat, '❤️')
                await advanced_heart_animation(m)
            elif cmd == 'love':
                m = await manager.client.send_message(target_chat, '💝')
                await advanced_heart_animation(m)
            elif cmd == 'santet':
                santet_msg = await manager.client.send_message(target_chat, '🕯️')
                for i in range(0, 101, 5):
                    bar_len = int(i / 100 * 20)
                    bar = '█' * bar_len + '░' * (20 - bar_len)
                    await santet_msg.edit(f'🕯️ {i}% [{bar}]')
                    await asyncio.sleep(0.05)
                await santet_msg.edit('✅ انجام شد 🥴')
            elif cmd == 'hack':
                hack_msg = await manager.client.send_message(target_chat, '💻')
                for step in [
                    'User online: True\nTelegram access: True',
                    'Hacking... 25%\n[█████░░░░░░░░░░░░░░░]',
                    'Hacking... 50%\n[██████████░░░░░░░░░░]',
                    'Hacking... 75%\n[███████████████░░░░░]',
                    'Hacking... 100%\n[████████████████████]',
                    '✅ هک کامل شد',
                ]:
                    await asyncio.sleep(1.2)
                    await hack_msg.edit(step)
        except Exception as e:
            logger.error(f'anim {cmd}: {e}')
        return

    # اکشن‌های مستقیم از منو (act_تایپ و ...)
    if cmd.startswith('act_'):
        action_name = cmd[4:]  # بعد از act_
        target_chat = _anim_target()
        try:
            ok = await manager.start_action(target_chat, action_name)
            if ok:
                await query.answer(f"✅ اکشن {action_name} → {target_chat}", show_alert=False)
            else:
                await query.answer(f"❌ اکشن نامعتبر: {action_name}", show_alert=True)
        except Exception as e:
            logger.error(f'act_: {e}')
            try:
                await query.answer(f"خطا: {str(e)[:80]}", show_alert=True)
            except Exception:
                pass
        return
    if cmd == 'action_off':
        target_chat = _anim_target()
        try:
            stopped = await manager.stop_action(target_chat)
            await query.answer(f"⏹️ اکشن {stopped or ''} خاموش شد", show_alert=False)
        except Exception as e:
            logger.error(f'action_off: {e}')
        return
    if cmd == 'action_list':
        active = getattr(manager, 'active_actions', {}) or {}
        if active:
            lines = [f"• {cid}: {name}" for cid, name in active.items()]
            txt = "📋 اکشن‌های فعال:\n" + "\n".join(lines)
        else:
            txt = "📭 هیچ اکشنی فعال نیست"
        try:
            await context.bot.send_message(chat_id=user_id, text=txt)
        except Exception:
            pass
        return
    
    if cmd == 'enemy':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و در سلف بنویسید:\nدشمن")
        return
    if cmd == 'friend':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و در سلف بنویسید:\nدوست")
        return
    if cmd == 'enemy_group':
        await msg.edit_text("⚠️ در گروه روی پیام کاربر ریپلای کنید و بنویسید:\nدشمن گروه\n\nهر پیامش با یک اسپم ریپلای می‌شود (پیوی جداست)")
        return
    if cmd == 'friend_group':
        await msg.edit_text("⚠️ در گروه روی پیام کاربر ریپلای کنید و بنویسید:\nدوست گروه")
        return
    if cmd == 'lock_pv':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور قفل پیوی را ارسال کنید")
        return
    if cmd == 'unlock_pv':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور باز پی را ارسال کنید")
        return
    if cmd == 'lock_all':
        db.update_selfbot_setting(user_id, 'pv_lock_all', 1)
        await msg.edit_text("✅ قفل پیوی همگانی فعال شد")
        return
    if cmd == 'unlock_all':
        db.update_selfbot_setting(user_id, 'pv_lock_all', 0)
        await msg.edit_text("✅ قفل پیوی همگانی غیرفعال شد")
        return
    if cmd == 'block':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور بلاک را ارسال کنید")
        return
    
    if cmd == 'enemy_list':
        enemies = db.get_enemies(user_id, 'pv')
        if enemies:
            message = "📋 لیست دشمنان:\n\n"
            for i, enemy_id in enumerate(enemies, 1):
                try:
                    enemy = await manager.client.get_entity(enemy_id)
                    enemy_name = enemy.first_name or f"کاربر {enemy_id}"
                    message += f"{i}. {enemy_name} ({enemy_id})\n"
                except:
                    message += f"{i}. کاربر {enemy_id}\n"
            await msg.edit_text(message)
        else:
            await msg.edit_text("📭 لیست دشمنان خالی است")
        return
    
    if cmd == 'add_spam':
        manager.adding_spam = True
        await msg.edit_text("📝 حالت اضافه کردن اسپم فعال شد\nبرای پایان: اتمام اسپم")
        return
    if cmd == 'end_spam':
        manager.adding_spam = False
        await msg.edit_text("✅ حالت اضافه کردن اسپم غیرفعال شد")
        return
    if cmd == 'spam_list':
        spam_messages = db.get_enemy_spam_messages(user_id)
        if spam_messages:
            message = "📜 لیست پیام‌های اسپم:\n\n"
            for i, spam_msg in enumerate(spam_messages, 1):
                message += f"{i}. {spam_msg['text']}\n"
            message += f"\n📊 تعداد: {len(spam_messages)}"
            await msg.edit_text(message)
        else:
            await msg.edit_text("📭 لیست پیام‌های اسپم خالی است")
        return
    if cmd == 'clear_spam':
        db.clear_enemy_spam_messages(user_id)
        await msg.edit_text("✅ لیست اسپم پاک شد")
        return
    if cmd == 'delete_spam':
        await msg.edit_text("🗑️ حذف اسپم [شماره]")
        return
    
    if cmd == 'filter_word':
        help_txt = (
            "🚫 افزودن کلمه فیلتر\n\n"
            "در چت سلف بنویسید:\n"
            "• `.فیلتر تبلیغ`\n"
            "• `فیلتر تبلیغ`\n\n"
            "سپس:\n"
            "• `فیلتر روشن` — فعال‌سازی حذف خودکار\n"
            "• `فیلتر خاموش`\n"
            "• `فیلتر لیست`\n"
            "• `فیلتر حذف [کلمه]`"
        )
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_filter_menu_keyboard(user_id))
        except Exception:
            try:
                if msg:
                    await msg.edit_text(help_txt)
            except Exception:
                pass
        return
    if cmd == 'filter_on':
        db.set_filter_enabled(user_id, True)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🚫 فیلتر کلمات — روشن شد", get_filter_menu_keyboard)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=get_filter_menu_keyboard(user_id))
            except Exception:
                pass
        return
    if cmd == 'filter_off':
        db.set_filter_enabled(user_id, False)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🚫 فیلتر کلمات — خاموش شد", get_filter_menu_keyboard)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=get_filter_menu_keyboard(user_id))
            except Exception:
                pass
        return
    if cmd == 'filter_list' or cmd == 'filter_remove':
        filters = db.get_filter_words(user_id)
        if filters:
            message_text = "📜 مدیریت کلمات فیلتر شده:\n\nروی کلمه بزنید تا روشن/خاموش شود، روی 🗑️ بزنید تا حذف شود.\n\n"
            try:
                await safe_edit_panel(query, message_text, reply_markup=build_filter_words_keyboard(user_id, filters))
            except Exception:
                try:
                    if msg:
                        await msg.edit_text(message_text, reply_markup=build_filter_words_keyboard(user_id, filters))
                    else:
                        await query.message.edit_text(message_text, reply_markup=build_filter_words_keyboard(user_id, filters))
                except Exception:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=build_filter_words_keyboard(user_id, filters))
                    except Exception:
                        pass
        else:
            empty_txt = "📭 لیست کلمات فیلتر خالی است\n\nبرای افزودن در سلف بنویسید:\n`.فیلتر تبلیغ`"
            try:
                await safe_edit_panel(query, empty_txt, reply_markup=get_filter_menu_keyboard(user_id))
            except Exception:
                try:
                    if msg:
                        await msg.edit_text(empty_txt)
                except Exception:
                    pass
        return
    if cmd.startswith('filtertgl_'):
        try:
            word_id = int(cmd.split('_')[1])
        except (IndexError, ValueError):
            try:
                await query.answer("⚠️ خطا در شناسایی کلمه", show_alert=True)
            except Exception:
                pass
            return
        new_state = db.toggle_filter_word_by_id(user_id, word_id)
        if new_state is None:
            try:
                await query.answer("⚠️ این کلمه دیگر در لیست نیست", show_alert=True)
            except Exception:
                pass
        else:
            try:
                await query.answer("✅ روشن" if new_state else "❌ خاموش")
            except Exception:
                pass
        filters = db.get_filter_words(user_id)
        text = "📜 مدیریت کلمات فیلتر شده:\n\nروی کلمه بزنید تا روشن/خاموش شود، روی 🗑️ بزنید تا حذف شود.\n\n"
        if filters:
            try:
                await safe_edit_panel(query, text, reply_markup=build_filter_words_keyboard(user_id, filters))
            except Exception:
                try:
                    await query.edit_message_reply_markup(reply_markup=build_filter_words_keyboard(user_id, filters))
                except Exception:
                    pass
        else:
            try:
                await safe_edit_panel(query, "📭 لیست خالی است", reply_markup=get_filter_menu_keyboard(user_id))
            except Exception:
                pass
        return
    if cmd.startswith('filterdel_'):
        try:
            word_id = int(cmd.split('_')[1])
        except (IndexError, ValueError):
            try:
                await query.answer("⚠️ خطا", show_alert=True)
            except Exception:
                pass
            return
        removed = db.remove_filter_word_by_id(user_id, word_id)
        try:
            await query.answer("🗑️ حذف شد" if removed else "یافت نشد")
        except Exception:
            pass
        filters = db.get_filter_words(user_id)
        if filters:
            text = "📜 مدیریت کلمات فیلتر شده:\n\nروی کلمه بزنید تا روشن/خاموش شود، روی 🗑️ بزنید تا حذف شود.\n\n"
            try:
                await safe_edit_panel(query, text, reply_markup=build_filter_words_keyboard(user_id, filters))
            except Exception:
                try:
                    await query.edit_message_reply_markup(reply_markup=build_filter_words_keyboard(user_id, filters))
                except Exception:
                    pass
        else:
            try:
                await safe_edit_panel(query, "📭 لیست کلمات فیلتر خالی است\n\n`.فیلتر [کلمه]`", reply_markup=get_filter_menu_keyboard(user_id))
            except Exception:
                pass
        return

    # ——— ساعت روی پروفایل ———
    if cmd == 'pclock_on':
        db.update_selfbot_setting(user_id, 'profile_clock_enabled', 1)
        try:
            await manager._backup_current_profile_photo()
            ok = await manager.update_profile_clock(force=True)
            await query.answer("✅ ساعت پروفایل روشن شد" if ok else "⚠️ روشن شد (آپلود ممکن است تأخیر داشته باشد)")
        except Exception as e:
            try:
                await query.answer(f"خطا: {str(e)[:40]}", show_alert=True)
            except Exception:
                pass
        try:
            await refresh_panel_keyboard(query, user_id, "🕰 ساعت در پروفایل", get_profile_clock_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'pclock_off':
        try:
            await manager.restore_profile_clock()
            await query.answer("✅ ساعت خاموش — پروفایل قبلی برگشت")
        except Exception as e:
            try:
                await query.answer(f"خطا: {str(e)[:40]}", show_alert=True)
            except Exception:
                pass
        try:
            await refresh_panel_keyboard(query, user_id, "🕰 ساعت در پروفایل", get_profile_clock_menu_keyboard)
        except Exception:
            pass
        return
    if cmd.startswith('pclock_color_'):
        color = cmd.replace('pclock_color_', '', 1)
        if color not in PROFILE_CLOCK_COLORS:
            try:
                await query.answer("رنگ نامعتبر", show_alert=True)
            except Exception:
                pass
            return
        db.update_selfbot_setting(user_id, 'profile_clock_color', color)
        if db.get_selfbot_settings(user_id).get('profile_clock_enabled'):
            try:
                await manager.update_profile_clock(force=True)
            except Exception:
                pass
        try:
            await query.answer(f"✅ رنگ: {color}")
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🕰 ساعت در پروفایل", get_profile_clock_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'pclock_refresh':
        try:
            ok = await manager.update_profile_clock(force=True)
            await query.answer("✅ بروزرسانی شد" if ok else "❌ خطا در بروزرسانی", show_alert=not ok)
        except Exception as e:
            try:
                await query.answer(str(e)[:50], show_alert=True)
            except Exception:
                pass
        return
    if cmd == 'pclock_noop':
        try:
            await query.answer("یک رنگ انتخاب کنید")
        except Exception:
            pass
        return
    if cmd == 'pclock_help':
        help_txt = (
            "🕰 راهنمای ساعت روی پروفایل\n\n"
            "• روشن: عکس پروفایل شما بکاپ می‌شود و ساعت سایبرپانک روی همان عکس می‌نشیند.\n"
            "• هر دقیقه عکس جدید با دقیقهٔ فعلی جایگزین می‌شود.\n"
            "• خاموش: عکس قبلی (قبل از روشن شدن) برمی‌گردد.\n"
            "• رنگ: فیروزه‌ای / سبز / بنفش / صورتی / نارنجی / قرمز / آبی / سفید\n\n"
            "دستورات متنی:\n"
            "`ساعت روشن`\n"
            "`ساعت خاموش`\n"
            "`ساعت رنگ سبز`"
        )
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_profile_clock_menu_keyboard(user_id))
        except Exception:
            pass
        return

    if cmd == 'video_to_voice':
        help_txt = (
            "🎙 ویدیو → ویس\n\n"
            "۱) روی یک ویدیو در چت سلف ریپلای کنید\n"
            "۲) بنویسید: ویس\n\n"
            "دستورات:\n• ویس\n• صدا\n• ویدیو به ویس\n\n"
            "صدا استخراج و به صورت ویس همان‌جا ارسال می‌شود."
        )
        try:
            if msg:
                await msg.delete()
        except Exception:
            pass
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_tools_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=help_txt, reply_markup=get_tools_menu_keyboard(user_id))
            except Exception:
                pass
        return

    if cmd == 'spam_protection_on':
        db.set_spam_settings(user_id, spam_protection=1)
        try:
            await refresh_panel_keyboard(query, user_id, "حفاظت اسپم", get_protection_menu_keyboard)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=get_protection_menu_keyboard(user_id))
            except Exception:
                pass
        return
    if cmd == 'spam_protection_off':
        db.set_spam_settings(user_id, spam_protection=0)
        try:
            await refresh_panel_keyboard(query, user_id, "حفاظت اسپم", get_protection_menu_keyboard)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=get_protection_menu_keyboard(user_id))
            except Exception:
                pass
        return
    if cmd == 'spam_settings':
        # بدون پیام اضافه — فقط راهنما در کپشن پنل
        try:
            await safe_edit_panel(query, "⚙️ در سلف بنویس:\nتنظیم اسپم [تعداد] [زمان]\nمثال: تنظیم اسپم 5 10", reply_markup=get_protection_menu_keyboard(user_id))
        except Exception:
            pass
        return
    if cmd == 'spam_status':
        settings = db.get_spam_settings(user_id)
        status_text = (
            f"🛡️ حفاظت اسپم:\n"
            f"🔒 وضعیت: {'فعال' if settings.get('spam_protection') else 'غیرفعال'}\n"
            f"📊 محدودیت: {settings.get('spam_limit', 10)} پیام\n"
            f"⏱️ زمان: {settings.get('mute_duration', 10)} ثانیه"
        )
        try:
            await safe_edit_panel(query, status_text, reply_markup=get_protection_menu_keyboard(user_id))
        except Exception:
            pass
        return
    lock_commands = {
        'lock_link': 'لینک',
        'lock_photo': 'عکس',
        'lock_video': 'ویدیو',
        'lock_sticker': 'استیکر',
        'lock_gif': 'گیف',
        'lock_voice': 'ویس',
        'lock_file': 'فایل',
        'lock_music': 'موزیک',
        'lock_video_note': 'ویدیو نوت',
        'lock_contact': 'کانتکت',
        'lock_location': 'لوکیشن',
        'lock_emoji': 'ایموجی',
        'lock_text': 'متن'
    }
    for cmd_prefix, lock_name in lock_commands.items():
        if cmd == cmd_prefix or cmd.startswith(cmd_prefix + '_'):
            # اولویت: target از پنل کاربر > ریپلای > پی‌وی طرف مقابل > عمومی (0)
            target_id = panel_lock_targets.get(user_id, 0)
            try:
                if not target_id and query.message and query.message.reply_to_message and query.message.reply_to_message.from_user:
                    target_id = query.message.reply_to_message.from_user.id
                if not target_id and query.message and query.message.chat and query.message.chat.type == 'private':
                    cid = query.message.chat.id
                    if cid != user_id:
                        target_id = cid
            except Exception:
                pass
            current = db.get_user_lock(user_id, target_id, cmd_prefix)
            db.set_user_lock(user_id, target_id, cmd_prefix, not current)
            try:
                if msg:
                    await msg.delete()
            except Exception:
                pass
            try:
                await query.edit_message_reply_markup(reply_markup=get_lock_menu_keyboard(user_id, target_id))
            except Exception:
                try:
                    await safe_edit_panel(query, "⊖ قفل رسانه", reply_markup=get_lock_menu_keyboard(user_id, target_id))
                except Exception:
                    pass
            return
    
    style_commands = {
        'bold': 'بولد',
        'underline': 'زیرخط',
        'strike': 'خط خورده',
        'quote': 'نقل قول',
        'spoiler': 'اسپویلر',
        'italic': 'کج',
        'code': 'کد',
        'pre': 'پیش'
    }
    for cmd_prefix, style_name in style_commands.items():
        if cmd.startswith(cmd_prefix):
            current = db.get_selfbot_settings(user_id).get('text_style')
            if current == style_name:
                db.update_selfbot_setting(user_id, 'text_style', None)
            else:
                db.update_selfbot_setting(user_id, 'text_style', style_name)
            try:
                if msg: await msg.delete()
            except Exception:
                pass
            try:
                await refresh_panel_keyboard(query, user_id, "✍️ استایل — به‌روز شد", get_style_menu_keyboard)
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            return
    
    ai_commands = {
        'ai_pm_1': {'ai_1_pm': True, 'ai_2_pm': False, 'ai_3_pm': False, 'msg': 'هوش ۱ (Gemini) در پی‌وی روشن شد'},
        'ai_pm_2': {'ai_1_pm': False, 'ai_2_pm': True, 'ai_3_pm': False, 'msg': 'هوش ۲ (Paxsenix) در پی‌وی روشن شد'},
        'ai_pm_3': {'ai_1_pm': False, 'ai_2_pm': False, 'ai_3_pm': True, 'msg': 'هوش ۳ (DeepSeek) در پی‌وی روشن شد'},
        'ai_pm_off': {'ai_1_pm': False, 'ai_2_pm': False, 'ai_3_pm': False, 'msg': 'همه هوش‌ها در پی‌وی خاموش شدند'},
        'ai_group_1': {'ai_1_group': True, 'ai_2_group': False, 'ai_3_group': False, 'msg': 'هوش ۱ (Gemini) در گروه روشن شد'},
        'ai_group_2': {'ai_1_group': False, 'ai_2_group': True, 'ai_3_group': False, 'msg': 'هوش ۲ (Paxsenix) در گروه روشن شد'},
        'ai_group_3': {'ai_1_group': False, 'ai_2_group': False, 'ai_3_group': True, 'msg': 'هوش ۳ (DeepSeek) در گروه روشن شد'},
        'ai_group_off': {'ai_1_group': False, 'ai_2_group': False, 'ai_3_group': False, 'msg': 'همه هوش‌ها در گروه خاموش شدند'}
    }
    for cmd_prefix, ai_data in ai_commands.items():
        if cmd.startswith(cmd_prefix):
            db.update_ai_status(user_id, ai_data)
            try:
                if msg: await msg.delete()
            except Exception:
                pass
            try:
                await refresh_panel_keyboard(query, user_id, "🤖 هوش مصنوعی", get_ai_menu_keyboard)
            except Exception:
                pass
            return
    
    if cmd == 'set_report':
        await msg.edit_text("📍 برای تنظیم گروه گزارش: تنظیم گزارش")
        return
    if cmd == 'show_report':
        report_config = manager.report_config
        await msg.edit_text(f"📍 گروه گزارش:\nآیدی: {report_config.report_group_id}")
        return
    
    if cmd == 'comment':
        await msg.edit_text("💬 کامنت [متن]")
        return
    if cmd == 'channels':
        auto_comments = manager.get_auto_comments()
        if auto_comments:
            msg_text = "📊 کانال‌های تنظیم شده:\n\n"
            for cid, config in auto_comments.items():
                msg_text += f"• {config['title']} ({config['type']})\n"
                msg_text += f"  آیدی: {cid}\n"
                msg_text += f"  متن: {config['text'][:30]}...\n\n"
            await msg.edit_text(msg_text)
        else:
            await msg.edit_text("📭 هیچ کانالی تنظیم نشده")
        return
    if cmd == 'delete_channel':
        chat = query.message.chat
        result = manager.remove_auto_comment(chat.id)
        await msg.edit_text(f"✅ {result}")
        return
    if cmd == 'test_channel':
        chat = query.message.chat
        info = f"🔍 اطلاعات تست:\n\n"
        info += f"چت: {chat.title}\n"
        info += f"نوع: {'کانال' if hasattr(chat, 'broadcast') and chat.broadcast else 'گروه'}\n"
        info += f"آیدی: {chat.id}\n"
        auto_comment = manager.auto_comment_settings.get(chat.id)
        info += f"تنظیم شده: {'✅' if auto_comment else '❌'}\n"
        if auto_comment:
            info += f"متن: {auto_comment['text'][:50]}...\n"
        await msg.edit_text(info)
        return
    
    if cmd == 'autosend_on':
        manager.autosend_mode = True
        db.update_selfbot_setting(user_id, 'autosend_mode', 1)
        manager.save_state()
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "📨 پیام", get_message_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'autosend_off':
        manager.autosend_mode = False
        db.update_selfbot_setting(user_id, 'autosend_mode', 0)
        manager.save_state()
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "📨 پیام", get_message_menu_keyboard)
        except Exception:
            pass
        return
    
    if cmd == 'crypto_rates':
        text = await compile_crypto_rates_text()
        try:
            await safe_edit_panel(query, text, reply_markup=get_crypto_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
            except Exception:
                pass
        # کارت تصویری
        try:
            lines = [ln.strip() for ln in text.replace("<b>","").replace("</b>","").replace("<code>","").replace("</code>","").split("\n") if ln.strip()]
            chart = await render_crypto_chart_image("بازار جهانی", lines[1:16] if len(lines)>1 else lines)
            if chart and os.path.exists(chart):
                await context.bot.send_photo(chat_id=chat_id, photo=open(chart,'rb'), caption="💎 نرخ لحظه‌ای")
                try: os.remove(chart)
                except: pass
        except Exception as _ce:
            logger.debug(f"crypto chart send: {_ce}")
        return
    if cmd == 'crypto_premium':
        text = await compile_crypto_premium_text()
        try:
            await safe_edit_panel(query, text, reply_markup=get_crypto_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
            except Exception:
                pass
        return
    if cmd == 'crypto_stars':
        text = await compile_crypto_stars_text()
        try:
            await safe_edit_panel(query, text, reply_markup=get_crypto_menu_keyboard(user_id))
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
            except Exception:
                pass
        return
    if cmd == 'crypto_help':
        help_txt = (
            "📖 راهنمای ارزها\n\n"
            "• لیست شاخص‌ها — قیمت لحظه‌ای کوین‌ها به دلار و تومان\n"
            "• پریمیوم فرگمنت — قیمت اشتراک تلگرام پریمیوم\n"
            "• استارز فرگمنت — قیمت بسته‌های ستاره\n\n"
            "در سلف می‌توانید بنویسید: نرخ ارز | قیمت ارز BTC | پریمیوم | استارز"
        )
        try:
            await safe_edit_panel(query, help_txt, reply_markup=get_crypto_menu_keyboard(user_id))
        except Exception:
            pass
        return

    if cmd == 'search_on':
        manager.search_mode = True
        try:
            await refresh_panel_keyboard(query, user_id, "🔎 گوگل", get_google_menu_keyboard)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=get_google_menu_keyboard(user_id))
            except Exception:
                pass
        return
    if cmd == 'search_off':
        manager.search_mode = False
        manager.last_search_results = []
        try:
            await refresh_panel_keyboard(query, user_id, "🔎 گوگل", get_google_menu_keyboard)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=get_google_menu_keyboard(user_id))
            except Exception:
                pass
        return

    # دستورات راهنمایی که فقط کپشن پنل را عوض می‌کنند (بدون پیام جدید)
    if cmd in ['info', 'download_profile', 'set_profile', 'set_bio',
               'delete_profile', 'delete_bio', 'change_name', 'change_bio',
               'change_profile', 'change_profile_alt', 'spam', 'reaction', 'reaction_off',
               'delete_all', 'delete_50', 'delete_10', 'action', 'action_off', 'action_list',
               'dice_1', 'dice_2', 'dice_3', 'dice_4', 'dice_5', 'dice_6',
               'dart', 'basketball', 'football']:
        # هیچ پیام جدیدی نفرست — فقط تیک کالبک
        try:
            await query.answer()
        except Exception:
            pass
        return

    # پیش‌فرض: هیچ پیام تأیید نفرست
    try:
        await query.answer()
    except Exception:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    user_id = str(user.id)
    # بن شده؟
    try:
        if db.is_user_banned(user.id):
            await update.message.reply_text("⛔ از طرف مدیریت بن شدید.\nدیگر به دستورات شما پاسخ داده نمی‌شود.")
            return
    except Exception:
        pass
    full_name = user.full_name or "کاربر"
    username = user.username or ""
    db.add_user(user_id, full_name, username)
    user_data = db.get_user(user_id)
    if user_data and user_data.get('self_active'):
        text = f"""
👋 سلام {full_name} عزیز!

✅ حساب شما فعال است.
• /panel - پنل مدیریت
• @{BOT_USERNAME} - پنل اینلاین
• .پنل - پنل در همین چت
• .اهنگ [نام آهنگ] - پخش آهنگ

⚠️ پنل فقط مخصوص شماست
        """
        keyboard = [[InlineKeyboardButton("📊 وضعیت عضویت", callback_data=f"membership_status_{user_id}")]]
        if is_admin(user.id):
            keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data=f"admin_panel")])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    text = f"""
👋 سلام {full_name} عزیز!

🌟 به ربات سلف‌بات خوش آمدید.

📌 برای استفاده:
1️⃣ روی دکمه عضویت کلیک کنید
2️⃣ شماره تلفن خود را وارد کنید
3️⃣ کد تأیید را وارد کنید

✅ پس از فعال شدن:
• /panel - پنل مدیریت
• @{BOT_USERNAME} - پنل اینلاین
• .پنل - پنل در همین چت
• .اهنگ [نام آهنگ] - پخش آهنگ
    """
    keyboard = [
        [InlineKeyboardButton("📝 عضویت", callback_data=f"membership_request_{user_id}")],
        [InlineKeyboardButton("📊 وضعیت عضویت", callback_data=f"membership_status_{user_id}")]
    ]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data=f"admin_panel")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پنل: فقط عکس + دکمه‌ها زیر آن (بدون متن میانی)"""
    if not update.message:
        return
    user = update.effective_user
    user_id = user.id
    try:
        if db.is_user_banned(user_id):
            await update.message.reply_text("⛔ از طرف مدیریت بن شدید.")
            return
    except Exception:
        pass
    user_data = db.get_user(str(user_id))
    sa = user_data.get('self_active') if user_data else None
    allowed = False
    if is_admin(user_id):
        allowed = True
    elif user_data and sa in (1, "1", True):
        allowed = True
    elif user_data and user_data.get('session_file') and os.path.exists(str(user_data.get('session_file'))):
        allowed = True
        try:
            db.update_user(str(user_id), self_active=1)
        except Exception:
            pass
    if not allowed:
        await update.message.reply_text("⛔ شما عضو سرویس نیستید")
        return
    try:
        await update.message.delete()
    except Exception:
        pass
    name = None
    try:
        name = db.get_current_name(str(user_id)) or db.get_original_name(str(user_id))
    except Exception:
        name = None
    if not name:
        name = user.full_name or user.first_name or "User"
    name = clean_display_name(name)
    # پنل اصلی → هدف پنل‌کاربر را پاک کن تا انیمیشن/اکشن به چت فعلی برود
    try:
        panel_lock_targets.pop(user_id, None)
        panel_lock_targets.pop(str(user_id), None)
    except Exception:
        pass
    keyboard = get_main_panel_keyboard(user_id)
    # دانلود آواتار
    avatar_path = None
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0:
            pf = await context.bot.get_file(photos.photos[0][-1].file_id)
            avatar_path = os.path.join(MEDIA_FOLDER, f"pf_{user_id}.jpg")
            os.makedirs(MEDIA_FOLDER, exist_ok=True)
            await pf.download_to_drive(avatar_path)
    except Exception as e:
        logger.debug(f"avatar download: {e}")
    photo_path = render_panel_image(name, avatar_path)
    if avatar_path:
        try:
            os.remove(avatar_path)
        except Exception:
            pass
    # اگر رندر نشد، خود تصویر طراحی‌شده را بفرست
    if not photo_path or not os.path.exists(photo_path):
        for p in [PANEL_HEADER_IMAGE, "panel_header.png", "panel_header_base.png",
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header.png")]:
            if p and os.path.exists(p) and os.path.getsize(p) > 1000:
                photo_path = p
                break
    caption = name
    if photo_path and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f,
                    caption=caption,
                    reply_markup=keyboard
                )
            return
        except Exception as e:
            logger.error(f"ارسال عکس پنل: {e}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=caption,
        reply_markup=keyboard
    )

async def membership_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    user_id_str = str(user_id)
    user_data = db.get_user(user_id_str)
    if not user_data:
        await query.edit_message_text("❌ خطا")
        return
    if user_data.get('self_active'):
        await query.edit_message_text("✅ شما قبلاً عضو شده‌اید")
        return
    if user_data.get('rejected'):
        await query.edit_message_text("❌ درخواست شما رد شده است")
        return
    if user_data.get('request_sent'):
        await query.edit_message_text("⏳ درخواست شما در انتظار تأیید است")
        return
    db.update_user(user_id_str, request_sent=1, request_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    admin_text = f"""
📋 درخواست عضویت جدید
━━━━━━━━━━━━━━━━━━━━
👤 نام: {user_data['full_name']}
🆔 آیدی: {user_id_str}
👤 یوزرنیم: @{user_data['username'] if user_data['username'] else 'ندارد'}
📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━
    """
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{user_id_str}"), InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id_str}")]
    ])
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=keyboard)
    await query.edit_message_text("✅ درخواست عضویت شما ثبت شد!\n\n⏳ منتظر تأیید ادمین باشید")

async def membership_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    user_id_str = str(user_id)
    user_data = db.get_user(user_id_str)
    if not user_data:
        await query.edit_message_text("👤 شما ثبت‌نام نکرده‌اید")
    elif user_data.get('self_active'):
        exp = user_data.get('expiration_date', 'نامشخص')
        await query.edit_message_text(f"✅ شما عضو فعال هستید\n\n📅 انقضا: {exp}")
    elif user_data.get('admin_approved'):
        await query.edit_message_text("⏳ در مرحله ورود اطلاعات\n\nشماره تلفن خود را وارد کنید")
    elif user_data.get('request_sent'):
        await query.edit_message_text("⏳ درخواست شما در انتظار تأیید است")
    elif user_data.get('rejected'):
        await query.edit_message_text("❌ درخواست شما رد شده است")
    else:
        await query.edit_message_text("👤 وضعیت نامشخص")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads (mainly for admin restore)"""
    if not update.message or not update.message.document:
        return
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and context.user_data.get('awaiting_restore_file'):
        await process_restore_file(update, context)
        return
    # otherwise ignore documents for non-admin / non-restore

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    text = update.message.text
    text = convert_persian_to_english(text)
    if text == '/cancel' and user_id == ADMIN_ID:
        context.user_data['awaiting_restore_file'] = False
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("✅ عملیات لغو شد")
        return
    if context.user_data.get('broadcast_mode') and user_id == ADMIN_ID:
        await handle_broadcast_message(update, context)
        return
    user_data = db.get_user(user_id_str)
    if not user_data:
        await start(update, context)
        return
    if user_data.get('rejected'):
        await update.message.reply_text("✖ درخواست شما رد شده است")
        return
    if user_data.get('self_active') in (1, "1", True) or user_data.get('self_active'):
        # عضو فعال: فقط دستور پنل را جواب بده — هیچ پیام اضافی نفرست
        if text.strip() in ('پنل', 'panel', '/panel', '.پنل'):
            await panel_command(update, context)
            return
        # اگر سلف روشن نیست، بی‌صدا روشن کن (بدون پیام)
        if user_id_str not in selfbot_managers:
            session_file = user_data.get('session_file')
            if session_file and os.path.exists(session_file):
                try:
                    manager = SelfBotManager(user_id_str)
                    if await manager.start(session_file):
                        selfbot_managers[user_id_str] = manager
                except Exception as e:
                    logger.error(f"silent start selfbot {user_id_str}: {e}")
        # هیچ پیامی نفرست — کاربر آزاد است تا /start بزند
        return
    step = user_data.get('step')
    if step == 'get_phone':
        if not user_data.get('admin_approved'):
            await update.message.reply_text("⏳ درخواست شما تأیید نشده است")
            return
        db.update_user(user_id_str, phone=text, step='get_code')
        await update.message.reply_text(f"✅ شماره {text} ذخیره شد\n⏳ در حال ارسال کد...")
        try:
            session_name = f"user_{user_id_str}"
            session_path = os.path.join(SESSIONS_FOLDER, f"{session_name}.session")
            if os.path.exists(session_path):
                os.remove(session_path)
            user_api = get_user_api(user_id_str)
            if not user_api:
                await update.message.reply_text("❌ خطا در دریافت API")
                return
            API_ID = user_api["api_id"]
            API_HASH = user_api["api_hash"]
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            sent_code = await client.send_code_request(text)
            phone_code_hash = sent_code.phone_code_hash
            db.update_user(user_id_str, phone_code_hash=phone_code_hash, code='')
            # کیبورد فارسی برای ورود کد
            code_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("۱", callback_data=f"code_digit_1_{user_id_str}"),
                    InlineKeyboardButton("۲", callback_data=f"code_digit_2_{user_id_str}"),
                    InlineKeyboardButton("۳", callback_data=f"code_digit_3_{user_id_str}"),
                ],
                [
                    InlineKeyboardButton("۴", callback_data=f"code_digit_4_{user_id_str}"),
                    InlineKeyboardButton("۵", callback_data=f"code_digit_5_{user_id_str}"),
                    InlineKeyboardButton("۶", callback_data=f"code_digit_6_{user_id_str}"),
                ],
                [
                    InlineKeyboardButton("۷", callback_data=f"code_digit_7_{user_id_str}"),
                    InlineKeyboardButton("۸", callback_data=f"code_digit_8_{user_id_str}"),
                    InlineKeyboardButton("۹", callback_data=f"code_digit_9_{user_id_str}"),
                ],
                [
                    InlineKeyboardButton("⌫ پاک", callback_data=f"code_del_{user_id_str}"),
                    InlineKeyboardButton("۰", callback_data=f"code_digit_0_{user_id_str}"),
                    InlineKeyboardButton("✅ تأیید", callback_data=f"code_ok_{user_id_str}"),
                ],
                [InlineKeyboardButton("🔙 بازگشت", callback_data=f"code_back_{user_id_str}")],
            ])
            await update.message.reply_text(
                "✅ کد تأیید ارسال شد!\n\n📩 کد ۵ رقمی را با دکمه‌های زیر وارد کنید:\n\nکد: (خالی)",
                reply_markup=code_kb
            )
            await client.disconnect()
        except FloodWaitError as e:
            await update.message.reply_text(f"⏳ {e.seconds} ثانیه صبر کنید")
            db.update_user(user_id_str, step='get_phone')
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"✖ خطا: {str(e)[:100]}\nدوباره شماره را وارد کنید")
            db.update_user(user_id_str, step='get_phone')
    elif step == 'get_code':
        # ورود متنی کد نادیده گرفته می‌شود — فقط از دکمه‌ها استفاده شود
        await update.message.reply_text("⚠️ لطفاً کد را فقط با دکمه‌های زیر پیام قبلی وارد کنید (نه به‌صورت متن).")
        return
    elif step == 'get_password':
        db.update_user(user_id_str, password=text)
        await update.message.reply_text("⏳ در حال تأیید رمز...")
        try:
            session_name = f"user_{user_id_str}"
            session_path = os.path.join(SESSIONS_FOLDER, f"{session_name}.session")
            user_api = get_user_api(user_id_str)
            if not user_api:
                await update.message.reply_text("❌ خطا در دریافت API")
                return
            API_ID = user_api["api_id"]
            API_HASH = user_api["api_hash"]
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            user_data = db.get_user(user_id_str)
            await client.sign_in(password=text)
            expiration_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            db.update_user(user_id_str, self_active=1, session_file=session_path, expiration_date=expiration_date, step=None)
            await client.disconnect()
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_path):
                selfbot_managers[user_id_str] = manager
            await update.message.reply_text("✅ سلف شما فعال شد")
            admin_message = f"✅ کاربر {user_data['full_name']} وارد شد\n🆔 {user_id_str}\n📞 {user_data['phone']}\n🔐 رمز: ✓\n🔑 API: {user_data.get('api_id', 'نامشخص')}"
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"✖ رمز نامعتبر است\nدوباره شماره را وارد کنید")
            db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None, password=None)
    else:
        await update.message.reply_text("لطفاً روی دکمه عضویت کلیک کنید")

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ دسترسی غیرمجاز")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 درخواست‌ها", callback_data="admin_requests", style="primary"), InlineKeyboardButton("🔐 منتظر ورود", callback_data="admin_login", style="primary")],
        [InlineKeyboardButton("✅ کاربران فعال", callback_data="admin_active", style="success"), InlineKeyboardButton("🤖 سلف‌بات‌ها", callback_data="admin_selfbots", style="primary")],
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats", style="primary"), InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast", style="primary")],
        [InlineKeyboardButton("💾 دریافت دیتابیس", callback_data="admin_backup_db", style="success"), InlineKeyboardButton("📤 آپلود و بازگردانی", callback_data="admin_restore_db", style="primary")],
        [InlineKeyboardButton("⚈ بازگشت", callback_data="back_main", style="danger")]
    ])
    await query.edit_message_text("👑 پنل مدیریت\n\nلطفاً انتخاب کنید:", reply_markup=keyboard)


async def admin_backup_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ دسترسی غیرمجاز")
        return
    await query.edit_message_text("⏳ در حال آماده‌سازی بکاپ دیتابیس‌ها...")
    try:
        import shutil
        import zipfile
        from datetime import datetime as dt
        ts = dt.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"backup_{ts}"
        os.makedirs(backup_dir, exist_ok=True)
        files_copied = []
        # main database
        if os.path.exists("main_database.db"):
            shutil.copy2("main_database.db", os.path.join(backup_dir, "main_database.db"))
            files_copied.append("main_database.db")
        # report config
        if os.path.exists(REPORT_CONFIG_FILE):
            shutil.copy2(REPORT_CONFIG_FILE, os.path.join(backup_dir, REPORT_CONFIG_FILE))
            files_copied.append(REPORT_CONFIG_FILE)
        # state files
        for f in os.listdir("."):
            if f.startswith("state_") and f.endswith(".json"):
                shutil.copy2(f, os.path.join(backup_dir, f))
                files_copied.append(f)
        # sessions folder (optional, can be large)
        if os.path.exists(SESSIONS_FOLDER):
            sess_dst = os.path.join(backup_dir, "user_sessions")
            os.makedirs(sess_dst, exist_ok=True)
            for f in os.listdir(SESSIONS_FOLDER):
                src = os.path.join(SESSIONS_FOLDER, f)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(sess_dst, f))
                    files_copied.append(f"user_sessions/{f}")
        # zip it
        zip_name = f"backup_full_{ts}.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(backup_dir):
                for file in files:
                    full = os.path.join(root, file)
                    arc = os.path.relpath(full, backup_dir)
                    zf.write(full, arc)
        # send to admin
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=open(zip_name, "rb"),
            caption=f"💾 بکاپ کامل دیتابیس و تنظیمات\n📅 {ts}\n📁 فایل‌ها: {len(files_copied)}\n\nشامل: main_database.db + state_*.json + report_config + sessions"
        )
        # cleanup
        shutil.rmtree(backup_dir, ignore_errors=True)
        try:
            os.remove(zip_name)
        except:
            pass
        await query.edit_message_text(f"✅ بکاپ ارسال شد.\nتعداد فایل: {len(files_copied)}")
    except Exception as e:
        logger.error(f"backup error: {e}")
        await query.edit_message_text(f"❌ خطا در بکاپ: {e}")


async def admin_restore_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ دسترسی غیرمجاز")
        return
    context.user_data['awaiting_restore_file'] = True
    await query.edit_message_text(
        "📤 **آپلود و بازگردانی دیتابیس**\n\n"
        "لطفاً فایل بکاپ (zip یا main_database.db) را همین‌جا ارسال کنید.\n\n"
        "⚠️ پس از دریافت:\n"
        "• فایل بررسی و استخراج می‌شود\n"
        "• دیتابیس جایگزین می‌شود\n"
        "• همه سلف‌بات‌های فعال ریستارت می‌شوند\n\n"
        "برای لغو: /cancel"
    )


async def process_restore_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded backup file from admin"""
    if not update.message or not update.message.document:
        return False
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return False
    if not context.user_data.get('awaiting_restore_file'):
        return False
    doc = update.message.document
    file_name = doc.file_name or "restore_file"
    await update.message.reply_text(f"⏳ دریافت فایل {file_name}...")
    try:
        import shutil
        import zipfile
        import tempfile
        file = await context.bot.get_file(doc.file_id)
        tmp_path = f"/tmp/restore_{doc.file_id}"
        await file.download_to_drive(tmp_path)
        extracted = []
        if file_name.endswith('.zip') or zipfile.is_zipfile(tmp_path):
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                zf.extractall("restore_tmp")
            for root, dirs, files in os.walk("restore_tmp"):
                for f in files:
                    src = os.path.join(root, f)
                    # map to correct places
                    if f == "main_database.db":
                        # stop all selfbots first
                        for uid, mgr in list(selfbot_managers.items()):
                            try:
                                await mgr.stop()
                            except:
                                pass
                            selfbot_managers.pop(uid, None)
                        shutil.copy2(src, "main_database.db")
                        extracted.append("main_database.db")
                    elif f == REPORT_CONFIG_FILE or f.endswith(".json") and f.startswith("state_"):
                        shutil.copy2(src, f)
                        extracted.append(f)
                    elif "user_sessions" in root or f.endswith(".session") or f.endswith(".session-journal"):
                        os.makedirs(SESSIONS_FOLDER, exist_ok=True)
                        dest = os.path.join(SESSIONS_FOLDER, f)
                        shutil.copy2(src, dest)
                        extracted.append(f"session:{f}")
            shutil.rmtree("restore_tmp", ignore_errors=True)
        elif file_name.endswith('.db') or "database" in file_name.lower():
            for uid, mgr in list(selfbot_managers.items()):
                try:
                    await mgr.stop()
                except:
                    pass
                selfbot_managers.pop(uid, None)
            shutil.copy2(tmp_path, "main_database.db")
            extracted.append("main_database.db")
        else:
            await update.message.reply_text("❌ فرمت فایل پشتیبانی نمی‌شود. zip یا .db ارسال کنید.")
            context.user_data['awaiting_restore_file'] = False
            try:
                os.remove(tmp_path)
            except:
                pass
            return True
        try:
            os.remove(tmp_path)
        except:
            pass
        # re-init db
        global db
        db = MainDatabase()
        # اصلاح مسیر session_file در صورت نیاز
        active_users = db.get_active_users()
        for user in active_users:
            uid = str(user['user_id'])
            sf = user.get('session_file')
            # اگر مسیر قدیمی/اشتباه بود، مسیر استاندارد را ست کن
            expected = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
            if (not sf or not os.path.exists(sf)) and os.path.exists(expected):
                db.update_user(uid, session_file=expected)
            elif sf and not os.path.exists(sf):
                # جستجو در پوشه sessions
                for f in os.listdir(SESSIONS_FOLDER) if os.path.exists(SESSIONS_FOLDER) else []:
                    if uid in f and f.endswith('.session'):
                        db.update_user(uid, session_file=os.path.join(SESSIONS_FOLDER, f))
                        break
        # همه کاربرانی که سشن دارند را فعال علامت بزن
        try:
            all_u = db.get_all_users()
            for u in all_u:
                uid = str(u['user_id'])
                exp = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
                if os.path.exists(exp):
                    db.update_user(uid, self_active=1, session_file=exp, admin_approved=1)
                else:
                    # جستجو
                    if os.path.exists(SESSIONS_FOLDER):
                        for fn in os.listdir(SESSIONS_FOLDER):
                            if uid in fn and fn.endswith('.session'):
                                db.update_user(uid, self_active=1, session_file=os.path.join(SESSIONS_FOLDER, fn), admin_approved=1)
                                break
        except Exception as e:
            logger.error(f"reactivate users: {e}")
        active_users = db.get_active_users()
        success = 0
        fail = 0
        fail_list = []
        for user in active_users:
            uid = str(user['user_id'])
            session_file = user.get('session_file')
            if not session_file or not os.path.exists(session_file):
                # آخرین تلاش
                expected = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
                if os.path.exists(expected):
                    session_file = expected
                    db.update_user(uid, session_file=expected)
            if session_file and os.path.exists(session_file):
                try:
                    manager = SelfBotManager(uid)
                    ok = await manager.start(session_file)
                    if ok:
                        selfbot_managers[uid] = manager
                        success += 1
                    else:
                        fail += 1
                        fail_list.append(uid)
                except Exception as e:
                    fail += 1
                    fail_list.append(f"{uid}:{e}")
                    logger.error(f"restore start {uid}: {e}")
                await asyncio.sleep(1.5)
            else:
                fail += 1
                fail_list.append(f"{uid}:no_session")
        context.user_data['awaiting_restore_file'] = False
        fail_info = ("\nناموفق: " + ", ".join(fail_list[:8])) if fail_list else ""
        await update.message.reply_text(
            f"✅ بازگردانی انجام شد.\n"
            f"📁 فایل‌های استخراج‌شده: {len(extracted)}\n"
            f"🤖 سلف‌بات موفق: {success}\n"
            f"❌ ناموفق: {fail}{fail_info}\n\n"
            f"لیست: {', '.join(extracted[:15])}{'...' if len(extracted)>15 else ''}"
        )
        return True
    except Exception as e:
        logger.error(f"restore error: {e}\n{traceback.format_exc()}")
        context.user_data['awaiting_restore_file'] = False
        await update.message.reply_text(f"❌ خطا در بازگردانی: {e}")
        return True


async def admin_requests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    pending = db.get_pending_requests()
    if pending:
        text = "📋 درخواست‌های عضویت:\n\n"
        keyboard = []
        for req in pending[:10]:
            text += f"👤 {req['full_name']}\n🆔 {req['user_id']}\n📅 {req.get('request_date', 'نامشخص')}\n\n"
            keyboard.append([InlineKeyboardButton(f"✅ تأیید {req['user_id']}", callback_data=f"approve_{req['user_id']}", style="success"), InlineKeyboardButton(f"❌ رد {req['user_id']}", callback_data=f"reject_{req['user_id']}", style="danger")])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data="admin_panel", style="danger")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("📋 هیچ درخواستی در انتظار نیست")

async def admin_login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    pending = db.get_pending_login()
    if pending:
        text = "🔐 کاربران در مرحله ورود:\n\n"
        for user in pending[:10]:
            text += f"👤 {user['full_name']}\n🆔 {user['user_id']}\n📞 {user.get('phone', 'نامشخص')}\nمرحله: {user.get('step', 'نامشخص')}\n\n"
        await query.edit_message_text(text)
    else:
        await query.edit_message_text("🔐 هیچ کاربری در مرحله ورود نیست")

async def admin_active_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    active = db.get_active_users()
    if active:
        text = "✅ کاربران فعال:\n\n"
        for user in active[:10]:
            text += f"👤 {user['full_name']}\n🆔 {user['user_id']}\n📞 {user.get('phone', 'نامشخص')}\n📅 انقضا: {user.get('expiration_date', 'نامشخص')}\n"
            text += f"🤖 سلف‌بات: {'✅' if user['user_id'] in selfbot_managers else '❌'}\n\n"
        await query.edit_message_text(text)
    else:
        await query.edit_message_text("✅ هیچ کاربر فعالی وجود ندارد")

async def admin_selfbots_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    if selfbot_managers:
        text = "🤖 سلف‌بات‌های فعال:\n\n"
        keyboard = []
        for uid, manager in list(selfbot_managers.items())[:10]:
            user_data = db.get_user(uid)
            name = user_data['full_name'] if user_data else f"کاربر {uid}"
            text += f"👤 {name}\n🆔 {uid}\n\n"
            keyboard.append([InlineKeyboardButton(f"🛑 توقف {uid}", callback_data=f"stop_selfbot_{uid}", style="danger"), InlineKeyboardButton(f"🔄 ریستارت {uid}", callback_data=f"restart_selfbot_{uid}", style="primary")])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data="admin_panel", style="danger")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("🤖 هیچ سلف‌باتی در حال اجرا نیست")

async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    total_users = len(db.get_all_users())
    active_users = len(db.get_active_users())
    pending_requests = len(db.get_pending_requests())
    pending_login = len(db.get_pending_login())
    active_selfbots = len(selfbot_managers)
    stats = f"""
📊 آمار کلی
━━━━━━━━━━━━━━━━━━━━
👥 کل کاربران: {total_users}
✅ کاربران فعال: {active_users}
📋 درخواست‌ها: {pending_requests}
🔐 منتظر ورود: {pending_login}
🤖 سلف‌بات فعال: {active_selfbots}
🕐 آخرین به‌روزرسانی: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━
    """
    await query.edit_message_text(stats)

async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    await query.edit_message_text(
        "📢 ارسال پیام همگانی\n\nلطفاً پیام خود را ارسال کنید.\n\n⚠️ توجه: این پیام برای همه کاربران فعال ارسال خواهد شد.\n\nبرای لغو: /cancel"
    )
    context.user_data['broadcast_mode'] = True

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    if not context.user_data.get('broadcast_mode'):
        return
    if update.message.text == '/cancel':
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("✅ ارسال پیام همگانی لغو شد")
        return
    message_text = update.message.text
    await update.message.reply_text("⏳ در حال ارسال پیام همگانی...")
    all_users = db.get_all_users()
    active_users = [u for u in all_users if u.get('self_active')]
    sent_count = 0
    failed_count = 0
    broadcast_id = db.add_broadcast(user_id, message_text, 'text')
    for user in active_users:
        try:
            await context.bot.send_message(chat_id=int(user['user_id']), text=f"📢 **پیام همگانی**\n━━━━━━━━━━━━━━━━━━━━\n\n{message_text}\n\n━━━━━━━━━━━━━━━━━━━━\n🕐 {datetime.now().strftime('%Y/%m/%d %H:%M')}", parse_mode='Markdown')
            sent_count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"خطا در ارسال به {user['user_id']}: {e}")
            failed_count += 1
    db.update_broadcast_stats(broadcast_id, sent_count, failed_count)
    result_text = f"""
✅ ارسال پیام همگانی کامل شد!
📊 آمار ارسال:
• کل کاربران فعال: {len(active_users)}
• ارسال موفق: {sent_count}
• ارسال ناموفق: {failed_count}
📝 متن پیام:
{message_text[:200]}
🕐 زمان: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}
    """
    await update.message.reply_text(result_text)
    context.user_data['broadcast_mode'] = False

async def approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[1]
    user_data = db.get_user(target_id)
    if not user_data:
        await query.answer("❌ کاربر یافت نشد", show_alert=True)
        return
    db.update_user(target_id, admin_approved=1, activation_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    try:
        await context.bot.send_message(chat_id=int(target_id), text="🎉 درخواست عضویت شما تأیید شد!\n\nلطفاً شماره تلفن خود را وارد کنید:\nمثال: +989123456789")
        db.update_user(target_id, step='get_phone')
    except:
        pass
    await query.edit_message_text(f"✅ کاربر {target_id} تأیید شد")
    await query.message.delete()

async def reject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[1]
    user_data = db.get_user(target_id)
    if not user_data:
        await query.answer("❌ کاربر یافت نشد", show_alert=True)
        return
    db.update_user(target_id, rejected=1, request_sent=0)
    try:
        await context.bot.send_message(chat_id=int(target_id), text="⚠ درخواست عضویت شما رد شد.\n\nمی‌توانید دوباره درخواست دهید")
    except:
        pass
    await query.edit_message_text(f"❌ کاربر {target_id} رد شد")
    await query.message.delete()

async def stop_selfbot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[2]
    if target_id in selfbot_managers:
        await selfbot_managers[target_id].stop()
        del selfbot_managers[target_id]
        await query.answer(f"✅ سلف‌بات کاربر {target_id} متوقف شد", show_alert=True)
    else:
        await query.answer("❌ سلف‌بات فعال نیست", show_alert=True)

async def restart_selfbot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[2]
    user_data = db.get_user(target_id)
    if not user_data or not user_data.get('self_active'):
        await query.answer("❌ کاربر فعال نیست", show_alert=True)
        return
    session_file = user_data.get('session_file')
    if not session_file or not os.path.exists(session_file):
        await query.answer("❌ فایل سشن یافت نشد", show_alert=True)
        return
    if target_id in selfbot_managers:
        await selfbot_managers[target_id].stop()
        del selfbot_managers[target_id]
    manager = SelfBotManager(target_id)
    if await manager.start(session_file):
        selfbot_managers[target_id] = manager
        await query.answer(f"✅ سلف‌بات کاربر {target_id} راه‌اندازی مجدد شد", show_alert=True)
    else:
        await query.answer("❌ خطا در راه‌اندازی مجدد", show_alert=True)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__)) if context.error else "بدون traceback"
    error_block = (
        f"\n{'#'*70}\n"
        f"🚨🚨🚨 خطای سراسری کنترل‌نشده 🚨🚨🚨\n"
        f"زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"update: {update}\n"
        f"نوع خطا: {type(context.error).__name__ if context.error else 'نامشخص'}\n"
        f"متن خطا: {context.error}\n"
        f"--- Traceback کامل ---\n{tb}"
        f"{'#'*70}\n"
    )
    print(error_block)
    logger.error(error_block)

async def main():
    try:
        path = ensure_panel_header_files()
        print(f"🖼 تصویر پنل: {path or 'نامشخص'}")
    except Exception as e:
        print(f"⚠️ پنل image: {e}")
    print("=" * 60)
    print("🤖 Self-Bot System v4.9.6")
    print(f"👑 ادمین: {ADMIN_ID}")
    print(f"📁 پوشه سشن‌ها: {SESSIONS_FOLDER}")
    print("=" * 60)
    
    if not os.path.exists(SESSIONS_FOLDER):
        os.makedirs(SESSIONS_FOLDER)
        print(f"📁 پوشه سشن‌ها ایجاد شد: {SESSIONS_FOLDER}")
    
    session_files = [f for f in os.listdir(SESSIONS_FOLDER) if f.endswith('.session')]
    print(f"📊 تعداد فایل‌های سشن: {len(session_files)}")
    
    request = HTTPXRequest(
        connection_pool_size=10,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )

    app = Application.builder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(InlineQueryHandler(inline_panel))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_error_handler(global_error_handler)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, timeout=30)
    
    print("✅ ربات شروع شد")
    print("=" * 60)
    
    active_users = db.get_active_users()
    success_count = 0
    fail_count = 0
    
    print(f"🔄 راه‌اندازی {len(active_users)} سلف‌بات...")
    
    for user in active_users:
        user_id_str = user['user_id']
        session_file = user.get('session_file')
        
        if session_file and os.path.exists(session_file):
            print(f"  • کاربر {user_id_str}...", end=" ")
            
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_file):
                selfbot_managers[user_id_str] = manager
                print("✅ موفق")
                success_count += 1
            else:
                print("❌ ناموفق")
                fail_count += 1
        else:
            print(f"  • کاربر {user_id_str}: فایل سشن یافت نشد ❌")
            fail_count += 1
    
    print(f"✅ {success_count} سلف‌بات فعال شدند")
    if fail_count > 0:
        print(f"⚠️ {fail_count} سلف‌بات فعال نشدند")
    print("=" * 60)
    
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("در حال توقف...")
    finally:
        for manager in selfbot_managers.values():
            await manager.stop()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == '__main__':
    print("=" * 60)
    print("🔧 PATCH: ریکت‌گروه + ترجمه - v2026-07-01")
    print("=" * 60)
    logger.info("🔧 نسخه اصلاح‌شده در حال اجراست - PATCH-2026-07-01-v2")
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 ربات متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطای fatal: {e}")
