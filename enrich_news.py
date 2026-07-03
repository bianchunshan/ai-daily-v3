#!/usr/bin/env python3
"""
AI 富化管线:抓取英文新闻 -> 用 Kimi/Qwen 翻译/改写/分类/关联 -> 写 data/ 下的拆分 JSON
- data/index.json      全量瘦索引(无 body),供首页/搜索/问AI
- data/index-hot.json  最新 HOT 条,首屏先渲染
- data/items/<xx>.json 按 id 前 2 位分片的完整条目(含 body),详情页按需取
- data/tickers.json    当日全部关联标的,行情页直读
- sitemap.xml          详情页 URL 清单
- 默认模型:kimi-for-coding(Kimi Coding Plan Anthropic 兼容端点),key 取环境变量 KIMI_KEY
- 仅用标准库,无需 pip 依赖(与 GitHub Action 保持一致)
- 原则:股票只输出 名称+代码+关联理由,绝不编造价格/涨跌
"""

import os
import sys
import json
import time
import hashlib
import re
import urllib.request
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from fetch_rss import fetch_all  # RSS 抓取(免费、无配额,英文国际源)

KEEP = int(os.environ.get('AID_KEEP', 2000))  # 每个板块的累计上限(到顶才淘汰该板块最旧;可环境变量覆盖)
CAP = int(os.environ.get('AID_CAP', 50))       # 单次最多富化多少条新条目(封顶模型成本;可覆盖)
HOT = int(os.environ.get('AID_HOT', 400))      # 首屏热索引条数(index-hot.json,先渲染再补全量)
SITE_BASE = os.environ.get('AID_SITE_BASE', 'https://ai-daily-v3.vercel.app').rstrip('/')
DATA_DIR = 'data'
ITEMS_DIR = os.path.join(DATA_DIR, 'items')
# 索引里只放列表/搜索需要的字段;body、标的理由等重字段留在按 id 分片的详情文件里
INDEX_FIELDS = ('id', 'title', 'summary', 'category', 'source', 'time', 'ts', 'url', 'image', 'tags')
MIN_SOURCE_CHARS = 80                          # 原始材料太少时先补抓,仍不足则不入库
MIN_SUMMARY_CHARS = 20
MIN_BODY_CHARS = 50
CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ts_key(it):
    """把 ts(带时区的 ISO)转成可比较的时间戳,用于按真实时间排序。"""
    t = it.get('ts', '')
    try:
        d = datetime.fromisoformat(str(t).replace('Z', '+00:00'))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:
        return 0.0

ENRICH_PROVIDER = os.environ.get('ENRICH_PROVIDER', 'kimi').strip().lower()
QWEN_KEY = os.environ.get('QWEN_KEY', '')
QWEN_URL = os.environ.get('QWEN_URL', "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic/v1/messages")
QWEN_MODEL = os.environ.get('QWEN_MODEL', "qwen3.7-max")
KIMI_KEY = os.environ.get('KIMI_KEY') or os.environ.get('MOONSHOT_API_KEY', '')
KIMI_CODING_BASE_URL = os.environ.get('KIMI_CODING_BASE_URL', 'https://api.kimi.com/coding').rstrip('/')
KIMI_URL = os.environ.get('KIMI_URL', f"{KIMI_CODING_BASE_URL}/v1/messages")
KIMI_MODEL = os.environ.get('KIMI_MODEL', 'kimi-for-coding')

CATEGORIES = ['人工智能', 'AI 基础设施', '半导体与先进制造', '机器人', '商业航天',
              '生物医药', '量子科技', '未来能源', '新材料', '脑机接口', '网络安全',
              '消费电子', '地缘科技']
CAT_MERGE = {
    '国际局势': '地缘科技',
    '集成电路': '半导体与先进制造',
    '具身智能': '机器人',
    '低空经济': '机器人',
    '前沿科技': '人工智能',
    'AI基础设施': 'AI 基础设施',
    '半导体': '半导体与先进制造',
    '先进制造': '半导体与先进制造',
    '材料科学': '新材料',
    '脑科学': '脑机接口',
    '网络安全与隐私计算': '网络安全',
}

CATEGORY_GUIDE = (
    "分类口径:"
    "人工智能=模型、Agent、AI应用、算法与产品;"
    "AI 基础设施=算力、数据中心、GPU集群、液冷、电力、光模块、网络、存储、云基础设施;"
    "半导体与先进制造=芯片、制程、EDA、光刻、封装、HBM、晶圆、工业软件与制造装备;"
    "机器人=机器人、具身智能、无人机、自动化、自动驾驶和低空经济;"
    "商业航天=火箭、卫星、深空探测、发射服务和空间基础设施;"
    "生物医药=药物、基因、医疗器械、数字医疗和生命科学;"
    "量子科技=量子计算、量子通信、量子材料和基础量子物理;"
    "未来能源=电池、核聚变、太阳能、储能、氢能、电网和气候能源技术;"
    "新材料=超导、纳米、碳材料、半导体材料、电池材料、生物材料;"
    "脑机接口=脑机接口、神经科技、类脑计算、神经调控和数字疗法;"
    "网络安全=安全漏洞、攻防、隐私计算、身份认证、加密和供应链安全;"
    "消费电子=手机、电脑、可穿戴、XR、智能家居和个人硬件;"
    "地缘科技=出口管制、技术制裁、国防科技、电子战、关键矿产、科技政策和科技相关冲突。"
)


TRACKING_PARAMS = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid', 'mc_cid', 'mc_eid'}


def canonical_url(url):
    """用于去重和稳定 ID 的规范化 URL。"""
    try:
        p = urlsplit(str(url or '').strip())
        if not p.scheme or not p.netloc:
            return str(url or '').strip()
        qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
        path = p.path.rstrip('/') or '/'
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urlencode(qs), ''))
    except Exception:
        return str(url or '').strip()


def stable_id(item):
    key = canonical_url(item.get('url')) or item.get('title') or json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]


def compact_text(text, limit=2800):
    text = re.sub(r'<[^>]+>', ' ', str(text or ''))
    text = re.sub(r'\[[^\]]{0,80}\]\([^)]+\)', ' ', text)
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if text.lower() == 'null':
        return ''
    return text[:limit]


def source_material(n):
    return compact_text("\n".join([
        str(n.get('title', '')),
        str(n.get('summary', '')),
        str(n.get('content', '')),
    ]))


def supporting_material(n):
    return compact_text("\n".join([
        str(n.get('summary', '')),
        str(n.get('content', '')),
    ]))


def fetch_article_text(url):
    """RSS 材料不足时,用 Jina Reader 拉取可读正文。失败返回空。"""
    if not url:
        return ''
    try:
        reader_url = 'https://r.jina.ai/http://' + str(url)
        req = urllib.request.Request(reader_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=18) as r:
            return compact_text(r.read(120000).decode('utf-8', 'replace'), 3200)
    except Exception as e:
        print(f"  ⚠️ 原文补抓失败「{str(url)[:80]}」: {e}")
        return ''


def has_enough_source(n):
    material = supporting_material(n)
    return len(material) >= MIN_SOURCE_CHARS


def is_usable_chinese_item(item):
    title = str(item.get('title', '')).strip()
    summary = str(item.get('summary', '')).strip()
    body = str(item.get('body', '')).strip()
    if not title or not summary or not body:
        return False
    if len(summary) < MIN_SUMMARY_CHARS or len(body) < MIN_BODY_CHARS:
        return False
    if len(CJK_RE.findall(title + summary + body)) < 20:
        return False
    return True


def call_anthropic_compat(url, key, model, auth_mode, prompt, max_tokens=1500, system=None, retries=2):
    """调用 Anthropic 兼容 messages 接口,返回纯文本。失败抛异常。"""
    if not key:
        raise RuntimeError(f'缺少环境变量 {auth_mode["env"]}')
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    data = json.dumps(body).encode('utf-8')
    last = None
    for i in range(retries):
        try:
            headers = {
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            headers[auth_mode["header"]] = f"Bearer {key}" if auth_mode.get("bearer") else key
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.loads(r.read().decode('utf-8'))
            return ''.join(b.get('text', '') for b in d.get('content', []) if isinstance(b, dict))
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(2 * (i + 1))
    raise last


def call_model(prompt, max_tokens=1500, system=None, retries=2):
    """默认 Kimi 富化;设置 ENRICH_PROVIDER=qwen 可退回 Qwen。"""
    if ENRICH_PROVIDER in ('qwen', 'qwen3'):
        return call_anthropic_compat(
            QWEN_URL, QWEN_KEY, QWEN_MODEL,
            {'header': 'x-api-key', 'env': 'QWEN_KEY'},
            prompt, max_tokens=max_tokens, system=system, retries=retries)
    return call_anthropic_compat(
        KIMI_URL, KIMI_KEY, KIMI_MODEL,
        {'header': 'authorization', 'bearer': True, 'env': 'KIMI_KEY'},
        prompt, max_tokens=max_tokens, system=system, retries=retries)


def extract_json(text):
    """从模型输出里抠出第一个 JSON 对象,容忍 ```json 围栏。"""
    t = text.strip()
    if t.startswith('```'):
        t = t.split('```', 2)[1]
        if t.startswith('json'):
            t = t[4:]
    s, e = t.find('{'), t.rfind('}')
    if s >= 0 and e > s:
        return json.loads(t[s:e + 1])
    raise ValueError('未找到 JSON')


ENRICH_SYS = (
    "你是中文科技财经编辑,把科技新闻整理成准确、地道的中文,并判断其利好标的。"
    "严格只输出 JSON,不要任何解释或代码围栏。"
)


def enrich_one(n):
    """单条富化(中英文皆可)。失败或质量不合格则跳过,不写英文/空正文兜底。"""
    n = dict(n)
    if not has_enough_source(n):
        extra = fetch_article_text(n.get('url', ''))
        if extra:
            n['content'] = compact_text("\n".join([str(n.get('content', '')), extra]))
    material = source_material(n)
    if len(material) < MIN_SOURCE_CHARS:
        print(f"  ⚠️ 原始材料不足,跳过「{n.get('title','')[:40]}」")
        return None

    prompt = f"""请把下面这条新闻材料整理成规范中文(若原文是英文则翻译),只输出如下 JSON:
{{
  "skip": false,
  "title": "中文标题,简洁有力,不超过30字",
  "summary": "中文摘要,1-2句,客观,至少20个汉字",
  "body": "中文正文,2-3段,至少50个汉字,基于给定材料客观转述,不编造未提供的细节,可点出意义与影响",
  "category": "从这些里选最贴切的一个:{'、'.join(CATEGORIES)}",
  "tags": ["2-4个中文标签"],
  "stocks": [{{"name":"利好标的中文名","ticker":"准确股票代码","reason":"为何受益,一句话","confidence":"high/medium/low"}}]
}}
如果材料不是科技、科学、前沿产业、产业政策、国防科技、出口管制或关键供应链相关内容(例如普通体育、娱乐、灾害、社会新闻),请只输出:
{{"skip": true, "reason": "简短说明"}}

关于 stocks(重要):
- 只有新闻和上市公司/标的存在明确业务关联时才填写;关联弱或只是泛泛行业影响时返回空数组 []。
- confidence 表示关联置信度;low 只用于详情页参考,不要硬凑利好。
- ticker 用真实准确代码,格式:美股直接用代码(如 NVDA、AAPL);港股用 代码.HK(如 0700.HK);A股用 代码.SH 或 代码.SZ(如 600519.SH、000001.SZ)。该代码会被系统用来查实时行情,务必准确。
- 绝不编造价格、涨跌幅等任何行情数字(行情由系统实时获取)。

标题:{n.get('title','')}
来源:{n.get('source','')}
{CATEGORY_GUIDE}
原文材料:{material}
"""
    try:
        out = extract_json(call_model(prompt, max_tokens=1500, system=ENRICH_SYS))
        if out.get('skip') is True:
            print(f"  ⚠️ 非前沿科技相关,跳过「{n.get('title','')[:40]}」")
            return None
        cat = out.get('category', '').strip()
        cat = CAT_MERGE.get(cat, cat)   # 废弃/旧分类归并
        stocks = []
        for s in (out.get('stocks') or [])[:4]:
            if isinstance(s, dict) and s.get('name'):
                stocks.append({'name': s.get('name', ''), 'ticker': s.get('ticker', ''),
                               'reason': s.get('reason', ''), 'confidence': s.get('confidence', '')})
        item = {
            'id': n.get('id'),
            'title': out.get('title') or n.get('title', ''),
            'summary': out.get('summary') or n.get('summary', ''),
            'body': out.get('body', ''),
            'category': cat if cat in CATEGORIES else CAT_MERGE.get(n.get('category', ''), '人工智能'),
            'tags': out.get('tags') or n.get('tags', []),
            'source': n.get('source', ''),
            'time': n.get('time', ''),
            'ts': n.get('_ts') or now_iso(),
            'url': n.get('url', ''),
            'image': n.get('image', ''),
            'stocks': stocks,
        }
        if not is_usable_chinese_item(item):
            print(f"  ⚠️ 富化结果不合格,跳过「{n.get('title','')[:40]}」")
            return None
        return item
    except Exception as e:
        print(f"  ⚠️ 富化失败,跳过「{n.get('title','')[:30]}」: {e}")
        return None


def make_digest(items):
    """生成今日综述。失败返回简单兜底。"""
    lines = "\n".join(f"{n['id']}. [{n['category']}] {n['title']}" for n in items[:20])
    prompt = f"""下面是今天的科技前沿要闻清单。请只输出 JSON:
{{
  "text": "120字以内的今日要闻综述,像专业科技日报的开篇导语,概括今天最值得关注的几个方向",
  "highlights": ["挑3-5条最重要的 id,必须原样使用清单里的字符串 id"]
}}
不要编造清单之外的内容。

{lines}
"""
    try:
        out = extract_json(call_model(prompt, max_tokens=600, system=ENRICH_SYS))
        valid_ids = {str(n.get('id', '')) for n in items[:20]}
        hl = [str(x) for x in (out.get('highlights') or []) if str(x) in valid_ids][:5]
        return {'text': out.get('text', ''), 'highlights': hl}
    except Exception as e:
        print(f"⚠️ 综述生成失败: {e}")
        return {'text': '', 'highlights': []}


def _extract_array(txt, varname):
    """从 const <varname> = [...] 里提取数组文本(括号配对,容忍字符串内的括号)。"""
    start = txt.find('const ' + varname)
    if start < 0:
        return None
    i = txt.find('[', start)
    if i < 0:
        return None
    depth, in_str, esc, q = 0, False, False, ''
    for j in range(i, len(txt)):
        c = txt[j]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == q:
                in_str = False
        elif c in '"\'':
            in_str, q = True, c
        elif c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                return txt[i:j + 1]
    return None


def read_existing():
    """读取已有数据(data/items/ 分片),用于去重与保留最近条目。兼容旧版 news_data_latest.js。"""
    if os.path.isdir(ITEMS_DIR):
        items = []
        try:
            for fn in sorted(os.listdir(ITEMS_DIR)):
                if fn.endswith('.json'):
                    shard = json.load(open(os.path.join(ITEMS_DIR, fn), encoding='utf-8'))
                    items.extend(shard.values())
            items.sort(key=ts_key, reverse=True)
            return items
        except Exception as e:
            print('读取分片数据失败,当作空:', e)
            return []
    if not os.path.exists('news_data_latest.js'):
        return []
    try:
        arr = _extract_array(open('news_data_latest.js', encoding='utf-8').read(), 'newsData')
        return json.loads(arr) if arr else []
    except Exception as e:
        print('读取旧数据失败,当作空:', e)
        return []


SEEN_FILE = 'seen_urls.json'
SEEN_MAX = 5000  # 持久化记忆最近见过的 URL 上限


def read_seen(existing):
    """已见 URL 清单(持久化)。首次无文件时用现有数据的 URL 播种。"""
    if os.path.exists(SEEN_FILE):
        try:
            return list(json.load(open(SEEN_FILE, encoding='utf-8')))
        except Exception:
            pass
    return [canonical_url(n.get('url')) for n in existing if n.get('url')]


def write_seen(seen):
    json.dump(seen[-SEEN_MAX:], open(SEEN_FILE, 'w', encoding='utf-8'), ensure_ascii=False)


def _dump_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'), sort_keys=False)
        f.write('\n')


def _index_entry(n):
    """列表/搜索用的瘦身条目:去掉 body,标的只留 名称/代码/置信度。"""
    e = {k: n.get(k, '') for k in INDEX_FIELDS}
    e['stocks'] = [{'name': s.get('name', ''), 'ticker': s.get('ticker', ''),
                    'confidence': s.get('confidence', '')}
                   for s in (n.get('stocks') or []) if s.get('name')]
    return e


def shard_of(item_id):
    return str(item_id)[:2]


def write_sitemap(items):
    urls = [f'{SITE_BASE}/', f'{SITE_BASE}/stock.html']
    urls += [f'{SITE_BASE}/detail.html?id={n["id"]}' for n in items]
    with open('sitemap.xml', 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in urls:
            f.write(f'  <url><loc>{u.replace("&", "&amp;")}</loc></url>\n')
        f.write('</urlset>\n')


def write_data(items, digest):
    """写拆分后的数据:瘦索引(全量+热门) + 按 id 前缀分片的详情 + 当日标的 + sitemap。"""
    os.makedirs(ITEMS_DIR, exist_ok=True)
    meta = {'generatedAt': now_iso(), 'total': len(items), 'digest': digest}

    index_items = [_index_entry(n) for n in items]
    _dump_json(os.path.join(DATA_DIR, 'index.json'), dict(meta, items=index_items))
    _dump_json(os.path.join(DATA_DIR, 'index-hot.json'), dict(meta, items=index_items[:HOT]))

    shards = {}
    for n in items:
        shards.setdefault(shard_of(n['id']), {})[n['id']] = n
    for key, shard in shards.items():
        _dump_json(os.path.join(ITEMS_DIR, f'{key}.json'), dict(sorted(shard.items())))
    for fn in os.listdir(ITEMS_DIR):   # 清掉已无条目的旧分片
        if fn.endswith('.json') and fn[:-5] not in shards:
            os.remove(os.path.join(ITEMS_DIR, fn))

    tickers, seen_tk = [], set()
    for n in items:
        for s in (n.get('stocks') or []):
            tk = (s.get('ticker') or '').strip()
            if tk and tk not in seen_tk:
                seen_tk.add(tk)
                tickers.append({'ticker': tk, 'name': s.get('name', '')})
    _dump_json(os.path.join(DATA_DIR, 'tickers.json'), tickers)

    write_sitemap(items)


def main():
    loaded_existing = read_existing()
    existing = [n for n in loaded_existing if is_usable_chinese_item(n)]
    if len(existing) != len(loaded_existing):
        print(f"清理历史低质量条目:{len(loaded_existing) - len(existing)} 条")
    seen_list = read_seen(existing)
    seen = set(seen_list)
    seen.update(canonical_url(n.get('url')) for n in existing if n.get('url'))
    print(f"已有 {len(existing)} 条,已见 URL {len(seen)} 个,开始抓取 RSS...")

    raw = fetch_all()
    new = [n for n in raw if n.get('url') and canonical_url(n['url']) not in seen]
    print(f"\n去重后新条目:{len(new)} 条")
    if not new:
        print("无新条目,数据文件保持不变(不会触发提交/部署)")
        return

    new = new[:CAP]
    print(f"开始 {ENRICH_PROVIDER} 富化 {len(new)} 条新条目(并发,单次封顶 {CAP})...")
    with ThreadPoolExecutor(max_workers=6) as ex:   # 并发调用,避免顺序累加拖很久
        enriched_new = [n for n in ex.map(enrich_one, new) if n]
    if not enriched_new:
        print("本次没有通过富化质量门禁的新条目,数据文件保持不变")
        return

    # 累计:新条目并入历史,按真实时间倒序(最新在上)
    combined = enriched_new + existing
    combined.sort(key=ts_key, reverse=True)
    # 每个板块各留最新 KEEP 条(到顶才淘汰该板块最旧的),其余板块互不影响;同时按规范 URL 去重。
    per_cat = {}
    seen_merged = set()
    merged = []
    for n in combined:
        key = canonical_url(n.get('url')) or n.get('title', '')
        if key in seen_merged:
            continue
        seen_merged.add(key)
        c = n.get('category', '其他')
        per_cat[c] = per_cat.get(c, 0) + 1
        if per_cat[c] <= KEEP:
            merged.append(n)
    for n in merged:   # merged 仍是全局时间倒序;id 必须稳定,不能随排序漂移
        n['id'] = stable_id(n)
        n.pop('_ts', None)

    print("生成今日综述...")
    digest = make_digest(merged)
    write_data(merged, digest)

    # 记录本次处理过的 URL,避免它们滚出窗口后被重复富化
    write_seen(seen_list + [canonical_url(n['url']) for n in new])

    print(f"\n✅ 已写入:新增 {len(enriched_new)} 条,合计 {len(merged)} 条,已见 URL {len(seen_list)+len(new)} 个")


if __name__ == '__main__':
    main()
