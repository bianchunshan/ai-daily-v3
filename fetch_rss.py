#!/usr/bin/env python3
"""
RSS 抓取(免费、无配额、无 key)。解析国际科技媒体 RSS/Atom,返回英文新闻列表。
仅用标准库。供 enrich_news.py 调用(再交给 Qwen 翻译富化)。
"""

import re
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# RSS 源(source 名 + 默认分类兜底,真正分类由 Qwen 判定)。国际源需翻译,中文源直接用。
FEEDS = [
    # 国际源
    ("TechCrunch", "https://techcrunch.com/feed/", "人工智能"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "消费电子"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "前沿科技"),
    ("Wired", "https://www.wired.com/feed/rss", "前沿科技"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/", "人工智能"),
    ("Engadget", "https://www.engadget.com/rss.xml", "消费电子"),
    ("Hacker News", "https://hnrss.org/frontpage", "前沿科技"),
    ("Tom's Hardware", "https://www.tomshardware.com/feeds/all", "人工智能"),
    ("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "人工智能"),
    ("SpaceNews", "https://spacenews.com/feed/", "商业航天"),
    # 国际局势 / 世界新闻(补美伊、地缘等)
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "国际局势"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "国际局势"),
    ("BBC中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml", "国际局势"),
    # 小众板块对口源(补量子/机器人/能源/航天/生物)
    ("Quanta", "https://api.quantamagazine.org/feed/", "量子科技"),
    ("The Robot Report", "https://www.therobotreport.com/feed/", "机器人"),
    ("Electrek", "https://electrek.co/feed/", "未来能源"),
    ("Space.com", "https://www.space.com/feeds/all", "商业航天"),
    ("ScienceDaily", "https://www.sciencedaily.com/rss/top/science.xml", "量子科技"),
    ("MedicalXpress", "https://medicalxpress.com/rss-feed/", "生物医药"),
    # 中文源(本身中文,Qwen 跳过翻译只做整理/分类/标的)
    ("36氪", "https://36kr.com/feed", "前沿科技"),
    ("量子位", "https://www.qbitai.com/feed", "人工智能"),
    ("IT之家", "https://www.ithome.com/rss/", "消费电子"),
]

PER_FEED = 15        # 每个源最多取多少条
UA = "Mozilla/5.0 (compatible; ai-daily-bot/1.0; +https://ai-daily-v3.vercel.app)"
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(s, limit=240):
    if not s:
        return ""
    s = TAG_RE.sub("", s)
    s = html.unescape(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:limit]


def relative_time(dt):
    if not dt:
        return "刚刚"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "刚刚"
    if mins < 60:
        return f"{mins}分钟前"
    if mins < 1440:
        return f"{mins // 60}小时前"
    return f"{mins // 1440}天前"


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        return parsedate_to_datetime(text)           # RFC822 (RSS pubDate)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))  # ISO (Atom)
    except Exception:
        return None


def strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif')


def find_image(e, *html_texts):
    """从条目里找一张配图:media:content/thumbnail、enclosure(image)、或正文首个 <img>。"""
    for c in e:
        t = strip_ns(c.tag)
        u = c.get('url') or c.get('href') or ''
        typ = (c.get('type') or '') + (c.get('medium') or '')
        if t in ('content', 'thumbnail') and u and ('image' in typ or u.lower().split('?')[0].endswith(IMG_EXT)):
            return u
        if t == 'enclosure' and u and 'image' in (c.get('type') or ''):
            return u
    for h in html_texts:
        if h:
            m = IMG_RE.search(h)
            if m and m.group(1).startswith('http'):
                return m.group(1)
    return ''


def fetch_feed(source, url, default_cat):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, */*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())

    items = []
    # RSS 2.0: channel/item ; Atom: entry
    nodes = root.iter()
    entries = [n for n in root.iter() if strip_ns(n.tag) in ("item", "entry")]
    for e in entries[:PER_FEED]:
        d = {strip_ns(c.tag): c for c in e}
        title = clean_text(d["title"].text if "title" in d else "", 200)
        # 链接:RSS <link>文本;Atom <link href=...>
        link = ""
        if "link" in d:
            link = (d["link"].text or "").strip() or d["link"].get("href", "")
        if not link:
            for c in e:
                if strip_ns(c.tag) == "link" and c.get("href"):
                    link = c.get("href"); break
        summary_node = d.get("description") or d.get("summary") or d.get("content")
        raw_html = (summary_node.text if summary_node is not None else "") or ""
        enc_node = d.get("encoded")  # content:encoded
        raw_html2 = (enc_node.text if enc_node is not None else "") or ""
        summary = clean_text(raw_html)
        image = find_image(e, raw_html, raw_html2)
        date_node = d.get("pubDate") or d.get("updated") or d.get("published")
        dt = parse_date(date_node.text if date_node is not None else None)
        if not title or not link:
            continue
        items.append({
            "title": title,
            "summary": summary,
            "url": link,
            "image": image,
            "source": source,
            "time": relative_time(dt),
            "_ts": dt.isoformat() if dt else "",
            "category": default_cat,
            "tags": [],
        })
    return items


def fetch_all():
    per_feed = []
    for source, url, cat in FEEDS:
        try:
            got = fetch_feed(source, url, cat)
            got.sort(key=lambda x: x.get("_ts", ""), reverse=True)  # 各源内部按新→旧
            print(f"  ✅ {source}: {len(got)} 条")
            per_feed.append(got)
        except Exception as e:
            print(f"  ⚠️ {source} 抓取失败: {e}")
    # 各源轮流取(round-robin),避免高频源刷屏,首页来源更均衡
    all_items = []
    for i in range(max((len(f) for f in per_feed), default=0)):
        for f in per_feed:
            if i < len(f):
                all_items.append(f[i])
    print(f"总计 RSS 抓到 {len(all_items)} 条")
    return all_items


if __name__ == "__main__":
    for n in fetch_all()[:10]:
        print(f"[{n['source']}] {n['title']}  ({n['time']})")
