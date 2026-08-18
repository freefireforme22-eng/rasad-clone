import os
import json
import time
import logging
import hashlib
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, quote_plus
import cloudscraper
from bs4 import BeautifulSoup
from ddgs import DDGS

# ─── CONFIG ───
CONFIG = {
    'AI_SEARCH_QUERIES': [
        'artificial intelligence AI news latest',
        'machine learning LLM GPT news today',
        'OpenAI Anthropic Google DeepMind AI',
        'AI model release benchmark 2026',
        'AI regulation policy safety news',
        'AI tools API open source release',
        'AI chips hardware NVIDIA AMD',
    ],
    'AI_KEYWORDS': [
        'artificial intelligence', 'machine learning', 'deep learning',
        'LLM', 'large language model', 'GPT', 'generative AI',
        'neural network', 'transformer', 'AI model', 'OpenAI',
        'Anthropic', 'Google DeepMind', 'Meta AI', 'Microsoft AI',
        'Claude', 'Gemini', 'Llama', 'Mistral', 'AI safety',
        'AI regulation', 'AI ethics', 'AI chip', 'GPU', 'NVIDIA',
    ],
    'SOURCE_PRIORITY': {
        'reuters.com': 10, 'apnews.com': 10, 'theverge.com': 9,
        'techcrunch.com': 9, 'arsTechnica.com': 8, 'venturebeat.com': 8,
        'wired.com': 8, 'mit.edu': 9, 'arxiv.org': 9, 'openai.com': 10,
        'anthropic.com': 10, 'deepmind.google': 10, 'ai.googleblog.com': 9,
        'huggingface.co': 9, 'github.com': 8, 'nvidia.com': 9,
    },
    'FILES': {
        'NEWS': '../data/news.json',
        'MARKET': '../data/market.json',
        'AI_NEWS': '../data/ai_news.json',
    },
    'TELEGRAM': {
        'BOT_TOKEN': os.environ.get('TG_BOT_TOKEN'),
        'CHANNEL_ID': os.environ.get('TG_CHANNEL_ID'),
    },
    'MAX_NEWS_AGE_HOURS': 6,
    'HISTORY_SIZE': 500,
    'MAX_AI_NEWS_PER_CYCLE': 15,
    'DDGS_MAX_RESULTS': 10,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SubaruRadar:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.scraper.headers.update({'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8'})
        self.existing_news = self._load_existing_news()
        self.existing_ai_news = self._load_existing_ai_news()
        self.seen_urls = set()
        self.seen_titles = set()
        for item in self.existing_news + self.existing_ai_news:
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

    def _load_existing_ai_news(self):
        path = CONFIG['FILES']['AI_NEWS']
        if not os.path.exists(path): return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except: return []

    def _save_news(self):
        with open(CONFIG['FILES']['NEWS'], 'w', encoding='utf-8') as f:
            json.dump(self.existing_news, f, ensure_ascii=False, indent=2)

    def _save_ai_news(self):
        with open(CONFIG['FILES']['AI_NEWS'], 'w', encoding='utf-8') as f:
            json.dump(self.existing_ai_news, f, ensure_ascii=False, indent=2)

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

    # ─── AI NEWS FETCH ───
    def is_ai_related(self, text):
        """Check if text contains AI-related keywords"""
        if not text: return False
        text_lower = text.lower()
        return any(kw in text_lower for kw in CONFIG['AI_KEYWORDS'])

    def get_source_priority(self, url):
        try:
            host = urlparse(url or '').netloc.lower().replace('www.', '')
            for domain, score in CONFIG['SOURCE_PRIORITY'].items():
                if domain in host:
                    return score
        except: pass
        return 3

    def fetch_ai_news_ddgs(self):
        """Fetch AI news using DDGS"""
        new_items = []
        ddgs = DDGS()

        for query in CONFIG['AI_SEARCH_QUERIES']:
            try:
                results = list(ddgs.text(query, max_results=CONFIG['DDGS_MAX_RESULTS']))
                for r in results:
                    url = r.get('href', '')
                    title = r.get('title', '')
                    body = r.get('body', '')

                    if not url or not title: continue
                    if not self.is_ai_related(title + ' ' + body): continue

                    clean_url = self._clean_url(url)
                    if clean_url in self.seen_urls: continue

                    # Score by source priority
                    score = self.get_source_priority(url)

                    item = {
                        'id': hashlib.md5(clean_url.encode()).hexdigest()[:10],
                        'title_en': title,
                        'title_fa': '',  # Will be filled by AI
                        'summary': [],
                        'impact': '',
                        'tag': 'AI',
                        'urgency': min(score, 9),
                        'sentiment': 0.0,
                        'source': urlparse(url).netloc.replace('www.', ''),
                        'url': url,
                        'clean_url': clean_url,
                        'image': '',
                        'timestamp': time.time(),
                        'ai_category': 'general',
                    }
                    new_items.append(item)
                    self.seen_urls.add(clean_url)

            except Exception as e:
                logger.warning(f"DDGS search failed for '{query}': {e}")

        # Sort by priority and recency
        new_items.sort(key=lambda x: (-x['urgency'], -x['timestamp']))
        return new_items[:CONFIG['MAX_AI_NEWS_PER_CYCLE']]

    def enrich_with_ai(self, items):
        """Use Pollinations AI to enrich news with Persian titles, summaries, categories"""
        if not items: return items

        for item in items:
            try:
                prompt = f"""
Analyze this AI news and return JSON only:
Title: {item['title_en']}
Source: {item['source']}
URL: {item['url']}

Return JSON with:
- title_fa: Persian title (max 80 chars)
- summary: 2-3 bullet points in Persian (key facts only)
- impact: One line Persian analysis of significance
- ai_category: One of [Model, Research, Tools, Biz, Policy, Hardware, Safety]
- sentiment: -1 to 1 (negative to positive)
- urgency: 1-9 (breaking=9, important=7, normal=5)

No markdown, no extra text. Pure JSON.
"""
                # Use Pollinations free API
                pollinations_url = "https://text.pollinations.ai/openai"
                payload = {
                    "messages": [{"role": "user", "content": prompt}],
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "max_tokens": 500,
                }
                resp = self.scraper.post(pollinations_url, json=payload, timeout=30)
                if resp.status_code == 200:
                    result = resp.json()
                    content = result.get('choices', [{}])[0].get('message', {}).get('content', '{}')
                    # Parse JSON from response
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        ai_data = json.loads(json_match.group())
                        item['title_fa'] = ai_data.get('title_fa', item['title_en'])
                        item['summary'] = ai_data.get('summary', [])
                        item['impact'] = ai_data.get('impact', '')
                        item['ai_category'] = ai_data.get('ai_category', 'general')
                        item['sentiment'] = ai_data.get('sentiment', 0.0)
                        item['urgency'] = ai_data.get('urgency', item['urgency'])
            except Exception as e:
                logger.warning(f"AI enrichment failed for {item['url']}: {e}")
                item['title_fa'] = item['title_fa'] or item['title_en']

        return items

    def fetch_and_process_ai_news(self):
        logger.info("🔍 Fetching AI news via DDGS...")
        raw_items = self.fetch_ai_news_ddgs()
        if not raw_items:
            logger.info("No new AI news found")
            return []

        logger.info(f"🤖 Enriching {len(raw_items)} items with AI...")
        enriched = self.enrich_with_ai(raw_items)

        # Add to existing (newest first)
        self.existing_ai_news = enriched + self.existing_ai_news
        # Keep history size
        self.existing_ai_news = self.existing_ai_news[:CONFIG['HISTORY_SIZE']]
        self._save_ai_news()

        logger.info(f"✅ Saved {len(enriched)} new AI news items")
        return enriched

    # ─── TELEGRAM FORMATTER (Rasad-style) ───
    def format_ai_news_for_telegram(self, items):
        """Format AI news in Rasad-style for Telegram"""
        if not items: return ""

        lines = ["🤖 **اخبار هوش مصنوعی - Subaru News**", ""]

        for item in items:
            # Category emoji
            cat_emoji = {
                'Model': '🧠', 'Research': '🔬', 'Tools': '🛠',
                'Biz': '💼', 'Policy': '⚖️', 'Hardware': '💾',
                'Safety': '🛡️', 'general': '📰'
            }.get(item.get('ai_category', 'general'), '📰')

            title = item.get('title_fa') or item.get('title_en', 'بدون عنوان')
            source = item.get('source', 'منبع ناشناس')
            url = item.get('url', '')
            ai_cat = item.get('ai_category', 'general')

            # Hashtags
            tags = ['#AI', f'#{ai_cat}']
            if 'OpenAI' in (item.get('title_en', '') + item.get('title_fa', '')):
                tags.append('#OpenAI')
            if 'Google' in (item.get('title_en', '') + item.get('title_fa', '')):
                tags.append('#Google')
            if 'NVIDIA' in (item.get('title_en', '') + item.get('title_fa', '')):
                tags.append('#NVIDIA')

            lines.append(f"{cat_emoji} **{title}** ({source})")
            lines.append(f"🔗 {url}")
            lines.append(f"{' '.join(tags)}")
            lines.append("")

        lines.append("---")
        lines.append(f"⏰ آپدیت: {datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime('%H:%M')} | 🔄 هر ۳ ساعت")
        lines.append("#SubaruNews #AI #ArtificialIntelligence")

        return "\n".join(lines)

    def send_to_telegram(self, text):
        """Send formatted message to Telegram channel"""
        token = CONFIG['TELEGRAM']['BOT_TOKEN']
        chat_id = CONFIG['TELEGRAM']['CHANNEL_ID']
        if not token or not chat_id:
            logger.warning("Telegram credentials not configured")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': False,
        }
        try:
            resp = self.scraper.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                logger.info("✅ Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def run(self):
        logger.info("🚀 Starting Subaru Radar...")

        # 1. Update market
        market = self.fetch_market_rates()
        with open(CONFIG['FILES']['MARKET'], 'w', encoding='utf-8') as f:
            json.dump(market, f, ensure_ascii=False, indent=2)
        logger.info(f"💰 Market updated: USD={market['usd']}, Oil={market['oil']}")

        # 2. Fetch and process AI news
        new_ai_items = self.fetch_and_process_ai_news()

        # 3. Send to Telegram if new items
        if new_ai_items:
            telegram_text = self.format_ai_news_for_telegram(new_ai_items)
            self.send_to_telegram(telegram_text)
        else:
            logger.info("No new AI news to send")

        logger.info("✅ Cycle complete")


if __name__ == "__main__":
    radar = SubaruRadar()
    radar.run()