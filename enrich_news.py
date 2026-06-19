#!/usr/bin/env python3
"""
AI 富化管线:抓取英文新闻 -> 用 Qwen 翻译/改写/分类/关联 -> 写中文 news_data_latest.js
- 模型:qwen3.7-max(阿里云 Anthropic 兼容端点),key 取环境变量 QWEN_KEY
- 仅用标准库,无需 pip 依赖(与 GitHub Action 保持一致)
- 原则:股票只输出 名称+代码+关联理由,绝不编造价格/涨跌
"""

import os
import sys
import json
import time
import urllib.request
from datetime import datetime, timezone

from fetch_rss import fetch_all  # RSS 抓取(免费、无配额,英文国际源)

KEEP = 2000  # 累计上限(到顶才淘汰最旧的,约数月历史;为性能与文件大小设的天花板)
CAP = 20     # 单次最多富化多少条新条目(封顶 Qwen 成本)


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

QWEN_KEY = os.environ.get('QWEN_KEY', '')
QWEN_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic/v1/messages"
QWEN_MODEL = "qwen3.7-max"

CATEGORIES = ['人工智能', '商业航天', '国际局势', '量子科技',
              '具身智能', '生物医药', '未来能源', '消费电子', '低空经济']
CAT_MERGE = {'集成电路': '人工智能'}  # 已废弃分类的归并(芯片并入人工智能)


def call_qwen(prompt, max_tokens=1500, system=None, retries=3):
    """调用 Qwen(Anthropic 协议),返回纯文本。失败抛异常。"""
    if not QWEN_KEY:
        raise RuntimeError('缺少环境变量 QWEN_KEY')
    body = {"model": QWEN_MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    data = json.dumps(body).encode('utf-8')
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(QWEN_URL, data=data, headers={
                "x-api-key": QWEN_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode('utf-8'))
            return ''.join(b.get('text', '') for b in d.get('content', []) if isinstance(b, dict))
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(2 * (i + 1))
    raise last


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
    """单条富化(中英文皆可)。失败则保留原文兜底。"""
    prompt = f"""请把下面这条科技新闻整理成规范中文(若原文是英文则翻译),只输出如下 JSON:
{{
  "title": "中文标题,简洁有力,不超过30字",
  "summary": "中文摘要,1-2句,客观",
  "body": "中文正文,2-3段,基于给定信息客观转述,不编造未提供的细节,可点出意义与影响",
  "category": "从这些里选最贴切的一个:{'、'.join(CATEGORIES)}",
  "tags": ["2-4个中文标签"],
  "stocks": [{{"name":"利好标的中文名","ticker":"准确股票代码","reason":"为何受益,一句话"}}]
}}
关于 stocks(重要):
- 必须给出至少 1 个最可能因这条新闻受益(利好)的上市公司/标的;若关联较弱也要给一个最相关的,并在 reason 里点明关联强弱。
- ticker 用真实准确代码,格式:美股直接用代码(如 NVDA、AAPL);港股用 代码.HK(如 0700.HK);A股用 代码.SH 或 代码.SZ(如 600519.SH、000001.SZ)。该代码会被系统用来查实时行情,务必准确。
- 绝不编造价格、涨跌幅等任何行情数字(行情由系统实时获取)。

标题:{n.get('title','')}
摘要:{n.get('summary','')}
来源:{n.get('source','')}
"""
    try:
        out = extract_json(call_qwen(prompt, max_tokens=1500, system=ENRICH_SYS))
        cat = out.get('category', '').strip()
        cat = CAT_MERGE.get(cat, cat)   # 废弃分类归并(如集成电路→人工智能)
        stocks = []
        for s in (out.get('stocks') or [])[:4]:
            if isinstance(s, dict) and s.get('name'):
                stocks.append({'name': s.get('name', ''), 'ticker': s.get('ticker', ''),
                               'reason': s.get('reason', '')})
        return {
            'id': n.get('id'),
            'title': out.get('title') or n.get('title', ''),
            'summary': out.get('summary') or n.get('summary', ''),
            'body': out.get('body', ''),
            'category': cat if cat in CATEGORIES else n.get('category', '前沿科技'),
            'tags': out.get('tags') or n.get('tags', []),
            'source': n.get('source', ''),
            'time': n.get('time', ''),
            'ts': n.get('_ts') or now_iso(),
            'url': n.get('url', ''),
            'stocks': stocks,
        }
    except Exception as e:
        print(f"  ⚠️ 富化失败,保留英文兜底「{n.get('title','')[:30]}」: {e}")
        n.setdefault('body', '')
        n.setdefault('stocks', [])
        n['ts'] = n.get('_ts') or now_iso()
        return n


def make_digest(items):
    """生成今日综述。失败返回简单兜底。"""
    lines = "\n".join(f"{n['id']}. [{n['category']}] {n['title']}" for n in items[:20])
    prompt = f"""下面是今天的科技前沿要闻清单。请只输出 JSON:
{{
  "text": "120字以内的今日要闻综述,像专业科技日报的开篇导语,概括今天最值得关注的几个方向",
  "highlights": [挑3-5条最重要的 id 数字]
}}
不要编造清单之外的内容。

{lines}
"""
    try:
        out = extract_json(call_qwen(prompt, max_tokens=600, system=ENRICH_SYS))
        hl = [int(x) for x in (out.get('highlights') or []) if str(x).isdigit()][:5]
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
SEEN_MAX = 800   # 持久化记忆最近见过的 URL 上限


def read_seen(existing):
    """已见 URL 清单(持久化)。首次无文件时用现有数据的 URL 播种。"""
    if os.path.exists(SEEN_FILE):
        try:
            return list(json.load(open(SEEN_FILE, encoding='utf-8')))
        except Exception:
            pass
    return [n.get('url') for n in existing if n.get('url')]


def write_seen(seen):
    json.dump(seen[-SEEN_MAX:], open(SEEN_FILE, 'w', encoding='utf-8'), ensure_ascii=False)


def write_data(items, digest):
    with open('news_data_latest.js', 'w', encoding='utf-8') as f:
        f.write('const newsData = ')
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write(';\n')
        f.write('const newsDigest = ')
        json.dump(digest, f, ensure_ascii=False, indent=2)
        f.write(';\n')


def main():
    existing = read_existing()
    seen_list = read_seen(existing)
    seen = set(seen_list)
    print(f"已有 {len(existing)} 条,已见 URL {len(seen)} 个,开始抓取 RSS...")

    raw = fetch_all()
    new = [n for n in raw if n.get('url') and n['url'] not in seen]
    print(f"\n去重后新条目:{len(new)} 条")
    if not new:
        print("无新条目,数据文件保持不变(不会触发提交/部署)")
        return

    new = new[:CAP]
    print(f"开始 Qwen 富化 {len(new)} 条新条目(单次封顶 {CAP})...")
    enriched_new = [enrich_one(n) for n in new]

    # 累计:新条目并入历史,按真实时间倒序(最新在上),到 KEEP 上限才淘汰最旧
    combined = enriched_new + existing
    combined.sort(key=ts_key, reverse=True)
    merged = combined[:KEEP]
    for i, n in enumerate(merged, 1):
        n['id'] = i
        n.pop('_ts', None)

    print("生成今日综述...")
    digest = make_digest(merged)
    write_data(merged, digest)

    # 记录本次处理过的 URL,避免它们滚出窗口后被重复富化
    write_seen(seen_list + [n['url'] for n in new])

    print(f"\n✅ 已写入:新增 {len(enriched_new)} 条,合计 {len(merged)} 条,已见 URL {len(seen_list)+len(new)} 个")


if __name__ == '__main__':
    main()
