#!/usr/bin/env python3
"""
AI 富化管线:抓取英文新闻 -> 用 Grok/Kimi/Qwen 翻译/改写/分类/关联 -> 写中文 news_data_latest.js
- 支持本机 Hermes xAI OAuth 代理的 OpenAI 兼容端点
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

from fetch_rss import fetch_all, LAST_SOURCE_STATUS
from news_export import export_news, write_json, read_json, write_status

KEEP = int(os.environ.get('AID_KEEP', 2000))  # 每个板块的累计上限(到顶才淘汰该板块最旧;可环境变量覆盖)
CAP = int(os.environ.get('AID_CAP', 50))       # 单次最多富化多少条新条目(封顶模型成本;可覆盖)
FRONTEND_DAYS = int(os.environ.get('AID_FRONTEND_DAYS', 14))  # 前端列表保留最近 N 天
FRONTEND_MAX = int(os.environ.get('AID_FRONTEND_MAX', 800))   # 前端列表条数上限
CHAT_INDEX_MAX = int(os.environ.get('AID_CHAT_INDEX_MAX', 1500))  # 问AI 召回索引条数
MIN_SOURCE_CHARS = 80                          # 原始材料太少时先补抓,仍不足则不入库
MIN_SUMMARY_CHARS = 20
MIN_BODY_CHARS = 50
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
RETRY_FILE = 'retry_queue.json'
MAX_ATTEMPTS = 5
LIST_KEYS = ('id', 'title', 'summary', 'category', 'tags', 'source', 'time', 'ts', 'url', 'image', 'stocks')


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
GROK_URL = os.environ.get('GROK_URL', 'http://127.0.0.1:18645/v1/chat/completions')
GROK_KEY = os.environ.get('GROK_KEY', 'local-hermes-proxy')
GROK_MODEL = os.environ.get('GROK_MODEL', 'grok-4.5')
# 本机 Qwen3.6-35B-A3B(LaunchAgent 链路:ai.mlx.auth-proxy -> qwen36.proxy -> ai.mlx.server)。
# 它是 thinking 模型:思考过程同样计入 max_tokens,单条实测要 2600+ token;
# 6 路并发时单条墙钟 150-210 秒(要排 mlx_lm.server 的解码队列),所以预算比云端大得多。
LOCAL_URL = os.environ.get('LOCAL_URL', 'http://127.0.0.1:8801/v1/chat/completions')
LOCAL_KEY = os.environ.get('LOCAL_KEY', '')
LOCAL_MODEL = os.environ.get('LOCAL_MODEL', 'qwen')
LOCAL_MAX_TOKENS = int(os.environ.get('LOCAL_MAX_TOKENS', '5000'))
LOCAL_TIMEOUT = int(os.environ.get('LOCAL_TIMEOUT', '420'))
# 关掉 thinking。开着时它先思考五千多字才出正文,单条 36 秒;关掉后 5 秒左右,
# 3 条对照实测 110.6s -> 13.8s,而分类/标签/标的完全一致、正文反而更完整。
# 富化是结构化改写任务,骨架由 prompt 的 JSON schema 定死,不吃模型自己的思考链。
LOCAL_EXTRA_BODY = json.loads(
    os.environ.get('LOCAL_EXTRA_BODY', '{"chat_template_kwargs":{"enable_thinking":false}}')
)

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
        reader_url = 'https://r.jina.ai/' + str(url)
        req = urllib.request.Request(reader_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=18) as r:
            return compact_text(r.read(120000).decode('utf-8', 'replace'), 3200)
    except Exception as e:
        print(f"  ⚠️ 原文补抓失败「{str(url)[:80]}」: {e}")
        return ''


def has_enough_source(n):
    material = supporting_material(n)
    return len(material) >= MIN_SOURCE_CHARS


# 与 api/quote.js 的 toSina() 支持范围保持一致:港股 .HK、A股 .SH/.SS/.SZ 或裸 6 位、美股纯字母。
# 模型常吐出真实但行情源不支持的代码(台股 .TW、韩股 .KS、日股 .T、北交所 .BJ),写进去前端查不到
# 只会静默失败;.DE/.PA/.SW 等欧股还会被 quote.js 的宽松正则误判成美股,转成 gb_xxx 去查同样查不到。
TICKER_PATTERNS = (
    re.compile(r'^\d{1,5}\.HK$'),            # 港股 0700.HK
    re.compile(r'^\d{6}\.(SH|SS|SZ)$'),      # A股 600519.SH / 000001.SZ
    re.compile(r'^\d{6}$'),                  # A股裸代码 600519
    re.compile(r'^[A-Z]{1,5}(\.[A-Z])?$'),   # 美股 NVDA / BRK.B
)


def normalize_ticker(raw):
    """规范化并校验股票代码。行情源查不到的一律返回 '',调用方保留公司名即可。"""
    tk = str(raw or '').strip().upper()
    if not tk:
        return ''
    return tk if any(p.match(tk) for p in TICKER_PATTERNS) else ''


def is_usable_chinese_item(item):
    title = str(item.get('title', '')).strip()
    summary = str(item.get('summary', '')).strip()
    body = str(item.get('body', '')).strip()
    if not title or not summary or not body:
        return False
    if len(CJK_RE.findall(title)) < 2:
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


def call_openai_compat(url, key, model, prompt, max_tokens=1500, system=None, retries=2,
                       timeout=90, extra_body=None):
    """调用 OpenAI 兼容 chat/completions 接口,返回纯文本。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    body.update(extra_body or {})
    data = json.dumps(body).encode('utf-8')
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "authorization": f"Bearer {key}",
                    "content-type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode('utf-8'))
            msg = d['choices'][0]['message']
            text = msg.get('content')
            if not text:
                # 思考型模型(本机 Qwen3.6 等)如果思考没收敛就撞上 max_tokens,
                # 返回的 message 里连 content 键都没有。这里显式失败以触发重试,
                # 不能当成空串返回,否则会静默产出不合格条目。
                raise RuntimeError(
                    f"模型未返回 content(finish_reason={d['choices'][0].get('finish_reason')})")
            return text
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(2 * (i + 1))
    raise last


def call_model(prompt, max_tokens=1500, system=None, retries=2):
    """按 ENRICH_PROVIDER 选择本机 Qwen、Grok、Qwen 云端或 Kimi。"""
    if ENRICH_PROVIDER in ('local', 'mlx'):
        return call_openai_compat(
            LOCAL_URL, LOCAL_KEY, LOCAL_MODEL,
            prompt, max_tokens=max(max_tokens, LOCAL_MAX_TOKENS), system=system,
            retries=retries, timeout=LOCAL_TIMEOUT, extra_body=LOCAL_EXTRA_BODY)
    if ENRICH_PROVIDER in ('grok', 'xai'):
        return call_openai_compat(
            GROK_URL, GROK_KEY, GROK_MODEL,
            prompt, max_tokens=max_tokens, system=system, retries=retries)
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
        raise ValueError('insufficient source material')

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
- ticker 只支持三个市场,格式:美股直接用代码(如 NVDA、AAPL);港股用 代码.HK(如 0700.HK);A股用 代码.SH 或 代码.SZ(如 600519.SH、000001.SZ)。该代码会被系统用来查实时行情,务必准确。
- 台股、韩股、日股、欧股、北交所等其他市场的代码(如 2330.TW、005930.KS、9984.T、SIE.DE、872190.BJ)一律不支持,系统查不到行情。这类公司若有美股 ADR 就填 ADR 代码(例如台积电填 TSM、阿斯麦填 ASML、索尼填 SONY);没有 ADR 就把 ticker 留空字符串,只保留公司名。
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
                tk = normalize_ticker(s.get('ticker'))
                if s.get('ticker') and not tk:
                    print(f"  ⚠️ 行情源不支持的代码,已剔除:{s.get('ticker')}（{s.get('name')}）")
                stocks.append({'name': s.get('name', ''), 'ticker': tk,
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
            raise ValueError('Chinese content quality check failed')
        return item
    except Exception as e:
        print(f"  ⚠️ 富化失败,跳过「{n.get('title','')[:30]}」: {e}")
        raise


def process_one(n):
    try:
        item = enrich_one(n)
        return {'status': 'success' if item else 'excluded', 'item': item}
    except Exception as exc:
        return {'status': 'retry', 'error': type(exc).__name__}


def update_retry(queue, raw, outcome):
    url = canonical_url(raw['url'])
    if outcome['status'] != 'retry':
        queue.pop(url, None)
        return
    attempts = queue.get(url, {}).get('attempts', 0) + 1
    queue[url] = {
        'item': {k: raw.get(k, '') for k in ('title', 'summary', 'content', 'url', 'source', 'image', '_ts', 'category', 'time')},
        'attempts': attempts, 'error': outcome['error'],
        'nextAttemptAt': time.time() + min(21600, 600 * 2 ** (attempts - 1)),
        'exhausted': attempts >= MAX_ATTEMPTS,
    }


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
    """从 var/const/let <varname> = [...] 里提取数组文本(括号配对,容忍字符串内的括号)。"""
    m = re.search(r'(?:var|const|let)\s+' + re.escape(varname) + r'\s*=\s*\[', txt)
    if not m:
        return None
    i = m.end() - 1  # 指向 '['
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
    """读取已有 news_data_latest.js 的 newsData,用于去重与保留最近条目。"""
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
    write_json(SEEN_FILE, list(dict.fromkeys(seen))[-SEEN_MAX:])


def _parse_ts(t):
    try:
        d = datetime.fromisoformat(str(t).replace('Z', '+00:00'))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def _frontend_slice(items):
    """前端只拿最近 N 天 / 最多 M 条的轻量列表,正文另存。"""
    cut = datetime.now(timezone.utc).timestamp() - FRONTEND_DAYS * 86400
    front = []
    for n in items:
        d = _parse_ts(n.get('ts'))
        if d and d.timestamp() < cut:
            continue
        front.append(n)
        if len(front) >= FRONTEND_MAX:
            break
    if len(front) < 50:
        front = items[:FRONTEND_MAX]
    return front


def write_data(items, digest):
    # 历史条目不经过 enrich_one,这里统一再洗一次代码,保证落盘数据全部能查到行情
    for n in items:
        for s in (n.get('stocks') or []):
            s['ticker'] = normalize_ticker(s.get('ticker'))

    # 全量归档(管线/chat 兜底用),紧凑写入;用 var 便于前端回退二次加载
    with open('news_data_latest.js', 'w', encoding='utf-8') as f:
        f.write('var newsData = ')
        json.dump(items, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\nvar newsDigest = ')
        json.dump(digest, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')

    front = _frontend_slice(items)
    lite = []
    bodies = {}
    for n in front:
        item = {k: n[k] for k in LIST_KEYS if k in n and n.get(k) is not None}
        lite.append(item)
        if n.get('body'):
            bodies[str(n['id'])] = n['body']

    with open('news_data_list.js', 'w', encoding='utf-8') as f:
        f.write('var newsData = ')
        json.dump(lite, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\nvar newsDigest = ')
        json.dump(digest, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')

    with open('news_bodies.json', 'w', encoding='utf-8') as f:
        json.dump(bodies, f, ensure_ascii=False, separators=(',', ':'))

    chat_idx = []
    for n in items[:CHAT_INDEX_MAX]:
        chat_idx.append({
            'id': n.get('id'),
            'title': str(n.get('title') or '')[:80],
            'summary': str(n.get('summary') or '')[:180],
            'category': n.get('category') or '',
            'source': str(n.get('source') or '')[:60],
            'url': str(n.get('url') or '')[:240],
            'tags': (n.get('tags') or [])[:6],
            'stocks': [
                {'name': s.get('name'), 'ticker': s.get('ticker')}
                for s in (n.get('stocks') or [])[:3]
            ],
            'ts': n.get('ts') or '',
        })
    with open('news_chat_index.json', 'w', encoding='utf-8') as f:
        json.dump(chat_idx, f, ensure_ascii=False, separators=(',', ':'))
    export_news(items, lite, digest)


def main():
    loaded_existing = read_existing()
    # Keep existing articles available while their translations are repaired.
    existing = loaded_existing
    queue = read_json(RETRY_FILE, {})
    for n in existing:
        if not is_usable_chinese_item(n) and canonical_url(n.get('url')) not in queue:
            queue[canonical_url(n['url'])] = {
                'item': {**n, 'content': n.get('body', ''), '_ts': n.get('ts', '')},
                'attempts': 0, 'nextAttemptAt': 0, 'exhausted': False,
            }
    seen_list = read_seen(existing)
    seen = set(seen_list)
    seen.update(canonical_url(n.get('url')) for n in existing if n.get('url'))
    print(f"已有 {len(existing)} 条,已见 URL {len(seen)} 个,开始抓取 RSS...")

    raw = fetch_all()
    due = [entry['item'] for entry in queue.values()
           if not entry.get('exhausted') and entry.get('nextAttemptAt', 0) <= time.time()]
    new = due + [n for n in raw if n.get('url') and canonical_url(n['url']) not in seen
                 and canonical_url(n['url']) not in queue]
    new = list({canonical_url(n['url']): n for n in new}.values())
    print(f"\n去重后新条目:{len(new)} 条")
    if not new:
        write_json(RETRY_FILE, queue)
        write_status(total=len(existing), latest=existing[0].get('ts') if existing else None,
                     pending=sum(not e.get('exhausted') for e in queue.values()),
                     exhausted=sum(bool(e.get('exhausted')) for e in queue.values()), sources=LAST_SOURCE_STATUS)
        print("无新条目,数据文件保持不变(不会触发提交/部署)")
        return

    new = new[:CAP]
    print(f"开始 {ENRICH_PROVIDER} 富化 {len(new)} 条新条目(并发,单次封顶 {CAP})...")
    with ThreadPoolExecutor(max_workers=6) as ex:   # 并发调用,避免顺序累加拖很久
        outcomes = list(ex.map(process_one, new))
    enriched_new = [out['item'] for out in outcomes if out['status'] == 'success']
    processed = []
    for raw_item, outcome in zip(new, outcomes):
        update_retry(queue, raw_item, outcome)
        if outcome['status'] != 'retry':
            processed.append(canonical_url(raw_item['url']))
    write_json(RETRY_FILE, queue)
    repaired = {canonical_url(n['url']) for n in enriched_new}
    added = sum(canonical_url(n['url']) not in seen for n in enriched_new)
    if repaired:
        existing = [n for n in existing if canonical_url(n.get('url')) not in repaired]
    if not enriched_new:
        # 避免无关或不合格条目在每次轮询中反复消耗模型。
        write_seen(seen_list + processed)
        write_status(total=len(existing), latest=existing[0].get('ts') if existing else None,
                     pending=sum(not e.get('exhausted') for e in queue.values()),
                     exhausted=sum(bool(e.get('exhausted')) for e in queue.values()), sources=LAST_SOURCE_STATUS)
        print("本次无新增;暂时失败的条目保留在重试队列")
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
    write_seen(seen_list + processed)
    write_status(added=added, total=len(merged), latest=merged[0].get('ts') if merged else None,
                 pending=sum(not e.get('exhausted') for e in queue.values()),
                 exhausted=sum(bool(e.get('exhausted')) for e in queue.values()), sources=LAST_SOURCE_STATUS)

    print(f"\n✅ 已写入:新增 {len(enriched_new)} 条,全量 {len(merged)} 条,前端列表已拆分,已见 URL {len(seen_list)+len(new)} 个")


if __name__ == '__main__':
    main()
