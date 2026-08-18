import os
import json
import time
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import cloudscraper
from bs4 import BeautifulSoup

# ─── CONFIG ───
CONFIG = {
    'SEARCH_QUERIES': [
        'Iran (Israel OR Gaza OR Hezbollah OR Houthis) (attack OR strike OR missile OR drone)',
        'Iran (nuclear OR IAEA OR enrichment OR sanctions)',
        'Iran (dollar OR rial OR currency OR IRGC OR economy)',
        '(Trump OR "Donald Trump") (Iran OR "regime change" OR sanctions OR nuclear OR Israel)',
    ],
    'SOURCE_PRIORITY': {
        'bbc.com': 10, 'radiofarda.com': 10, 'iranintl.com': 9,
        'reuters.com': 9, 'apnews.com': 8, 'aljazeera.com': 7,
        'tasnimnews.com': 4, 'farsnews.ir': 4, 'irna.ir': 4,
    },
    'FILES': {
        'NEWS': '../data/news.json',
        'MARKET': '../data/market.json',
    },
    'TELEGRAM': {
        'BOT_TOKEN': os.environ.get('TG_BOT_TOKEN'),
        'CHANNEL_ID': os.environ.get('TG_CHANNEL_ID'),
    },
    'AI_TIMEOUT': 45,
    'MAX_NEWS_AGE_HOURS': 18,
    'HISTORY_SIZE': 300,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IranNewsRadar:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.scraper.headers.update({'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8'})
        self.existing_news = self._load_existing_news()
        self.seen_urls = set()
        self.seen_titles = set()
        for item in self.existing_news:
            if item.get('url'):
                self.seen_urls.add(self._clean_url(item['url']))
            for key in ('title_en', 'title_fa'):
                if item.get(key):
                    self.seen_titles.add(self._normalize_text(item[key]))

    def _clean_url(self, url):
        if not url: return ""
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')
        except: return url

    def _normalize_text(self, text):
        if not text: return ""
        text = text.replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
        clean = ''.join(c for c in text.lower() if c.isalnum() or c.isspace())
        return ' '.join(clean.split())

    def _load_existing_news(self):
        path = CONFIG['FILES']['NEWS']
        if not os.path.exists(path): return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except: return []

    def _save_news(self):
        with open(CONFIG['FILES']['NEWS'], 'w', encoding='utf-8') as f:
            json.dump(self.existing_news, f, ensure_ascii=False, indent=2)

    # ─── MARKET RATES ───
    def fetch_market_rates(self):
        data = {"usd": "نامشخص", "oil": "نامشخص", "updated": "--:--"}
        try:
            resp = self.scraper.get("https://alanchand.com/en/currencies-price/usd", timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                usd_input = soup.find('input', attrs={'data-curr': 'tmn'})
                if usd_input:
                    val = usd_input.get('data-price') or usd_input.get('value')
                    if val:
                        data["usd"] = f"{int(int(val.replace(',', '')) / 10):,}"
        except Exception as e:
            logger.warning(f"USD fetch failed: {e}")

        try:
            resp = self.scraper.get("https://oilprice.com/oil-price-charts/46", timeout=10)
            soup = BeautifulSoup(resp.text, 'lxml')
            oil_elem = soup.select_one(".last_price")
            if oil_elem:
                data["oil"] = oil_elem.get_text().strip()
        except Exception as e:
            logger.warning(f"Oil fetch failed: {e}")

        data["updated"] = datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime("%H:%M")
        return data

    # ─── NEWS FETCH (simplified - uses DDGS + RSS) ───
    def fetch_news(self):
        new_items = []
        # For starter: just show structure. Real impl needs DDGS + trafilatura + AI
        logger.info("News fetch placeholder - integrate DDGS + AI analysis")
        return new_items

    def run(self):
        logger.info("🚀 Starting Iran News Radar...")
        # 1. Update market
        market = self.fetch_market_rates()
        with open(CONFIG['FILES']['MARKET'], 'w', encoding='utf-8') as f:
            json.dump(market, f, ensure_ascii=False, indent=2)
        logger.info(f"💰 Market updated: USD={market['usd']}, Oil={market['oil']}")

        # 2. Fetch news (placeholder)
        # new_items = self.fetch_news()
        # if new_items: self.existing_news = new_items + self.existing_news; self._save_news()

        logger.info("✅ Cycle complete")

if __name__ == "__main__":
    radar = IranNewsRadar()
    radar.run()