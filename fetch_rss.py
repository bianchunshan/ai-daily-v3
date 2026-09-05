#!/usr/bin/env python3
"""
RSS 抓取(免费、无配额、无 key)。解析国际科技媒体 RSS/Atom,返回英文新闻列表。
仅用标准库。供 enrich_news.py 调用(再交给配置的模型翻译富化)。
"""

import re
import html
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# RSS 源(source 名 + 默认分类兜底,真正分类由模型判定)。国际源需翻译,中文源直接用。
FEEDS = [
    # 国际源
    ("TechCrunch", "https://techcrunch.com/feed/", "人工智能"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "消费电子"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "人工智能"),
    ("Wired", "https://www.wired.com/feed/rss", "人工智能"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/", "人工智能"),
    ("Engadget", "https://www.engadget.com/rss.xml", "消费电子"),
    ("Hacker News", "https://hnrss.org/frontpage", "人工智能"),
    ("Tom's Hardware", "https://www.tomshardware.com/feeds/all", "半导体与先进制造"),
    ("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "AI 基础设施"),
    ("SpaceNews", "https://spacenews.com/feed/", "商业航天"),
    # 地缘科技 / 世界新闻(出口管制、国防科技、科技政策、关键资源等由 Qwen 精筛)
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "地缘科技"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "地缘科技"),
    ("BBC中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml", "地缘科技"),
    # 小众板块对口源(补量子/机器人/能源/航天/生物)
    ("Quanta", "https://api.quantamagazine.org/feed/", "量子科技"),
    ("The Robot Report", "https://www.therobotreport.com/feed/", "机器人"),
    ("Electrek", "https://electrek.co/feed/", "未来能源"),
    ("Space.com", "https://www.space.com/feeds/all", "商业航天"),
    ("ScienceDaily", "https://www.sciencedaily.com/rss/top/science.xml", "新材料"),
    ("MedicalXpress", "https://medicalxpress.com/rss-feed/", "生物医药"),
    # 中文源(本身中文,Qwen 跳过翻译只做整理/分类/标的)
    ("36氪", "https://36kr.com/feed", "人工智能"),
    ("量子位", "https://www.qbitai.com/feed", "人工智能"),
    ("IT之家", "https://www.ithome.com/rss/", "消费电子"),
]

PER_FEED = 15        # 每个源最多取多少条
AIHOT_TAKE = 30      # AIHOT 精选条目取数
UA = "Mozilla/5.0 (compatible; ai-daily-bot/1.0; +https://ai-daily-v3.vercel.app)"
TAG_RE = re.compile(r"<[^>]+>")
LAST_SOURCE_STATUS = []


def clean_text(s, limit=240):
    if not s:
        return ""
    s = html.unescape(str(s))
    s = TAG_RE.sub("", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    if s.lower() == "null":
        return ""
    return s[:limit]


def node_text(node):
    """读取 RSS/Atom 节点文本,兼容 CDATA 和 HTML 子节点。"""
    if node is None:
        return ""
    return "".join(node.itertext())


def first_node(d, *names):
    """Element 不能直接用 or 串联,无子节点的 Element 会被判为 False。"""
    for name in names:
        if name in d:
            return d[name]
    return None


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
        xml = r.read().decode('utf-8', 'replace')
        # Some feeds contain bare ampersands or XML 1.0 control characters.
        xml = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml)
        xml = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[\da-fA-F]+;)', '&amp;', xml)
        root = ET.fromstring(xml)

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
        summary_node = first_node(d, "description", "summary", "content")
        raw_html = node_text(summary_node)
        enc_node = first_node(d, "encoded")  # content:encoded
        raw_html2 = node_text(enc_node)
        summary = clean_text(raw_html or raw_html2, 360)
        content = clean_text(raw_html2 or raw_html, 1400)
        image = find_image(e, raw_html, raw_html2)
        date_node = first_node(d, "pubDate", "updated", "published")
        dt = parse_date(node_text(date_node))
        if not title or not link:
            continue
        items.append({
            "title": title,
            "summary": summary,
            "content": content,
            "url": link,
            "image": image,
            "source": source,
            "time": relative_time(dt),
            "_ts": dt.isoformat() if dt else "",
            "category": default_cat,
            "tags": [],
        })
    return items


def fetch_aihot_items(take=AIHOT_TAKE):
    """抓 AIHOT 公开精选 AI/科技条目。来源来自历史 Hermes aihot 日报配置。"""
    url = f"https://aihot.virxact.com/api/public/items?mode=selected&take={take}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, */*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))

    items = []
    for it in (data.get("items") or [])[:take]:
        title = clean_text(it.get("title") or it.get("title_en") or "", 220)
        link = (it.get("url") or it.get("sourceUrl") or it.get("permalink") or "").strip()
        if not title or not link:
            continue
        source_name = clean_text(it.get("source") or it.get("sourceName") or "AIHOT", 120)
        summary = clean_text(it.get("summary") or "", 420)
        content = clean_text(f"来源:{source_name}\n{it.get('summary') or ''}", 1400)
        dt = parse_date(it.get("publishedAt") or it.get("generatedAt") or "")
        items.append({
            "title": title,
            "summary": summary,
            "content": content,
            "url": link,
            "image": "",
            "source": "AIHOT精选",
            "time": relative_time(dt),
            "_ts": dt.isoformat() if dt else "",
            "category": "人工智能",
            "tags": [],
        })
    return items


def fetch_all():
    LAST_SOURCE_STATUS.clear()
    per_feed = []
    try:
        got = fetch_aihot_items()
        got.sort(key=lambda x: x.get("_ts", ""), reverse=True)
        print(f"  ✅ AIHOT精选: {len(got)} 条")
        per_feed.append(got)
        LAST_SOURCE_STATUS.append({'source': 'AIHOT精选', 'ok': True, 'count': len(got)})
    except Exception as e:
        LAST_SOURCE_STATUS.append({'source': 'AIHOT精选', 'ok': False, 'error': type(e).__name__})
        print(f"  ⚠️ AIHOT精选 抓取失败: {e}")

    for source, url, cat in FEEDS:
        try:
            got = fetch_feed(source, url, cat)
            got.sort(key=lambda x: x.get("_ts", ""), reverse=True)  # 各源内部按新→旧
            print(f"  ✅ {source}: {len(got)} 条")
            per_feed.append(got)
            LAST_SOURCE_STATUS.append({'source': source, 'ok': True, 'count': len(got)})
        except Exception as e:
            LAST_SOURCE_STATUS.append({'source': source, 'ok': False, 'error': type(e).__name__})
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
