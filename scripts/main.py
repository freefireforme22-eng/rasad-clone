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
        'https://blog.anthropic.com/rss/',
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
        """Use Pollinations AI to enrich news with Persian titles, summaries, categories.
        Falls back to local generation if API fails."""
        if not items: return items

        for item in items:
            enriched = False
            try:
                prompt = f"""این خبر هوش مصنوعی رو تحلیل کن و فقط JSON برگردان:
عنوان: {item['title_en']}
منبع: {item['source']}
لینک: {item['url']}

فیلدهای خروجی (همه به فارسی، کلمات انگلیسی به تلفظ فارسی):
- title_fa: عنوان فارسی (ماکس ۸۰ کاراکتر)
- summary: ۲-۳ نکته کلیدی به فارسی (فقط کلمات فارسی، انگلیسی‌ها به تلفظ فارسی مثل: ماشین لرنینگ، ال‌ام‌ال، جی‌پی‌یو، اوپن‌ای‌آی)
- impact: تحلیل اهمیت به فارسی (یک خط)
- ai_category: یکی از [مدل، تحقیق، ابزار، کسب‌وکار، سیاست، سخت‌افزار، امنیت]
- sentiment: -۱ تا ۱ (منفی تا مثبت)
- urgency: ۱-۹ (خبر فوری=۹، مهم=۷، معمولی=۵)

فقط JSON خالص، بدون متن اضافی، بدون مارک‌داون."""
                pollinations_url = "https://text.pollinations.ai/openai"
                payload = {
                    "messages": [{"role": "user", "content": prompt}],
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "max_tokens": 600,
                }
                resp = self.scraper.post(pollinations_url, json=payload, timeout=90)
                if resp.status_code == 200:
                    result = resp.json()
                    content = result.get('choices', [{}])[0].get('message', {}).get('content', '{}')
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        ai_data = json.loads(json_match.group())
                        item['title_fa'] = ai_data.get('title_fa', item['title_en'])
                        item['summary'] = ai_data.get('summary', [])
                        item['impact'] = ai_data.get('impact', '')
                        item['ai_category'] = ai_data.get('ai_category', 'عمومی')
                        item['sentiment'] = ai_data.get('sentiment', 0.0)
                        item['urgency'] = ai_data.get('urgency', item['urgency'])
                        enriched = True
            except Exception as e:
                logger.warning(f"AI enrichment failed for {item['url']}: {e}")

            # Fallback: local Persian generation
            if not enriched:
                item['title_fa'] = self._generate_persian_title(item['title_en'])
                item['summary'] = self._generate_persian_summary(item['title_en'], item['source'])
                item['impact'] = self._generate_persian_impact(item['title_en'])
                item['ai_category'] = self._guess_category(item['title_en'])
                item['sentiment'] = 0.1
                item['urgency'] = item.get('urgency', 6)

        return items

    def _generate_persian_title(self, title_en):
        """Generate Persian title with English terms in parentheses"""
        # Keyword mapping: Persian (English) format
        replacements = {
            'AI': 'هوش مصنوعی (AI)', 'Artificial Intelligence': 'هوش مصنوعی (AI)',
            'Machine Learning': 'ماشین لرنینگ (Machine Learning)', 'Deep Learning': 'دیپ لرنینگ (Deep Learning)',
            'LLM': 'ال‌ام‌ال (LLM)', 'Large Language Model': 'مدل زبانی بزرگ (LLM)',
            'GPT': 'جی‌پی‌یو (GPT)', 'Generative AI': 'هوش مصنوعی مولد (Generative AI)',
            'OpenAI': 'اوپن‌ای‌آی (OpenAI)', 'Anthropic': 'آنتروپیک (Anthropic)',
            'Google': 'گوگل (Google)', 'DeepMind': 'دیپ‌مایند (DeepMind)',
            'Meta': 'مِتا (Meta)', 'Microsoft': 'مایکروسافت (Microsoft)',
            'NVIDIA': 'انویدیا (NVIDIA)', 'GPU': 'جی‌پی‌یو (GPU)',
            'Model': 'مدل (Model)', 'Release': 'انتشار (Release)', 'Launch': 'راه‌اندازی (Launch)',
            'Research': 'تحقیق (Research)', 'Paper': 'مقاله (Paper)', 'Study': 'مطالعه (Study)',
            'Benchmark': 'بنچ‌مارک (Benchmark)', 'Training': 'آموزش (Training)',
            'Agent': 'عامل (Agent)', 'Tool': 'ابزار (Tool)', 'API': 'ای‌پی‌آی (API)',
            'Open Source': 'بازمتن (Open Source)', 'Coding': 'کدنویسی (Coding)',
            'Safety': 'امنیت (Safety)', 'Regulation': 'تنظیمات (Regulation)',
            'Chip': 'تراشه (Chip)', 'Hardware': 'سخت‌افزار (Hardware)',
            'Funding': 'سرمایه‌گذاری (Funding)', 'Investment': 'سرمایه‌گذاری (Investment)',
            'Startup': 'استارتاپ (Startup)', 'Company': 'شرکت (Company)',
            'News': 'اخبار (News)', 'Latest': 'جدیدترین (Latest)', 'Insights': 'بینش‌ها (Insights)',
            'Analysis': 'تحلیل (Analysis)', 'Powering': 'قدرت‌بخشی به (Powering)', 'Driven': 'مبتنی بر (Driven)',
            'Business': 'کسب‌وکار (Business)', 'Growth': 'رشد (Growth)', 'Headlines': 'سرتیترها (Headlines)',
            'Developments': 'توسعه‌ها (Developments)', 'Updates': 'به‌روزرسانی‌ها (Updates)',
            'Artificial': 'مصنوعی (Artificial)', 'Intelligence': 'هوش (Intelligence)',
            'Technology': 'تکنولوژی (Technology)', 'Tech': 'تک (Tech)',
            'Annual': 'سالانه (Annual)', 'Report': 'گزارش (Report)', 'Review': 'بررسی (Review)',
            'Guide': 'راهنما (Guide)', 'Tutorial': 'آموزش (Tutorial)', 'Explained': 'توضیح داده شده (Explained)',
            'Embedding': 'امبدینگ (Embedding)', 'Vector': 'برداری (Vector)', 'Multi-Vector': 'چند برداری (Multi-Vector)',
            'Sentence': 'جمله (Sentence)', 'Transformer': 'ترنسفورمر (Transformer)', 'Transformers': 'ترنسفورمرها (Transformers)',
            'Late Interaction': 'تعامل دیرهنگام (Late Interaction)', 'Decoder': 'دی‌کدر (Decoder)',
            'Claude': 'کلود (Claude)', 'Gemini': 'جمینی (Gemini)', 'Llama': 'لاما (Llama)', 'Mistral': 'مِیسترال (Mistral)',
            'RAG': 'رگ (RAG)', 'RAG': 'RAG', 'Fine-tuning': 'فاین‌تیونینگ (Fine-tuning)',
            'Inference': 'استنتاج (Inference)', 'Prompt': 'پرامپت (Prompt)', 'Prompting': 'پرامپتینگ (Prompting)',
            'Context': 'بافت (Context)', 'Attention': 'توجه (Attention)', 'Attention Mechanism': 'مکانیزم توجه (Attention Mechanism)',
            'Neural Network': 'شبکه عصبی (Neural Network)', 'Parameters': 'پارامترها (Parameters)',
            'Tokens': 'توکن‌ها (Tokens)', 'Dataset': 'دیتاست (Dataset)', 'Benchmark': 'بنچ‌مارک (Benchmark)',
            'Open-weight': 'باز‌وزن (Open-weight)', 'Open-weight Model': 'مدل باز‌وزن (Open-weight Model)',
            'Nous Research': 'نوس ریسرچ (Nous Research)', 'NousCoder': 'نوس‌کدر (NousCoder)',
            'Salesforce': 'سیِلزفورس (Salesforce)', 'Slackbot': 'اسلک‌بات (Slackbot)', 'Cowork': 'کاوورک (Cowork)',
            'Railway': 'ریلوِی (Railway)', 'AWS': 'ا‌دابلیو‌اس (AWS)', 'Cloud': 'کلاد (Cloud)',
            'Infrastructure': 'زیرساخت (Infrastructure)', 'Workspace': 'ورک‌اسپیس (Workspace)',
            'Desktop': 'دسکتاپ (Desktop)', 'Files': 'فایل‌ها (Files)', 'Coding': 'کدنویسی (Coding)',
            'Decodability': 'کدپذیری (Decodability)', 'Hidden State': 'حالت پنهان (Hidden State)',
            'Majority Voting': 'رأی‌گیری اکثریت (Majority Voting)', 'Selection': 'انتخاب (Selection)',
            'Prediction': 'پیش‌بینی (Prediction)', 'Road Safety': 'ایمنی راه (Road Safety)',
            'Intervention': 'مداخله (Intervention)', 'Driving': 'رانندگی (Driving)', 'Hotspots': 'هات‌اسپات‌ها (Hotspots)',
            'Connected Vehicle': 'خودرو متصل (Connected Vehicle)', 'Data': 'دیتا (Data)',
            'Classical': 'کلاسیک (Classical)', 'Transformer-based': 'ترنسفورمر-بیس (Transformer-based)',
            'Document': 'سند (Document)', 'Sensitivity': 'حساسیت (Sensitivity)', 'Classification': 'طبقه‌بندی (Classification)',
            'Daily-Scale': 'روزانه (Daily-Scale)', 'Longitudinal': 'طی‌دراز (Longitudinal)', 'Multimodal': 'چند حالته (Multimodal)',
            'Readmission': 'بازآسپذیری (Readmission)', 'Margin-Regularized': 'مرز-منظم‌شده (Margin-Regularized)',
            'Structured': 'ساختاریافته (Structured)', 'Semantic': 'سمنتیک (Semantic)', 'Alignment': 'الاینمنت (Alignment)',
            'Brain': 'مغز (Brain)', 'Language': 'زبان (Language)', 'Correspondence': 'همبستگی (Correspondence)',
            'Cross-Model': 'کراس-مدل (Cross-Model)', 'Memory': 'حافظه (Memory)', 'Transfer': 'ترنسفر (Transfer)',
            'Target-Side': 'هدف-سمت (Target-Side)', 'Reader': 'ریدر (Reader)', 'Adaptation': 'آدابتیشن (Adaptation)',
            'Institution-Specific': 'مؤسسه-مخصوص (Institution-Specific)', 'PHI': 'فی‌آی‌اچ (PHI)',
            'De-identification': 'دی‌آی‌نتیفیکیشن (De-identification)', 'Gold Standards': 'استانداردهای طلایی (Gold Standards)',
            'Uncertainty': 'عدم اطمینان (Uncertainty)', 'Decision Making': 'تصمیم‌گیری (Decision Making)',
            'Safer': 'امن‌تر (Safer)', 'Agents': 'عامل‌ها (Agents)', 'Capable': 'قادر (Capable)',
            'System 2': 'سیستم ۲ (System 2)', 'Thinking': 'تفکر (Thinking)', 'Access': 'دسترسی (Access)',
            'Untrusted': 'غیرموثوق (Untrusted)', 'Documents': 'اسناد (Documents)',
        }
        fa_title = title_en
        # Sort by length descending to avoid partial replacements
        for en, fa in sorted(replacements.items(), key=lambda x: -len(x[0])):
            fa_title = fa_title.replace(en, fa)
        # Truncate
        if len(fa_title) > 120:
            fa_title = fa_title[:117] + '...'
        return fa_title

    def _generate_persian_summary(self, title_en, source):
        """Generate Persian summary points with English terms in parentheses"""
        summaries = []
        title_lower = title_en.lower()
    
        if any(kw in title_lower for kw in ['release', 'launch', 'announce', 'unveil']):
            summaries.append("نسخه جدید (Release) منتشر و در دسترس عموم قرار گرفته")
        if any(kw in title_lower for kw in ['model', 'llm', 'gpt', 'claude', 'gemini', 'llama']):
            summaries.append("مدل هوش مصنوعی (AI Model) با قابلیت‌های پیشرفته معرفی شده")
        if any(kw in title_lower for kw in ['open source', 'open-source']):
            summaries.append("این پروژه به صورت بازمتن (Open Source) منتشر شده و قابل استفاده رایگان است")
        if any(kw in title_lower for kw in ['funding', 'investment', 'million', 'billion', 'raises']):
            summaries.append("سرمایه‌گذاری جدید (Funding) برای توسعه تکنولوژی‌های هوش مصنوعی انجام شده")
        if any(kw in title_lower for kw in ['research', 'paper', 'study', 'arxiv', 'benchmark']):
            summaries.append("نتایج پژوهشی جدید (Research) در مورد عملکرد و قابلیت‌های مدل‌ها منتشر شده")
        if any(kw in title_lower for kw in ['agent', 'tool', 'api', 'coding']):
            summaries.append("ابزار یا عامل هوش مصنوعی (AI Agent/Tool) جدید برای توسعه‌دهندگان عرضه شده")
        if any(kw in title_lower for kw in ['safety', 'security', 'privacy', 'regulation']):
            summaries.append("مسائل امنیتی و اخلاقی (Safety/Ethics) در توسعه هوش مصنوعی مورد بررسی قرار گرفته")
        if any(kw in title_lower for kw in ['chip', 'gpu', 'hardware', 'nvidia']):
            summaries.append("پیشرفت در سخت‌افزار (Hardware) و تراشه‌های مخصوص هوش مصنوعی گزارش شده")
    
        if not summaries:
            summaries = [
                "پیشرفت جدید در حوزه هوش مصنوعی (AI) گزارش شده",
                "تأثیر این توسعه بر صنعت و کاربران مورد تحلیل قرار گرفته"
            ]
    
        return summaries[:3]

    def _generate_persian_impact(self, title_en):
        """Generate Persian impact analysis with English terms in parentheses"""
        title_lower = title_en.lower()
    
        if any(kw in title_lower for kw in ['openai', 'anthropic', 'google', 'deepmind', 'meta', 'microsoft']):
            return "شرکت‌های بزرگ تکنولوژی (Big Tech) پیشروی در توسعه هوش مصنوعی (AI) را ادامه می‌دهند"
        if any(kw in title_lower for kw in ['open source', 'open-source']):
            return "بازمتن بودن این پروژه (Open Source) نوآوری و دسترسی گسترده را تسریع می‌کند"
        if any(kw in title_lower for kw in ['funding', 'investment', 'million', 'billion']):
            return "جذب سرمایه (Funding) نشان‌دهنده اعتماد بازار به آینده هوش مصنوعی (AI) است"
        if any(kw in title_lower for kw in ['research', 'paper', 'arxiv', 'study']):
            return "پیشرفت‌های علمی (Research) پایه برای کاربردهای آینده فراهم می‌آورند"
    
        return "این توسعه می‌تواند بر روندهای آینده هوش مصنوعی (AI) تأثیر بگذارد"

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

    # ─── TELEGRAM FORMATTER (Rasad-style) ───
    def _escape_markdown(self, text):
        """Escape Markdown special characters"""
        if not text: return ""
        # Escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{c}' if c in escape_chars else c for c in text)

    def format_ai_news_for_telegram(self, items):
        """Format AI news in Rasad-style for Telegram (full Persian)"""
        if not items: return ""

        lines = ["🤖 **اخبار هوش مصنوعی - سوبارو نیوز**", ""]

        for item in items:
            cat_emoji = {
                'مدل': '🧠', 'تحقیق': '🔬', 'ابزار': '🛠',
                'کسب‌وکار': '💼', 'سیاست': '⚖️', 'سخت‌افزار': '💾',
                'امنیت': '🛡️', 'عمومی': '📰'
            }.get(item.get('ai_category', 'عمومی'), '📰')

            title = self._escape_markdown(item.get('title_fa') or item.get('title_en', 'بدون عنوان'))
            source = self._escape_markdown(item.get('source', 'منبع ناشناس'))
            url = item.get('url', '')
            ai_cat = item.get('ai_category', 'عمومی')

            # Summary
            summary = item.get('summary', [])
            if summary:
                for s in summary:
                    s_clean = self._escape_markdown(s)
                    lines.append(f"▸ {s_clean}")

            # Impact
            impact = item.get('impact', '')
            if impact:
                lines.append(f"💡 {self._escape_markdown(impact)}")

            # Source and link
            lines.append(f"📰 منبع: {source}")
            lines.append(f"🔗 {url}")

            # Hashtags (Persian)
            tags = ['#هوش_مصنوعی', f'#{ai_cat}']
            title_text = (item.get('title_fa', '') + ' ' + item.get('title_en', '')).lower()
            if 'openai' in title_text or 'اوپن‌ای‌آی' in title_text:
                tags.append('#اوپن_ای_آی')
            if 'google' in title_text or 'گوگل' in title_text:
                tags.append('#گوگل')
            if 'nvidia' in title_text or 'انویدیا' in title_text:
                tags.append('#انویدیا')
            if 'مایکروسافت' in title_text or 'microsoft' in title_text:
                tags.append('#مایکروسافت')

            lines.append(f"{' '.join(tags)}")
            lines.append("━━━━━━━━━━━━━━━━")

        lines.append("")
        lines.append(f"⏰ آپدیت: {datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime('%H:%M')} | 🔄 هر ۳ ساعت")
        lines.append("#سوبارو_نیوز #هوش_مصنوعی #AI")

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