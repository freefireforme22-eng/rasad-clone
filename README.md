# Rasad News Radar - Starter Kit

یک کلون ساده‌شده از **رصد نیوز** برای پایش اخبار ایران، با:
- **دیتا در GitHub Pages** (JSON files)
- **GitHub Actions** برای اتوماسیون هر ۱۵ دقیقه
- **سایت SPA** با Tailwind + Vazirmatn
- **تلگرام بات** برای ارسال اخبار فوری

## 🚀 راه‌اندازی سریع

### ۱. Fork و Clone
```bash
git clone https://github.com/YOUR_USERNAME/rasad-clone
cd rasad-clone
```

### ۲. GitHub Secrets تنظیم کن
در Settings → Secrets → Actions اضافه کن:
| Secret | مقدار |
|--------|-------|
| `TG_BOT_TOKEN` | توکن ربات تلگرام (از @BotFather) |
| `TG_CHANNEL_ID` | آیدی عددی کانال (مثلا `-1001234567890`) |

### ۳. GitHub Pages فعال کن
Settings → Pages → Source: **GitHub Actions**

### ۴. Workflow رو اجرا کن
Actions → "Rasad News Radar" → Run workflow

### ۵. آدرس سایت
`https://YOUR_USERNAME.github.io/rasad-clone/`

## 📁 ساختار پروژه

```
rasad-clone/
├── data/                    # فایل‌های JSON (روی GitHub Pages سرو میشن)
│   ├── market.json          # دلار، نفت، آپدیت
│   ├── news.json            # آرایه اخبار
│   ├── special_reports.json # گزارش‌های تحلیلی عمیق
│   ├── daily_summary.json   # جمع‌بندی روزانه
│   └── bulletins.json       # بولتن صبح/شام
├── scripts/
│   └── main.py              # موتور اصلی (Python)
├── site/
│   └── index.html           # سایت SPA
├── .github/workflows/
│   └── radar.yml            # اتوماسیون هر ۱۵ دقیقه
└── requirements.txt
```

## ⚙️ کامپوننت‌های اصلی

### 1. Market Data (`scripts/main.py`)
```python
def fetch_market_rates(self):
    # دلار از alanchand.com
    # نفت از oilprice.com
    # آپدیت هر ۱۵ دقیقه
```

### 2. News Pipeline (Placeholder)
```python
def fetch_news(self):
    # TODO: Integrate DDGS + trafilatura + AI analysis
    # 1. Search queries (GNews/DDGS)
    # 2. Extract content (trafilatura)
    # 3. AI analysis (Pollinations/OpenAI)
    # 4. Deduplication (fuzzy matching)
    # 5. Save to news.json
```

### 3. Telegram Bot
```python
# send_digest_to_telegram() - اخبار فوری (urgency >= 7)
# send_daily_summary_to_telegram() - جمع‌بندی روزانه
# send_bulletin_to_telegram() - بولتن صبح/شام
```

### 4. Website (`site/index.html`)
- Market header (دلار، نفت، BTC، ساعت‌های زنده)
- Category filters (تشدید، نظامی، اقتصادی، دیپلماسی، هسته‌ای، نیابتی، هرمز)
- Infinite scroll news feed
- Special report modal
- Dark/Light mode
- RTL + Vazirmatn font

## 🔧 توسعه بیشتر

### News Fetch کامل کردن
در `scripts/main.py`:
```python
# اضافه کن:
from ddgs import DDGS
import trafilatura
# یا از Pollinations/OpenAI برای تحلیل
```

### AI Analysis با Pollinations (رایگان)
```python
async def analyze_with_ai(text):
    prompt = f"خبر رو تحلیل کن و JSON برگردان: {text[:2000]}"
    # call Pollinations API
```

### موارد پیشرفته (از رصد نیوز اصلی)
- `special_reports.json` با `key_findings`, `regime_vs_reality`, `strategic_outlook`
- `daily_summary.json` با `probability_matrix`, `forecast`
- `bulletins.json` صبح/شام
- Proxy rotation برای اسکراپینگ
- Service Worker (PWA)

## 📝 نکات مهم

1. **USERNAME/REPO** در `site/index.html` رو با یوزر/ریپوی خودت جایگزین کن
2. **Rate limits**: GitHub Actions ۱۵ دقیقه یکبار، APIهای خارجی مراقب باش
3. **Deduplication**: فازی متچینگ روی عنوان (token overlap > 50%)
4. **Images**: فیلتر googleusercontent، tbn، gstatic
5. **Persian digits**: از Vazirmatn-FD استفاده شده

## 📄 License
MIT - آزاد برای استفاده و توسعه

---

**ساخته شده با ❤️ برای فلوگل-کون** (◕‿◕)♡ ★彡 ~nya!