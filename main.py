#!/usr/bin/env python3
"""
# Subaru News Radar - Minimal Starter
Fetches market data, news, generates AI summaries, posts to Telegram.
Runs every 15 minutes via GitHub Actions.
"""

import os
import json
import time
import logging
import hashlib
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup
import trafilatura
from gnews import GNews
from ddgs import DDGS
from dateutil import parser as dateparser
import requests
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG ──────────────────────────────────────────────────────────────
CONFIG = {
    'SEARCH_QUERIES': [
        'Iran (Israel OR Gaza OR Hezbollah OR Houthis) (attack OR strike OR missile OR drone)',
        'Iran (nuclear OR IAEA OR enrichment OR sanctions)',
        'Iran (dollar OR rial OR currency OR IRGC OR economy)',
        '(Trump OR "Donald Trump") (Iran OR "regime change" OR sanctions OR nuclear OR Israel)',
        '(Netanyahu OR "Benjamin Netanyahu") (Iran OR strike OR nuclear OR Hezbollah OR IRGC)',
    ],
    'SOURCE_PRIORITY': {
        'bbc.com': 10, 'radiofarda.com': 10, 'iranintl.com': 9,
        'independentpersian.com': 8, 'dw.com': 8,
        'reuters.com': 9, 'apnews.com': 8, 'aljazeera.com': 7,
        'theguardian.com': 7, 'nytimes.com': 7,
        'tasnimnews.com': 4, 'farsnews.ir': 4, 'irna.ir': 4,
        'mehrnews.com': 4, 'presstv.ir': 3,
    },
    'FILES': {
        'NEWS': 'data/news.json',
        'MARKET': 'data/market.json',
        'SPECIAL': 'data/special_reports.json',
        'DAILY': 'data/daily_summary.json',
        'BULLETINS': 'data/bulletins.json',
    },
    'TELEGRAM': {
        'BOT_TOKEN': os.environ.get('TG_BOT_TOKEN'),
        'CHANNEL_ID': os.environ.get('TG_CHANNEL_ID'),
    },
    'AI': {
        'API_KEY': os.environ.get('POLLINATIONS_API_KEY') or os.environ.get('OPENAI_API_KEY'),
        'USE_POLLINATIONS': bool(os.environ.get('POLLINATIONS_API_KEY')),
        'MODEL': 'gpt-4o-mini',
        'TIMEOUT': 45,
    },
    'TIMEOUT': 12,
    'MAX_CANDIDATES': 15,
    'MAX_TEXT_CHARS': 1800,
    'MIN_TEXT_LEN': 100,
    'MIN_TELEGRAM_URGENCY': 7,
    'MAX_NEWS_AGE_HOURS': 18,
    'HISTORY_SIZE': 300,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BAD_IMAGE_HOSTS = (
    'lh3.googleusercontent.com', 'lh4.googleusercontent.com', 'lh5.googleusercontent.com',
    'lh6.googleusercontent.com', 'encrypted-tbn0.gstatic.com', 'encrypted-tbn1.gstatic.com',
    'encrypted-tbn2.gstatic.com', 'encrypted-tbn3.gstatic.com', 'news.google.com',
    'www.google.com', 'google.com',
)

# ─── HELPERS ─────────────────────────────────────────────────────────────
def tehran_now():
    return datetime.now(timezone(timedelta(hours=3, minutes=30)))

def clean_url(url: str) -> str:
    if not url: return ""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip('/')
    except: return url

def normalize_text(text: str) -> str:
    if not text: return ""
    text = text.replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
    clean = re.sub(r'[^\w\s]', '', text.lower())
    return re.sub(r'\s+', '', clean)

def title_hash(title: str) -> str:
    return hashlib.md5(normalize_text(title).encode()).hexdigest()

def domain_score(url: str, publisher: str = "") -> int:
    try:
        host = urlparse(url or '').netloc.lower().replace('www.', '')
        for domain, score in CONFIG['SOURCE_PRIORITY'].items():
            if domain in host: return score
    except: pass
    pub = (publisher or '').lower()
    for domain, score in CONFIG['SOURCE_PRIORITY'].items():
        if domain.split('.')[0] in pub: return score
    return 3

def is_valid_image(url: str) -> bool:
    if not url or not url.startswith(('http://', 'https://')): return False
    try:
        host = urlparse(url).netloc.lower().replace('www.', '')
        if any(bad in host for bad in BAD_IMAGE_HOSTS): return False
        if 'googleusercontent.com' in host and ('=s0' in url or 'w300' in url or '-rw' in url): return False
    except: return False
    return True

def fallback_image(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ['ship','navy','sea','strait','hormuz','دریایی','کشتی','خلیج']):
        return 'https://images.unsplash.com/photo-1509316975850-ff9c5deb0cd9?auto=format&fit=crop&w=1200&q=80'
    if any(w in t for w in ['missile','strike','war','army','military','نظامی','موشک','پهپاد','حمله']):
        return 'https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=1200&q=80'
    if any(w in t for w in ['nuclear','atomic','iaea','هسته‌ای','غنی‌سازی']):
        return 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=1200&q=80'
    if any(w in t for w in ['currency','dollar','economy','تومان','دلار','تحریم','ارز']):
        return 'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=80'
    return 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=1200&q=80'

# ─── CORE CLASS ──────────────────────────────────────────────────────────
class SubaruRadar:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.scraper.headers.update({'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8'})
        self.ai_key = CONFIG['AI']['API_KEY']
        self.use_pollinations = CONFIG['AI']['USE_POLLINATIONS']
        self.existing_news = self._load_json(CONFIG['FILES']['NEWS'], [])
        self.seen_urls = {clean_url(n.get('url', '')) for n in self.existing_news if n.get('url')}
        self.seen_hashes = {title_hash(n.get('title_fa') or n.get('title_en') or '') for n in self.existing_news}
        self.gnews = GNews(language='en', country='US', period='4h', max_results=5)
        self.ddgs = DDGS()

    # ─── JSON I/O ────────────────────────────────────────────────────────
    def _load_json(self, path, default):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default

    def _save_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ─── MARKET DATA ─────────────────────────────────────────────────────
    def fetch_market(self):
        data = {"usd": "نامشخص", "oil": "نامشخص", "updated": tehran_now().strftime("%H:%M")}
        # USD from alanchand.com
        try:
            r = self.scraper.get("https://alanchand.com/en/currencies-price/usd", timeout=CONFIG['TIMEOUT'])
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                inp = soup.find('input', attrs={'data-curr': 'tmn'})
                if inp and inp.get('data-price'):
                    val = int(inp['data-price'].replace(',', ''))
                    data["usd"] = f"{val // 10:,}"
        except Exception as e:
            logger.warning(f"USD fetch failed: {e}")
        # Oil from oilprice.com
        try:
            r = self.scraper.get("https://oilprice.com/oil-price-charts/46", timeout=CONFIG['TIMEOUT'])
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                oil = soup.select_one(".last_price")
                if oil:
                    data["oil"] = oil.get_text().strip()
        except Exception as e:
            logger.warning(f"Oil fetch failed: {e}")
        self._save_json(CONFIG['FILES']['MARKET'], data)
        logger.info(f"Market updated: {data}")
        return data

    # ─── NEWS FETCHING ───────────────────────────────────────────────────
    def fetch_candidates(self):
        candidates = []
        # GNews
        for q in CONFIG['SEARCH_QUERIES']:
            try:
                for item in self.gnews.get_news(q) or []:
                    candidates.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'publisher': item.get('publisher', {}).get('title', ''),
                        'published': item.get('published date', ''),
                        'source': 'gnews'
                    })
            except Exception as e:
                logger.warning(f"GNews failed for '{q}': {e}")
        # DDGS
        for q in CONFIG['SEARCH_QUERIES'][:3]:
            try:
                for item in self.ddgs.news(q, max_results=5):
                    candidates.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'publisher': item.get('source', ''),
                        'published': item.get('date', ''),
                        'source': 'ddgs'
                    })
            except Exception as e:
                logger.warning(f"DDGS failed for '{q}': {e}")
        # Dedup by URL
        seen = set()
        uniq = []
        for c in candidates:
            cu = clean_url(c['url'])
            if cu and cu not in seen and cu not in self.seen_urls:
                seen.add(cu)
                uniq.append(c)
        return uniq[:CONFIG['MAX_CANDIDATES']]

    def extract_article(self, url: str):
        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded: return None, None
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False, favor_precision=True)
            if not text or len(text.strip()) < CONFIG['MIN_TEXT_LEN']: return None, None
            text = re.sub(r'\s+', ' ', text).strip()[:CONFIG['MAX_TEXT_CHARS']]
            # Try get image
            image = None
            try:
                meta = trafilatura.extract_metadata(downloaded)
                if meta and getattr(meta, 'image', None) and is_valid_image(meta.image):
                    image = meta.image
            except: pass
            return text, image
        except Exception as e:
            logger.warning(f"Extract failed {url}: {e}")
            return None, None

    # ─── AI ANALYSIS ─────────────────────────────────────────────────────
    def ai_analyze(self, text: str, url: str, title_hint: str = ""):
        if not self.ai_key:
            logger.warning("No AI key, skipping analysis")
            return None
        
        prompt = f"""Analyze this news article and return ONLY valid JSON:

Title hint: {title_hint}
URL: {url}
Text: {text[:2000]}

Return JSON with these exact keys:
- title_fa: Persian title (max 100 chars)
- title_en: English title (max 120 chars)
- summary: array of 2-3 short bullet points (Persian)
- impact: one sentence Persian analysis of implications
- tag: ONE of [نظامی, اقتصادی, تحریم, دیپلماسی, هسته‌ای, نیابتی, هرمز, سیاسی]
- urgency: integer 1-9 (9=breaking)
- sentiment: float -1.0 to 1.0 (negative=bad for Iran)
- lang: "fa" or "en" (detected language)"""

        try:
            if self.use_pollinations:
                # Pollinations free API
                r = requests.post(
                    "https://text.pollinations.ai/openai",
                    headers={"Authorization": f"Bearer {self.ai_key}", "Content-Type": "application/json"},
                    json={"model": CONFIG['AI']['MODEL'], "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
                    timeout=CONFIG['AI']['TIMEOUT']
                )
            else:
                # OpenAI compatible
                r = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.ai_key}", "Content-Type": "application/json"},
                    json={"model": CONFIG['AI']['MODEL'], "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
                    timeout=CONFIG['AI']['TIMEOUT']
                )
            if r.status_code == 200:
                content = r.json()['choices'][0]['message']['content']
                # Extract JSON from response
                start = content.find('{')
                end = content.rfind('}') + 1
                if start >= 0 and end > start:
                    return json.loads(content[start:end])
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")
        return None

    # ─── PROCESS PIPELINE ────────────────────────────────────────────────
    def process(self):
        logger.info("=== Starting Subaru Radar cycle ===")
        # 1. Market
        self.fetch_market()
        # 2. News
        candidates = self.fetch_candidates()
        logger.info(f"Found {len(candidates)} candidates")
        new_items = []
        for c in candidates:
            text, img = self.extract_article(c['url'])
            if not text: continue
            analysis = self.ai_analyze(text, c['url'], c.get('title', ''))
            if not analysis: continue
            # Build news item
            item = {
                "id": hashlib.md5(c['url'].encode()).hexdigest()[:10],
                "title_fa": analysis.get('title_fa', c['title'][:100]),
                "title_en": analysis.get('title_en', c['title'][:120]),
                "summary": analysis.get('summary', []),
                "impact": analysis.get('impact', ''),
                "tag": analysis.get('tag', 'گزارش'),
                "urgency": min(max(analysis.get('urgency', 5), 1), 9),
                "sentiment": max(min(analysis.get('sentiment', 0.0), 1.0), -1.0),
                "source": c.get('publisher', 'Unknown'),
                "url": c['url'],
                "clean_url": clean_url(c['url']),
                "image": img or analysis.get('image') or fallback_image(analysis.get('tag', '')),
                "timestamp": time.time(),
            }
            # Dedup check
            h = title_hash(item['title_fa'])
            if h in self.seen_hashes: continue
            self.seen_hashes.add(h)
            self.seen_urls.add(item['clean_url'])
            new_items.append(item)
            logger.info(f"New: {item['title_fa'][:50]}... (urgency={item['urgency']})")
        # Prepend new items
        if new_items:
            all_news = new_items + self.existing_news
            all_news = all_news[:CONFIG['HISTORY_SIZE']]
            self._save_json(CONFIG['FILES']['NEWS'], all_news)
            self.existing_news = all_news
            # Send urgent to Telegram
            urgent = [n for n in new_items if n['urgency'] >= CONFIG['MIN_TELEGRAM_URGENCY']]
            if urgent:
                self.send_to_telegram(urgent)
        logger.info(f"Cycle done. New items: {len(new_items)}")

    # ─── TELEGRAM ────────────────────────────────────────────────────────
    def send_to_telegram(self, items):
        if not CONFIG['TELEGRAM']['BOT_TOKEN'] or not CONFIG['TELEGRAM']['CHANNEL_ID']:
            logger.warning("Telegram not configured")
            return
        bot = Bot(token=CONFIG['TELEGRAM']['BOT_TOKEN'])
        tag_icons = {
            'نظامی': '🔴', 'اقتصادی': '💰', 'تحریم': '🚫', 'دیپلماسی': '🤝',
            'هسته‌ای': '☢️', 'نیابتی': '⚔️', 'هرمز': '⚓', 'سیاسی': '🏛️',
        }
        for item in items[:3]:  # Max 3 per cycle
            icon = tag_icons.get(item['tag'], '📰')
            urgency_stars = '⭐' * min(item['urgency'], 5)
            msg = (
                f"{icon} <b>{item['tag']}</b> {urgency_stars}\n"
                f"<b>{item['title_fa']}</b>\n"
                f"📰 <i>منبع: {item['source']}</i>\n"
                f"━━━━━━━━━━━━━━━━\n"
            )
            for s in item['summary'][:2]:
                msg += f"• {s}\n"
            msg += f"━━━━━━━━━━━━━━━━\n"
            msg += f"💡 <b>تحلیل:</b> {item['impact']}\n"
            msg += f"<a href='{item['url']}'>🔗 خواندن کامل</a>"
            try:
                if item['image'] and is_valid_image(item['image']):
                    bot.send_photo(
                        chat_id=CONFIG['TELEGRAM']['CHANNEL_ID'],
                        photo=item['image'],
                        caption=msg,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    bot.send_message(
                        chat_id=CONFIG['TELEGRAM']['CHANNEL_ID'],
                        text=msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                time.sleep(1)  # Rate limit
            except Exception as e:
                logger.error(f"Telegram send failed: {e}")

# ─── MAIN / SCHEDULER ────────────────────────────────────────────────────
def main():
    radar = SubaruRadar()
    radar.process()

if __name__ == "__main__":
    main()