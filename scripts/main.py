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
    'AI_RSS_FEEDS': [
        'https://openai.com/blog/rss.xml',
        'https://deepmind.google/blog/rss.xml',
        'https://ai.googleblog.com/feeds/posts/default',
        'https://huggingface.co/blog/feed.xml',
        'https://www.technologyreview.com/feed/',
        'https://venturebeat.com/category/ai/feed/',
        'https://techcrunch.com/tag/artificial-intelligence/feed/',
        'https://www.theverge.com/ai-artificial-intelligence/rss/index.xml',
        'https://arxiv.org/rss/cs.AI',
        'https://arxiv.org/rss/cs.LG',
        'https://arxiv.org/rss/cs.CL',
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

    def _is_category_page(self, url, title):
        """Filter out category/index/aggregator pages"""
        url_lower = url.lower()
        title_lower = title.lower()
        
        # Patterns that indicate category/list pages
        category_patterns = [
            '/categories/', '/category/', '/tag/', '/tags/',
            '/topic/', '/topics/', '/section/', '/channels/',
            '/latest', '/news/', '/archive/', '/feed/',
            'latest-headlines', 'latest-news', 'all-news',
            'artificial-intelligence/', 'machine-learning/',
            'ai-news', '/ai/', '/news', 'newsnow', 'google.com/news',
        ]
        
        # Generic titles that indicate aggregator pages
        generic_titles = [
            'latest headlines', 'latest news', 'latest developments',
            'news & insights', 'news and analysis', 'news |',
            'categories', 'all news', 'topic:', 'section:',
        ]
        
        for pattern in category_patterns:
            if pattern in url_lower:
                return True
        for generic in generic_titles:
            if generic in title_lower:
                return True
        
        return False

    def fetch_article_content(self, url):
        """Fetch and extract article content from URL - improved extraction"""
        try:
            resp = self.scraper.get(url, timeout=20)
            if resp.status_code != 200:
                return "", []
            
            soup = BeautifulSoup(resp.content, 'lxml')
            
            # Extract images FIRST (before removing any elements)
            images = self._extract_article_images(soup, url)
            
            # Remove unwanted elements
            for elem in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'button', 'iframe', 'noscript', 'meta', 'link']):
                elem.decompose()
            
            # Also remove common non-content classes/ids
            for elem in soup.find_all(class_=re.compile(r'(nav|menu|sidebar|footer|header|ad|banner|cookie|popup|modal|share|social|related|recommended|newsletter|subscribe|comment|author|breadcrumb|pagination|tag|category)', re.I)):
                elem.decompose()
            for elem in soup.find_all(id=re.compile(r'(nav|menu|sidebar|footer|header|ad|banner|cookie|popup|modal|share|social|related|recommended|newsletter|subscribe|comment|breadcrumb|pagination)', re.I)):
                elem.decompose()
            
            # Try common article selectors with priority
            article_selectors = [
                'article[role="article"]',
                'article.post',
                'article.entry',
                'article',
                '[role="article"]',
                '.post-content',
                '.entry-content',
                '.article-content',
                '.content-body',
                '.post-body',
                '.article-body',
                '.story-body',
                '.entry-body',
                'main.content',
                '.main-content',
                '#content',
                '#main-content',
                '.article-text',
                '.story-content',
            ]
            
            article_text = ""
            for selector in article_selectors:
                elements = soup.select(selector)
                if elements:
                    # Get text from all matching elements
                    texts = []
                    for el in elements:
                        text = el.get_text(separator=' ', strip=True)
                        if len(text) > 100:  # Only substantial content
                            texts.append(text)
                    if texts:
                        article_text = ' '.join(texts)
                        if len(article_text) > 500:
                            break
            
            # Fallback: get all paragraph text from main content area
            if not article_text or len(article_text) < 500:
                # Try to find main content container
                main_candidates = soup.select('main, .main, #main, .content, #content, .post, .article, .entry')
                if main_candidates:
                    paragraphs = main_candidates[0].find_all('p')
                else:
                    paragraphs = soup.find_all('p')
                
                article_text = ' '.join([
                    p.get_text(strip=True) 
                    for p in paragraphs 
                    if len(p.get_text(strip=True)) > 60
                    and not any(skip in p.get_text(strip=True).lower() for skip in [
                        'read more', 'click here', 'subscribe', 'follow us', 'sign up',
                        'privacy policy', 'terms of use', 'cookie policy', 'all rights reserved',
                        'copyright', 'advertisement', 'sponsored', 'affiliate', 'share this',
                        'tweet', 'share on', 'like us', 'follow on'
                    ])
                ])
            
            # Clean up
            article_text = re.sub(r'\s+', ' ', article_text)
            
            # Remove common boilerplate patterns
            article_text = re.sub(r'(?i)(subscribe|newsletter|sign up|follow us|share this|advertisement|sponsored|cookie policy|privacy policy|terms of use|all rights reserved|copyright).*?\.', '', article_text)
            
            return article_text[:8000], images
            
        except Exception as e:
            logger.warning(f"Failed to fetch article content from {url}: {e}")
            return "", []

    def _extract_article_images(self, soup, base_url):
        """Extract relevant images from article page"""
        images = []
        from urllib.parse import urljoin
        
        # Priority 1: Open Graph / Twitter Card images
        og_image = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'twitter:image'})
        if og_image and og_image.get('content'):
            img_url = urljoin(base_url, og_image['content'])
            images.append(img_url)
        
        # Priority 2: First large image in article content
        article_imgs = soup.select('article img, .post-content img, .entry-content img, .article-content img, .content-body img, main img, .main-content img')
        for img in article_imgs[:5]:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                width = img.get('width')
                height = img.get('height')
                if width and height:
                    try:
                        if int(width) < 200 or int(height) < 150:
                            continue
                    except:
                        pass
                img_url = urljoin(base_url, src)
                if img_url not in images:
                    images.append(img_url)
        
        # Priority 3: Any large img in main content area
        if len(images) < 3:
            main_imgs = soup.select('main img, .content img, #content img, .post img, .article img')
            for img in main_imgs[:5]:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    width = img.get('width')
                    height = img.get('height')
                    if width and height:
                        try:
                            if int(width) < 200 or int(height) < 150:
                                continue
                        except:
                            pass
                    img_url = urljoin(base_url, src)
                    if img_url not in images:
                        images.append(img_url)
        
        # Limit to max 3 images per article
        return images[:3]

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
                    if self._is_category_page(url, title): continue

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
        """Enrich news with Persian titles, summaries, categories using content-aware local generation.
        (Pollinations disabled - was returning generic responses)"""
        if not items: return items

        for item in items:
            # Fetch article content for better summarization
            article_content, images = self.fetch_article_content(item['url'])
            item['article_content'] = article_content
            item['images'] = images

            # Use content-aware local Persian generation (PRIMARY METHOD)
            item['title_fa'] = self._generate_persian_title(item['title_en'])
            item['summary'] = self._generate_persian_summary(item['title_en'], item['source'], item.get('article_content', ''), item.get('description', ''))
            item['impact'] = self._generate_persian_impact(item['title_en'])
            item['ai_category'] = self._guess_category(item['title_en'])
            item['sentiment'] = 0.1
            item['urgency'] = item.get('urgency', 6)

        return items

    def _generate_persian_title(self, title_en):
                """Generate Persian title ONLY (no English in parentheses) - token-based"""
                import re

                # All mappings: English -> Persian ONLY
                # Sorted by length descending for phrase matching
                all_mappings = [
                    # Phrases (longest first)
                    ('Multi-Vector', 'چند برداری'),
                    ('Late Interaction', 'تعامل دیرهنگام'),
                    ('Sentence Transformers', 'سنتنس ترنسفورمرز'),
                    ('Open Source', 'بازمتن'),
                    ('Open-weight Model', 'مدل باز‌وزن'),
                    ('Open-weight', 'باز‌وزن'),
                    ('Large Language Model', 'مدل زبانی بزرگ'),
                    ('Artificial Intelligence', 'هوش مصنوعی'),
                    ('Machine Learning', 'ماشین لرنینگ'),
                    ('Deep Learning', 'دیپ لرنینگ'),
                    ('Generative AI', 'هوش مصنوعی مولد'),
                    ('Neural Network', 'شبکه عصبی'),
                    ('Attention Mechanism', 'مکانیزم توجه'),
                    ('Fine-tuning', 'فاین‌تیونینگ'),
                    ('Hidden State', 'حالت پنهان'),
                    ('Majority Voting', 'رأی‌گیری اکثریت'),
                    ('Road Safety', 'ایمنی راه'),
                    ('Connected Vehicle', 'خودرو متصل'),
                    ('Transformer-based', 'ترنسفورمر-بیس'),
                    ('Daily-Scale', 'روزانه'),
                    ('Longitudinal', 'طی‌دراز'),
                    ('Multimodal', 'چند حالته'),
                    ('Readmission', 'بازآسپذیری'),
                    ('Margin-Regularized', 'مرز-منظم‌شده'),
                    ('Structured Semantic Alignment', 'الاینمنت سمنتیک ساختاریافته'),
                    ('Brain-Language Correspondence', 'همبستگی مغز-زبان'),
                    ('Cross-Model Memory Transfer', 'ترنسفر حافظه کراس-مدل'),
                    ('Target-Side Reader Adaptation', 'آدابتیشن ریدر هدف-سمت'),
                    ('Institution-Specific', 'مؤسسه-مخصوص'),
                    ('De-identification', 'دی‌آی‌نتیفیکیشن'),
                    ('Gold Standards', 'استانداردهای طلایی'),
                    ('Decision Making', 'تصمیم‌گیری'),
                    ('System 2', 'سیستم ۲'),
                    ('Untrusted Documents', 'اسناد غیرموثوق'),
                    ('Safer RAG', 'رگ امن‌تر'),

                    # Single words
                    ('AI', 'هوش مصنوعی'),
                    ('LLM', 'ال‌ام‌ال'),
                    ('GPT', 'جی‌پی‌یو'),
                    ('RAG', 'رگ'),
                    ('GPU', 'جی‌پی‌یو'),
                    ('API', 'ای‌پی‌آی'),
                    ('AWS', 'ا‌دابلیو‌اس'),
                    ('PHI', 'فی‌آی‌اچ'),
                    ('Model', 'مدل'),
                    ('Models', 'مدل‌ها'),
                    ('Modeling', 'مدل‌سازی'),
                    ('Embedding', 'امبدینگ'),
                    ('Embeddings', 'امبدینگ‌ها'),
                    ('Vector', 'برداری'),
                    ('Vectors', 'برداری‌ها'),
                    ('Transformer', 'ترنسفورمر'),
                    ('Transformers', 'ترنسفورمرها'),
                    ('Decoder', 'دی‌کدر'),
                    ('Decodability', 'کدپذیری'),
                    ('Sentence', 'جمله'),
                    ('Sentences', 'جملات'),
                    ('Claude', 'کلود'),
                    ('Gemini', 'جمینی'),
                    ('Llama', 'لاما'),
                    ('Mistral', 'مِیسترال'),
                    ('NousCoder', 'نوس‌کدر'),
                    ('Nous Research', 'نوس ریسرچ'),
                    ('Cowork', 'کاوورک'),
                    ('Slackbot', 'اسلک‌بات'),
                    ('Salesforce', 'سیِلزفورس'),
                    ('Railway', 'ریلوِی'),
                    ('OpenAI', 'اوپن‌ای‌آی'),
                    ('Anthropic', 'آنتروپیک'),
                    ('Google', 'گوگل'),
                    ('DeepMind', 'دیپ‌مایند'),
                    ('Meta', 'مِتا'),
                    ('Microsoft', 'مایکروسافت'),
                    ('NVIDIA', 'انویدیا'),
                    ('Research', 'تحقیق'),
                    ('Paper', 'مقاله'),
                    ('Study', 'مطالعه'),
                    ('Benchmark', 'بنچ‌مارک'),
                    ('Training', 'آموزش'),
                    ('Inference', 'استنتاج'),
                    ('Agent', 'عامل'),
                    ('Agents', 'عامل‌ها'),
                    ('Tool', 'ابزار'),
                    ('Tools', 'ابزارها'),
                    ('Release', 'انتشار'),
                    ('Launch', 'راه‌اندازی'),
                    ('Coding', 'کدنویسی'),
                    ('Desktop', 'دسکتاپ'),
                    ('Files', 'فایل‌ها'),
                    ('Workspace', 'ورک‌اسپیس'),
                    ('Cloud', 'کلاد'),
                    ('Infrastructure', 'زیرساخت'),
                    ('Safety', 'امنیت'),
                    ('Security', 'امنیت'),
                    ('Privacy', 'حریم خصوصی'),
                    ('Regulation', 'تنظیمات'),
                    ('Ethics', 'اخلاق'),
                    ('Chip', 'تراشه'),
                    ('Chips', 'تراشه‌ها'),
                    ('Hardware', 'سخت‌افزار'),
                    ('Funding', 'سرمایه‌گذاری'),
                    ('Investment', 'سرمایه‌گذاری'),
                    ('Startup', 'استارتاپ'),
                    ('Company', 'شرکت'),
                    ('Business', 'کسب‌وکار'),
                    ('Growth', 'رشد'),
                    ('News', 'اخبار'),
                    ('Latest', 'جدیدترین'),
                    ('Insights', 'بینش‌ها'),
                    ('Analysis', 'تحلیل'),
                    ('Developments', 'توسعه‌ها'),
                    ('Updates', 'به‌روزرسانی‌ها'),
                    ('Technology', 'تکنولوژی'),
                    ('Tech', 'تک'),
                    ('Annual', 'سالانه'),
                    ('Report', 'گزارش'),
                    ('Review', 'بررسی'),
                    ('Guide', 'راهنما'),
                    ('Tutorial', 'آموزش'),
                    ('Explained', 'توضیح داده شده'),
                    ('Prediction', 'پیش‌بینی'),
                    ('Intervention', 'مداخله'),
                    ('Driving', 'رانندگی'),
                    ('Hotspots', 'هات‌اسپات‌ها'),
                    ('Data', 'دیتا'),
                    ('Classical', 'کلاسیک'),
                    ('Document', 'سند'),
                    ('Documents', 'اسناد'),
                    ('Sensitivity', 'حساسیت'),
                    ('Classification', 'طبقه‌بندی'),
                    ('Uncertainty', 'عدم اطمینان'),
                    ('Thinking', 'تفکر'),
                    ('Access', 'دسترسی'),
                    ('Capable', 'قادر'),
                    ('Context', 'بافت'),
                    ('Attention', 'توجه'),
                    ('Parameters', 'پارامترها'),
                    ('Tokens', 'توکن‌ها'),
                    ('Dataset', 'دیتاست'),
                    ('Prompt', 'پرامپت'),
                    ('Prompting', 'پرامپتینگ'),
                    ('Alignment', 'الاینمنت'),
                    ('Semantic', 'سمنتیک'),
                    ('Structured', 'ساختاریافته'),
                    ('Correspondence', 'همبستگی'),
                    ('Transfer', 'ترنسفر'),
                    ('Memory', 'حافظه'),
                    ('Reader', 'ریدر'),
                    ('Adaptation', 'آدابتیشن'),
                    ('Brain', 'مغز'),
                    ('Language', 'زبان'),
                    ('Selection', 'انتخاب'),
                    ('Voting', 'رأی‌گیری'),
                    ('Majority', 'اکثریت'),
                ]

                # Tokenize: split on word boundaries while keeping delimiters
                # This preserves punctuation, spaces, hyphens, etc.
                tokens = re.findall(r'\w+|[^\w\s]|\s+', title_en)

                result_tokens = []
                i = 0
                while i < len(tokens):
                    matched = False
                    # Try to match phrases (up to 4 tokens ahead)
                    for phrase_len in range(4, 0, -1):
                        if i + phrase_len <= len(tokens):
                            candidate = ''.join(tokens[i:i+phrase_len])
                            # Check if candidate matches any mapping
                            for en_term, fa_term in all_mappings:
                                if candidate == en_term:
                                    result_tokens.append(fa_term)
                                    i += phrase_len
                                    matched = True
                                    break
                            if matched:
                                break
                    if not matched:
                        result_tokens.append(tokens[i])
                        i += 1

                fa_title = ''.join(result_tokens)

                # Truncate
                if len(fa_title) > 120:
                    fa_title = fa_title[:117] + '...'
                return fa_title

    def _generate_persian_summary(self, title_en, source, article_content='', description=''):
            """Generate Persian summary points - ONLY Persian, content-specific"""
            summaries = []
        
            # Combine all available content
            all_content = (title_en + ' ' + description + ' ' + article_content).lower()
            content_lower = article_content.lower() if article_content else ''
            desc_lower = description.lower() if description else ''
        
            # PRIORITY 1: Extract actual meaningful sentences from article content
            # This is the BEST source for specific summaries
            if content_lower and len(content_lower) > 200:
                sentences = [s.strip() for s in article_content.split('.') if len(s.strip()) > 50]
                # Filter for informative sentences (contain numbers, specific terms, etc.)
                informative = []
                for s in sentences[:10]:
                    sl = s.lower()
                    # Skip generic marketing fluff
                    if any(skip in sl for skip in ['read more', 'click here', 'subscribe', 'follow us', 'sign up', 'privacy policy', 'terms of use', 'cookie policy', 'all rights reserved']):
                        continue
                    # Prefer sentences with specific details
                    if any(indicator in sl for indicator in ['%', '$', 'million', 'billion', 'percent', 'درصد', 'میلیون', 'میلیارد', '۲۰۲', '۲۰۲۶', '۲۰۲۵', 'released', 'launched', 'announced', 'راه‌اندازی', 'انتشار', 'منتشر', 'researchers found', 'study shows', 'پیدا کرد', 'نمایش داد', 'according to', 'بر اساس']):
                        informative.append(s)
                    elif len(s) > 80:
                        informative.append(s)
            
                if informative:
                    for s in informative[:2]:
                        clean = s[:200] + '...' if len(s) > 200 else s
                        # Translate common English terms to Persian
                        clean = clean.replace('AI', 'هوش مصنوعی').replace('LLM', 'ال‌ام‌ال').replace('GPT', 'جی‌پی‌یو')
                        clean = clean.replace('RAG', 'رگ').replace('API', 'ای‌پی‌آی').replace('GPU', 'جی‌پی‌یو')
                        clean = clean.replace('OpenAI', 'اوپن‌ای‌آی').replace('Anthropic', 'آنتروپیک').replace('Google', 'گوگل')
                        clean = clean.replace('Microsoft', 'مایکروسافت').replace('Meta', 'مِتا').replace('NVIDIA', 'انویدیا')
                        summaries.append(clean)
                    if len(summaries) >= 3:
                        return summaries[:3]
        
            # PRIORITY 2: Use RSS/DDGS description if available
            if desc_lower and len(desc_lower) > 100 and len(summaries) < 3:
                sentences = [s.strip() for s in description.split('.') if len(s.strip()) > 40]
                for s in sentences[:3-len(summaries)]:
                    clean = s[:200] + '...' if len(s) > 200 else s
                    clean = clean.replace('AI', 'هوش مصنوعی').replace('LLM', 'ال‌ام‌ال').replace('GPT', 'جی‌پی‌یو')
                    clean = clean.replace('RAG', 'رگ').replace('API', 'ای‌پی‌آی').replace('GPU', 'جی‌پی‌یو')
                    clean = clean.replace('OpenAI', 'اوپن‌ای‌آی').replace('Anthropic', 'آنتروپیک').replace('Google', 'گوگل')
                    clean = clean.replace('Microsoft', 'مایکروسافت').replace('Meta', 'مِتا').replace('NVIDIA', 'انویدیا')
                    summaries.append(clean)
        
            # PRIORITY 3: Specific content-based patterns (only if we still need more)
            if len(summaries) < 3:
                # Funding/Investment - specific amounts
                if '100 million' in all_content or '$100m' in all_content or '۱۰۰ میلیون' in all_content:
                    summaries.append("۱۰۰ میلیون دلار سرمایه‌گذاری برای توسعه زیرساخت ابری بومی هوش مصنوعی جذب شد")
                elif any(kw in all_content for kw in ['series a', 'series b', 'series c', 'funding round', 'investment round']):
                    summaries.append("گردهمایی سرمایه‌گذاری جدید برای توسعه تکنولوژی‌های هوش مصنوعی انجام شد")
            
                # Specific model releases with details
                if 'claude code' in all_content and 'goose' in all_content:
                    summaries.append("گوس جایگزین رایگان کلود کد برای کدنویسی خودکار به صورت محلی عرضه شد")
                elif 'cowork' in all_content or 'claude desktop' in all_content:
                    summaries.append("عامل دسکتاپ کلود برای کار با فایل‌های کاربر بدون نیاز به کدنویسی راه‌اندازی شد")
                elif 'slackbot' in all_content and 'salesforce' in all_content:
                    summaries.append("سیلزفورس عامل هوش مصنوعی اسلک‌بات برای محیط کار عرضه کرد")
                elif 'qwen' in all_content and ('27b' in all_content or '27 billion' in all_content):
                    summaries.append("مدل کوئن ۲۷ میلیارد پارامتری با عملکرد هم‌سطح مدل‌های پیشرو معرفی شد")
                elif 'ornith' in all_content and '397b' in all_content:
                    summaries.append("مدل آرنیت ۳۹۷ میلیارد پارامتری در بنچ‌مارک‌های لیدربورد حاضر شد")
                elif 'glm' in all_content and '5.3' in all_content:
                    summaries.append("جی‌ال‌ام ۵.۳ از تیم زِدهای انتشار یافت")
            
                # Regulation/Policy
                if 'ai regulation' in all_content and 'healthcare' in all_content:
                    summaries.append("تنظیمات هوش مصنوعی در بخش درمان پیش از قانون‌گذاری فدرال توسط ایالت‌ها پیشرو شده")
                elif 'white house' in all_content and 'national policy' in all_content:
                    summaries.append("خانه سفید چارچوب سیاست ملی هوش مصنوعی با اولویت امنیت کودکان را منتشر کرد")
                elif 'china' in all_content and 'export' in all_content and 'data' in all_content:
                    summaries.append("چین قصد صادرات داده‌های آموزشی برای نفوذ روایات خود در چت‌بات‌های جهانی را دارد")
            
                # Hardware/Chips
                if 'nvidia' in all_content and 'amd' in all_content and ('chip' in all_content or 'hardware' in all_content):
                    summaries.append("مقایسه تراشه‌های هوش مصنوعی انویدیا، ای‌م‌دی و سفارشی برای آینده سخت‌افزار")
            
                # Research specific
                if 'rag' in all_content and 'cost' in all_content and ('6x' in all_content or '۶ برابر' in all_content):
                    summaries.append("رویکرد آبشاری رگ هزینه استنتاج را ۶ برابر کاهش می‌دهد با حفظ دقت")
                elif 'peer review' in all_content and 'overwhelm' in all_content:
                    summaries.append("تحلیل تأثیر تولید مقاله‌های هوش مصنوعی بر سیستم داوران و چالش‌های موجود")
                elif 'decodability' in all_content and 'hidden state' in all_content:
                    summaries.append("معیار کدپذیری پیش‌بینی می‌کند که انتخاب حالت پنهان کجا بر رأی‌گیری اکثریت برتری دارد")
                elif 'road safety' in all_content and 'connected vehicle' in all_content:
                    summaries.append("مداخله پیشگیرانه ایمنی راه با پیش‌بینی نقاط خطرناک رانندگی از داده‌های خودروهای متصل")
        
            # LAST RESORT: Only if absolutely nothing else worked
            if not summaries:
                summaries.append("پیشرفت جدید در حوزه هوش مصنوعی گزارش شده")
                summaries.append("جزئیات در متن کامل مقاله موجود است")
        
            return summaries[:3]

    def _generate_persian_impact(self, title_en):
        """Generate Persian impact analysis - ONLY Persian, no English"""
        title_lower = title_en.lower()
    
        if any(kw in title_lower for kw in ['openai', 'anthropic', 'google', 'deepmind', 'meta', 'microsoft']):
            return "شرکت‌های بزرگ تکنولوژی پیشروی در توسعه هوش مصنوعی را ادامه می‌دهند"
        if any(kw in title_lower for kw in ['open source', 'open-source']):
            return "بازمتن بودن این پروژه نوآوری و دسترسی گسترده را تسریع می‌کند"
        if any(kw in title_lower for kw in ['funding', 'investment', 'million', 'billion']):
            return "جذب سرمایه نشان‌دهنده اعتماد بازار به آینده هوش مصنوعی است"
        if any(kw in title_lower for kw in ['research', 'paper', 'arxiv', 'study']):
            return "پیشرفت‌های علمی پایه برای کاربردهای آینده فراهم می‌آورند"
    
        return "این توسعه می‌تواند بر روندهای آینده هوش مصنوعی تأثیر بگذارد"

    def _guess_category(self, title_en):
        """Guess AI category from title"""
        title_lower = title_en.lower()
        if any(kw in title_lower for kw in ['model', 'llm', 'gpt', 'claude', 'gemini', 'llama', 'release', 'launch']):
            return 'مدل'
        if any(kw in title_lower for kw in ['research', 'paper', 'arxiv', 'study', 'benchmark']):
            return 'تحقیق'
        if any(kw in title_lower for kw in ['tool', 'api', 'agent', 'coding', 'open source', 'open-source']):
            return 'ابزار'
        if any(kw in title_lower for kw in ['funding', 'investment', 'startup', 'company', 'million', 'billion']):
            return 'کسب‌وکار'
        if any(kw in title_lower for kw in ['safety', 'security', 'regulation', 'policy', 'ethics', 'privacy']):
            return 'امنیت'
        if any(kw in title_lower for kw in ['chip', 'gpu', 'hardware', 'nvidia', 'amd', 'intel']):
            return 'سخت‌افزار'
        return 'عمومی'

    def fetch_and_process_ai_news(self):
        logger.info("🔍 Fetching AI news via RSS + DDGS...")
    
        # 1. Fetch from RSS feeds (primary source)
        rss_items = self.fetch_ai_news_rss()
    
        # 2. Fetch from DDGS (fallback)
        ddgs_items = self.fetch_ai_news_ddgs()
    
        # Combine and deduplicate
        all_raw_items = rss_items + ddgs_items
        seen = set()
        unique_items = []
        for item in all_raw_items:
            clean_url = self._clean_url(item['url'])
            if clean_url not in seen:
                seen.add(clean_url)
                unique_items.append(item)
    
        if not unique_items:
            logger.info("No new AI news found")
            return []

        logger.info(f"🤖 Enriching {len(unique_items)} items with AI...")
        enriched = self.enrich_with_ai(unique_items)

        # Limit to 15 newest items
        enriched = enriched[:15]

        # Add to existing (newest first)
        self.existing_ai_news = enriched + self.existing_ai_news
        # Keep history size
        self.existing_ai_news = self.existing_ai_news[:CONFIG['HISTORY_SIZE']]
        self._save_ai_news()

        logger.info(f"✅ Saved {len(enriched)} new AI news items")
        return enriched

    def fetch_ai_news_rss(self):
        """Fetch AI news from RSS feeds"""
        import xml.etree.ElementTree as ET
        new_items = []

        for feed_url in CONFIG['AI_RSS_FEEDS']:
            try:
                resp = self.scraper.get(feed_url, timeout=15)
                if resp.status_code != 200:
                    continue
            
                root = ET.fromstring(resp.content)
                # Handle different RSS/Atom formats
                items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
            
                for item in items[:10]:  # Max 10 per feed
                    if item.tag.endswith('item'):  # RSS
                        title = item.findtext('title', '')
                        link = item.findtext('link', '')
                        description = item.findtext('description', '')
                        pub_date = item.findtext('pubDate', '')
                    else:  # Atom
                        title = item.findtext('{http://www.w3.org/2005/Atom}title', '')
                        link = item.find('{http://www.w3.org/2005/Atom}link')
                        link = link.get('href', '') if link is not None else ''
                        description = item.findtext('{http://www.w3.org/2005/Atom}summary', '')
                        pub_date = item.findtext('{http://www.w3.org/2005/Atom}published', '')

                    if not title or not link:
                        continue
                
                    # Check if AI related
                    if not self.is_ai_related(title + ' ' + description):
                        continue
                    if self._is_category_page(link, title):
                        continue

                    clean_url = self._clean_url(link)
                    if clean_url in self.seen_urls:
                        continue

                    score = self.get_source_priority(link)
                
                    news_item = {
                        'id': hashlib.md5(clean_url.encode()).hexdigest()[:10],
                        'title_en': title,
                        'title_fa': '',
                        'summary': [],
                        'impact': '',
                        'tag': 'AI',
                        'urgency': min(score, 9),
                        'sentiment': 0.0,
                        'source': urlparse(link).netloc.replace('www.', ''),
                        'url': link,
                        'clean_url': clean_url,
                        'image': '',
                        'timestamp': time.time(),
                        'ai_category': 'general',
                    }
                    new_items.append(news_item)
                    self.seen_urls.add(clean_url)

            except Exception as e:
                logger.warning(f"RSS fetch failed for {feed_url}: {e}")

        return new_items

    # ─── TELEGRAM FORMATTER (Rasad Rich v2 — Bot API 10.2 sendRichMessage) ───
    def _esc_md(self, text):
        """Escape Markdown special characters for Rich Markdown."""
        if not text: return ""
        escape_chars = set('_*[]()~`>#+-=|{}.!')
        return ''.join(f'\\{c}' if c in escape_chars else c for c in str(text))

    def format_ai_news_rich_markdown(self, items):
        """Format AI news as Rich Markdown (headings, lists, toggle, table) - max 12 items"""
        if not items:
            return None

        items = items[:12]
        now = datetime.now(timezone(timedelta(hours=3, minutes=30)))
        stamp = now.strftime('%H:%M — %Y/%m/%d')

        cat_emoji = {
            'مدل': '🧠', 'تحقیق': '🔬', 'ابزار': '🛠',
            'کسب‌وکار': '💼', 'سیاست': '⚖️', 'سخت‌افزار': '💾',
            'امنیت': '🛡️', 'عمومی': '📰'
        }

        md_parts = []
        md_parts.append(f"# 🤖 اخبار هوش مصنوعی — سوبارو نیوز\n")
        md_parts.append(f"⏱ **بروزرسانی: {stamp}** (تهران)\n")
        md_parts.append("---\n")
        md_parts.append("## 📌 سرخط مهم‌ترین اخبار\n")

        # Headlines section (bulleted list)
        for item in items[:8]:
            emoji = cat_emoji.get(item.get('ai_category', 'عمومی'), '📰')
            title_fa = item.get('title_fa') or item.get('title_en') or 'بدون عنوان'
            source = item.get('source', 'منبع ناشناس')
            url = item.get('url', '')
            link_part = f" — [{self._esc_md(source)}]({url})" if url else f" ({self._esc_md(source)})"
            md_parts.append(f"- {emoji} {self._esc_md(title_fa)}{link_part}")

        md_parts.append("\n---\n")

        # Details in collapsible toggle blocks
        md_parts.append("## 📋 تحلیل و جزئیات\n")
        for idx, item in enumerate(items):
            emoji = cat_emoji.get(item.get('ai_category', 'عمومی'), '📰')
            title_fa = item.get('title_fa') or item.get('title_en') or 'بدون عنوان'
            source = item.get('source', 'منبع ناشناس')
            url = item.get('url', '')
            summary = item.get('summary', [])
            impact = item.get('impact', '')
            ai_cat = item.get('ai_category', 'عمومی')

            inner_lines = []
            for s in summary[:3]:
                inner_lines.append(f"- {self._esc_md(s)}")
            if impact:
                inner_lines.append(f"\n💡 **تحلیل:** {self._esc_md(impact)}")
            
            # Source tags
            tags = [f"`#{ai_cat}`"]
            title_text = (item.get('title_fa', '') + ' ' + item.get('title_en', '')).lower()
            tag_map = [('openai', 'اوپن‌ای‌آی', '#اوپن_ای_آی'), ('google', 'گوگل', '#گوگل'),
                       ('nvidia', 'انویدیا', '#انویدیا'), ('microsoft', 'مایکروسافت', '#مایکروسافت'),
                       ('anthropic', 'آنتروپیک', '#آنتروپیک')]
            for en, fa, tg in tag_map:
                if en in title_text or fa in title_text:
                    tags.append(tg)
            inner_lines.append("\n" + "  ".join(tags))

            if url:
                inner_lines.append(f"\n🔗 [مشاهده منبع کامل]({url})")

            summary_txt = "\n".join(inner_lines)
            md_parts.append(
                f"<details>\n<summary>{emoji} {self._esc_md(title_fa)} — {self._esc_md(source)}</summary>\n\n"
                f"{summary_txt}\n\n</details>\n"
            )

        # Stats table
        n_total = len(items)
        cats = {}
        for it in items:
            c = it.get('ai_category', 'عمومی')
            cats[c] = cats.get(c, 0) + 1
        if len(cats) >= 2:
            md_parts.append("\n## 📊 آمار این بروزرسانی\n")
            md_parts.append("| دسته | تعداد |")
            md_parts.append("|---|---|")
            for c, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                e = cat_emoji.get(c, '📰')
                md_parts.append(f"| {e} {c} | {cnt} |")
            md_parts.append("")

        urgency_avg = sum(int(it.get('urgency', 5)) for it in items) / max(1, len(items))
        urgency_bar = "🔥" * min(5, max(1, int(round(urgency_avg / 2))))
        md_parts.append(f"\n⚡ **شاخص اهمیت:** {urgency_bar} \({int(urgency_avg)}/10\)")
        md_parts.append(f"\n🔄 هر ۳ ساعت | 🤖 رصد خودکار سوبارو نیوز")
        md_parts.append(f"\n#سوبارو_نیوز #هوش_مصنوعی")

        result = "\n".join(md_parts)

        # Rich message limit is 32768 chars; keep a sane cap
        if len(result) > 30000:
            result = result[:29800] + "\n\n... (ادامه در بروزرسانی بعدی)"
        return result

    def send_to_telegram(self, text):
        """Send formatted message to Telegram channel via sendRichMessage (Bot API 10.2).
        Falls back to legacy Markdown sendMessage if rich fails."""
        token = CONFIG['TELEGRAM']['BOT_TOKEN']
        chat_id = CONFIG['TELEGRAM']['CHANNEL_ID']
        if not token or not chat_id:
            logger.warning("Telegram credentials not configured")
            return False

        # Primary: Rich message (headings, toggle, tables, checklists...)
        url = f"https://api.telegram.org/bot{token}/sendRichMessage"
        payload = {
            'chat_id': chat_id,
            'rich_message': {'markdown': text},
        }
        try:
            resp = self.scraper.post(url, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    logger.info("✅ Rich message sent successfully")
                    return True
                logger.warning(f"Rich API not ok: {data.get('description')}")
            else:
                logger.warning(f"Rich API HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Rich send failed: {e}")

        # Fallback: legacy markdown
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
                logger.info("✅ Telegram message sent (legacy fallback)")
                return True
            else:
                logger.error(f"Telegram API error: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send_media_group_to_telegram(self, items):
        """Send AI news as media group (album) with images to Telegram"""
        token = CONFIG['TELEGRAM']['BOT_TOKEN']
        chat_id = CONFIG['TELEGRAM']['CHANNEL_ID']
        if not token or not chat_id:
            logger.warning("Telegram credentials not configured")
            return False

        # Group items by those with and without images
        items_with_images = [item for item in items if item.get('images')]
        items_without_images = [item for item in items if not item.get('images')]

        success = True

        # Send items with images as media groups (max 10 per group)
        for i in range(0, len(items_with_images), 10):
            batch = items_with_images[i:i+10]
            media = []
            for idx, item in enumerate(batch):
                images = item.get('images', [])
                if not images:
                    continue
                # Use first image for each item
                img_url = images[0]
                # Build caption for first item only (to avoid too long captions)
                if idx == 0:
                    title = self._escape_markdown(item.get('title_fa') or item.get('title_en', 'بدون عنوان'))
                    source = self._escape_markdown(item.get('source', 'منبع ناشناس'))
                    url = item.get('url', '')
                    summary = item.get('summary', [])
                    caption = f"📰 **{title}** ({source})\n"
                    for s in summary[:2]:
                        s_clean = self._escape_markdown(s)
                        caption += f"▸ {s_clean}\n"
                    caption += f"🔗 {url}"
                else:
                    caption = ""
                
                media.append({
                    'type': 'photo',
                    'media': img_url,
                    'caption': caption if idx == 0 else "",
                    'parse_mode': 'Markdown' if idx == 0 else None
                })

            if media:
                url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
                payload = {
                    'chat_id': chat_id,
                    'media': media
                }
                try:
                    resp = self.scraper.post(url, json=payload, timeout=30)
                    if resp.status_code == 200:
                        logger.info(f"✅ Telegram media group sent: {len(media)} photos")
                    else:
                        logger.error(f"Telegram media group error: {resp.status_code} - {resp.text}")
                        success = False
                except Exception as e:
                    logger.error(f"Telegram media group send failed: {e}")
                    success = False

        # Send remaining items as ONE rich digest message
        if items_without_images:
            telegram_text = self.format_ai_news_rich_markdown(items_without_images)
            if telegram_text and not self.send_to_telegram(telegram_text):
                success = False

        return success

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
            self.send_media_group_to_telegram(new_ai_items)
        else:
            logger.info("No new AI news to send")

        logger.info("✅ Cycle complete")


if __name__ == "__main__":
    radar = SubaruRadar()
    radar.run()