#!/usr/bin/env python3
"""
Subaru News — Feature Pack v1 (15 features)
Loaded by scripts/main.py at runtime. All Persian, all rich-formatted.
"""
import os
import re
import json
import time
import hashlib
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("subaru.features")

TEHRAN = timezone(timedelta(hours=3, minutes=30))

# ─── helpers ─────────────────────────────────────────────────────────

def _now():
    return datetime.now(TEHRAN)

def _data_path(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', name)

def _load_json(name, default):
    try:
        with open(_data_path(name), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(name, obj):
    try:
        with open(_data_path(name), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"save {name}: {e}")

def esc(t):
    if not t: return ""
    out = []
    for c in str(t):
        out.append(f'\\{c}' if c in set('_*[]()~`>#+-=|{}.!') else c)
    return ''.join(out)


class SubaruFeatures:
    """15 premium features layered onto the news pipeline."""

    def __init__(self, radar=None):
        self.radar = radar
        # persistent state
        self.reactions   = _load_json('f_reactions.json', {})    # F1 message->stats
        self.reading_log = _load_json('f_reading_log.json', [])  # F2 what was sent when
        self.stats       = _load_json('f_stats.json', {})        # F10 aggregate stats
        self.muted_cats  = set(_load_json('f_muted.json', []))   # F13 user-muted categories
        self.bookmarks   = _load_json('f_bookmarks.json', [])    # F14 saved items
        self.glossary    = _load_json('f_glossary.json', {})     # F9 term -> explanation

    # ── F1: sentiment & tone analysis ────────────────────────────────
    POS_WORDS = ('شکست', 'موفق', 'پیشرفت', 'بهبود', 'رکورد', 'برتری', 'نوآوری', 'عرضه', 'همکاری', 'سرمایه')
    NEG_WORDS = ('تحریم', 'حمله', 'خطر', 'افول', 'اختلاف', 'جعل', 'تقلب', 'مرگ', 'بحران', 'شکایت')

    def analyze_sentiment(self, text):
        """Returns (score -1..+1, emoji)."""
        tl = (text or '').lower()
        pos = sum(w in tl for w in self.POS_WORDS)
        neg = sum(w in tl for w in self.NEG_WORDS)
        if pos + neg == 0:
            return 0.0, '😐'
        score = (pos - neg) / max(1, pos + neg)
        emoji = '😊' if score > 0.25 else '😟' if score < -0.25 else '😐'
        return round(score, 2), emoji

    # ── F2: reading-time estimate ────────────────────────────────────
    def reading_minutes(self, item):
        words = len(((item.get('article_content') or '') + ' ' + ' '.join(item.get('summary', []))).split())
        return max(1, round(words / 180))  # ~180 wpm

    # ── F3: auto TL;DR (first meaningful sentence compressed) ───────
    def tldr(self, item):
        content = (item.get('article_content') or '').strip()
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', content) if len(s.strip()) > 40]
        if not sents:
            for s in item.get('summary', []):
                if len(s) > 40 and 'گزارش شده' not in s:
                    return s[:140]
            return 'خبری کوتاه؛ جزئیات در منبع.'
        best = min(sents[:5], key=lambda s: len(s))
        return best[:160]

    # ── F4: smart hashtags from content ─────────────────────────────
    HASHTAG_MAP = [
        ('openai', '#اوپن‌ای‌آی'), ('anthropic', '#آنتروپیک'), ('claude', '#کلود'),
        ('gemini', '#جمینی'), ('gpt', '#جی‌پی‌تی'), ('llama', '#لاما'),
        ('nvidia', '#انویدیا'), ('gpu', '#جی‌پی‌یو'), ('chip', '#تراشه'),
        ('robot', '#رباتیک'), ('quantum', '#کوانتوم'), ('security', '#امنیت'),
        ('regulation', '#قانون‌گذاری'), ('funding', '#سرمایه‌گذاری'),
        ('benchmark', '#بنچ‌مارک'), ('agent', '#عامل_هوشمند'), ('rag', '#رگ'),
        ('image', '#تصویری'), ('video', '#ویدیویی'), ('voice', '#صوتی'),
    ]

    def smart_hashtags(self, item):
        blob = ((item.get('title_en') or '') + ' ' + (item.get('article_content') or '')[:800]).lower()
        tags = []
        for kw, tag in self.HASHTAG_MAP:
            if kw in blob and tag not in tags:
                tags.append(tag)
        cat = item.get('ai_category', '')
        if cat and f'#{cat}' not in tags:
            tags.insert(0, f'#{esc(cat)}')
        return tags[:4]

    # ── F5: trending topics across the batch ────────────────────────
    def trending_topics(self, items, top=6):
        freq = {}
        stop = {'این','آن','با','از','به','که','در','است','برای','روی','یک','های','می','شود','کرد','شده',
                   'the','and','for','with','that','this','from','sources','source','artificial',
                   'intelligence','research','news','update','updates','latest','today','yesterday',
                   'about','into','your','have','been','will','more','than','were','their','other',
                   'which','using','based','model','models','learning','machine','what','when','hours','ago'}
        extra_stop_file = _data_path('f_trending_stop.json')
        try:
            for w in _load_json('f_trending_stop.json', []):
                stop.add(w.lower())
        except Exception:
            pass
        for it in items:
            blob = ((it.get('title_en') or '') + ' ' + (it.get('article_content') or '')[:600]).lower()
            words = re.findall(r'[a-zA-Z؀-ۿ]{4,}', blob)
            for w in words:
                if w not in stop:
                    freq[w] = freq.get(w, 0) + 1
        ranked = [(w,c) for w,c in sorted(freq.items(), key=lambda x: -x[1]) if c >= 2][:top]
        tr = getattr(self.radar, '_translate_fa', None) if self.radar else None
        out = []
        for w, c in ranked:
            fa = tr(w.capitalize()) if (tr and w.isascii()) else w
            out.append((fa, c))
        return out

    # ── F6: hotness score (urgency × source × freshness) ────────────
    def hotness(self, item):
        try:
            u = int(item.get('urgency', 5))
        except (TypeError, ValueError):
            u = 5
        sp = self.radar.get_source_priority(item.get('url','')) if self.radar else 5
        ts = item.get('timestamp', 0)
        age_h = max(0, (_now().timestamp() - ts) / 3600) if ts else 12
        fresh = max(0, 24 - age_h) / 24          # 0..1
        return round(u * 0.5 + sp * 0.35 + fresh * 10 * 0.15, 1)

    def heat_bar(self, item):
        h = self.hotness(item)
        n = max(1, min(5, int(round(h / 2))))
        return '🔥' * n + ('·' * (5 - n))

    # ── F7: duplicate-cluster flagger ───────────────────────────────
    def dedupe_near(self, items):
        """Mark near-duplicates (same story from different outlets)."""
        seen_sig = {}
        dup_ids = set()
        for i, it in enumerate(items):
            title = (it.get('title_en') or it.get('title_fa') or '').lower()
            sig = hashlib.md5(re.sub(r'\W+', '', title)[:60].encode()).hexdigest()[:8]
            words = frozenset(w for w in re.findall(r'\w{5,}', title) if len(w) > 4)
            hit = None
            for prev_sig, prev_words in seen_sig.items():
                overlap = len(words & prev_words[1])
                if words and overlap >= max(2, len(words) // 2):
                    hit = prev_sig
                    break
            if hit:
                dup_ids.add(i)
            else:
                seen_sig[sig] = (i, words)
        return [it for i, it in enumerate(items) if i not in dup_ids]

    # ── F8: related-news linker (within batch) ──────────────────────
    def related_links(self, item, items, k=2):
        words = set(re.findall(r'\w{5,}', ((item.get('title_en') or '') + ' ' + (item.get('article_content') or '')[:500]).lower()))
        scores = []
        for other in items:
            if other is item:
                continue
            ow = set(re.findall(r'\w{5,}', ((other.get('title_en') or '') + ' ' + (other.get('article_content') or '')[:500]).lower()))
            inter = len(words & ow)
            if inter >= 3:
                scores.append((inter, other))
        scores.sort(key=lambda x: -x[0])
        return [o for _, o in scores[:k]]

    # ── F10: daily/weekly statistics block ──────────────────────────
    def update_stats(self, items):
        today = _now().strftime('%Y-%m-%d')
        st = self.stats
        day = st.setdefault(today, {'count': 0, 'cats': {}, 'sources': {}, 'heat': 0})
        day['count'] += len(items)
        for it in items:
            c = it.get('ai_category', 'عمومی')
            day['cats'][c] = day['cats'].get(c, 0) + 1
            s = it.get('source', '?')
            day['sources'][s] = day['sources'].get(s, 0) + 1
            day['heat'] += self.hotness(it)
        # keep last 30 days
        keys = sorted(st.keys())[-30:]
        self.stats = {k: st[k] for k in keys}
        _save_json('f_stats.json', self.stats)

    def stats_block_md(self, items):
        today = _now().strftime('%Y-%m-%d')
        week_items = sum(v.get('count', 0) for k, v in self.stats.items()
                         if (today[:8]) in k)
        cats = {}
        srcs = {}
        for it in items:
            c = it.get('ai_category', 'عمومی'); cats[c] = cats.get(c, 0) + 1
            s = it.get('source', '?'); srcs[s] = srcs.get(s, 0) + 1
        top_src = sorted(srcs.items(), key=lambda x: -x[1])[:3]
        lines = ["| دسته | تعداد |", "|---|---|"]
        for c, n in sorted(cats.items(), key=lambda x: -x[1]):
            lines.append(f"| {esc(c)} | {n} |")
        md = "\n".join(lines)
        md += f"\n\n**منابع برتر این بروزرسانی:** " + "، ".join(f"{esc(s)} ({n})" for s, n in top_src)
        md += f"\n**میانگین داغی:** {round(sum(self.hotness(i) for i in items)/max(1,len(items)),1)}/۱۰"
        return md

    # ── F11: market widget (USD/oil/gold inline) ─────────────────────
    def market_widget(self):
        m = _load_json('market.json', {})
        usd = m.get('usd'); oil = m.get('oil'); gold = m.get('gold')
        parts = []
        if usd: parts.append(f"💵 دلار: `{esc(usd)}` تومان")
        if gold: parts.append(f"🥇 طلا: `{esc(gold)}`")
        if oil: parts.append(f"🛢 نفت: `{esc(oil)}`$")
        return " | ".join(parts) if parts else ""

    # ── F12: quote-of-the-day (from articles) ────────────────────────
    QUOTES = [
        ("هوش مصنوعی برقی است، نه جادویی.", "اصل مهندسی AI"),
        ("داده تازه، نفتِ مدل‌های زبانی است.", "ضرب‌المثل حوزه داده"),
        ("ساده‌ترین راه‌حلی که کار کند، بهترین معماری است.", "اصل طراحی سیستم"),
        ("هر بنچ‌مارکی که بهینه شود، دیگر معیار نیست.", "قانون گودهارت"),
    ]
    def quote_of_day(self):
        idx = int(_now().strftime('%j')) % len(self.QUOTES)
        q, by = self.QUOTES[idx]
        return f"> 💬 «{q}»\n> — {by}"

    # ── F13: category mute/unmute (reads data/f_muted.json) ──────────
    def filter_muted(self, items):
        if not self.muted_cats:
            return items
        return [i for i in items if i.get('ai_category', '') not in self.muted_cats]

    # ── F15: on-this-day / history nugget ────────────────────────────
    ON_THIS_DAY = {
        '08-23': ('۱۹۶۶', 'راه‌اندازی Lunar Orbiter 1 — اولین عکس کامل از زمین'),
        '08-24': ('۲۰۰۶', 'پلوتو از فهرست سیارات منظومه شمسی حذف شد'),
        '08-25': ('۲۰۱۲', 'وویجر ۱ به فضای بین‌ستاره‌ای رسید'),
        '08-26': ('۱۹۷۴', 'معرفی اولین پردازنده تجاری دنیا اینتل ۸۰۸۰'),
    }
    def on_this_day(self):
        key = _now().strftime('%m-%d')
        if key in self.ON_THIS_DAY:
            y, ev = self.ON_THIS_DAY[key]
            return f"📅 **چنین روزی:** در سال {y} — {ev}"
        return ""

    # ── F9: AI glossary (auto-explains jargon in toggles) ────────────
    GLOSSARY_SEED = {
        'llm': 'مدل زبانی بزرگ؛ شبکه عصبی که روی حجم عظیمی از متن آموزش دیده',
        'rag': 'تولید تقویت‌شده با بازیابی؛ اتصال مدل به اسناد بیرونی برای پاسخ دقیق‌تر',
        'benchmark': 'آزمون استاندارد برای مقایسه عملکرد مدل‌ها',
        'agent': 'برنامه هوشمندی که خودش برنامه‌ریزی و ابزار به‌کار می‌گیرد',
        'fine-tuning': 'آموزش تکمیلی مدل روی داده تخصصی',
        'token': 'قطعه کوچک متن؛ واحد پردازش و صورت‌حساب مدل‌ها',
        'multimodal': 'مدلی که هم متن، هم تصویر/صدا را می‌فهمد',
        'inference': 'مرحله استفاده از مدلِ آموزش‌دیده برای تولید پاسخ',
    }
    def explain_term(self, text):
        tl = (text or '').lower()
        for term, expl in self.GLOSSARY_SEED.items():
            if term in tl:
                return f"📚 **{term} چیست؟** {expl}"
        return ""

    # ── F14: bookmarks (persist items flagged interesting) ───────────
    def bookmark(self, item):
        url = item.get('url', '')
        if not url or any(b.get('url') == url for b in self.bookmarks):
            return False
        self.bookmarks.append({
            'title': item.get('title_fa') or item.get('title_en', ''),
            'url': url,
            'ts': _now().isoformat(),
            'hotness': self.hotness(item),
        })
        self.bookmarks = sorted(self.bookmarks, key=lambda b: -b['hotness'])[:50]
        _save_json('f_bookmarks.json', self.bookmarks)
        return True

    def bookmarks_md(self, k=5):
        lines = []
        for b in self.bookmarks[:k]:
            lines.append(f"- [{esc(b['title'][:60])}]({b['url']}) — 🔥{b['hotness']}")
        return "\n".join(lines) if lines else "- هنوز خبری ذخیره نشده"

    # ── Weekly digest builder (F-weekly) ─────────────────────────────
    def weekly_digest_md(self):
        today = _now()
        week_ago = today - timedelta(days=7)
        items = [i for i in _load_json('ai_news.json', [])
                 if datetime.fromtimestamp(i.get('timestamp', 0), TEHRAN) >= week_ago]
        if not items:
            return None
        top = sorted(items, key=self.hotness, reverse=True)[:7]
        md = ["# 📅 گزارش هفتگی هوش مصنوعی", ""]
        md.append(f"⏱ **هفته منتهی به {today.strftime('%Y/%m/%d')}**")
        md.append(f"📊 مجموع اخبار: **{len(items)}** مورد\n")
        md.append("## 🏆 داغ‌ترین اخبار هفته\n")
        for i, it in enumerate(top, 1):
            t = it.get('title_fa') or it.get('title_en') or 'بدون عنوان'
            u = it.get('url', '')
            link = f"[{esc(t[:70])}]({u})" if u else esc(t[:70])
            md.append(f"{i}. {link} — 🔥{self.hotness(it)}")
        trend = self.trending_topics(items, top=8)
        if trend:
            md.append("\n## 📈 موضوعات داغ هفته\n")
            md.append(" · ".join(f"**{esc(t)}** ×{c}" for t, c in trend))
        md.append("\n#گزارش_هفتگی #هوش_مصنوعی")
        return "\n".join(md)
