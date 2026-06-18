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

from fetch_currents_news import generate_all_news  # 复用现有抓取逻辑(英文源)

QWEN_KEY = os.environ.get('QWEN_KEY', '')
QWEN_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic/v1/messages"
QWEN_MODEL = "qwen3.7-max"

CATEGORIES = ['人工智能', '集成电路', '商业航天', '国际局势', '量子科技',
              '具身智能', '生物医药', '未来能源', '消费电子', '低空经济']


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
    "你是中文科技财经编辑。把英文科技新闻改写成准确、地道的中文。"
    "严格只输出 JSON,不要任何解释或代码围栏。"
)


def enrich_one(n):
    """单条富化。失败则保留英文原文兜底。"""
    prompt = f"""请把下面这条英文科技新闻处理成中文,只输出如下 JSON:
{{
  "title": "中文标题,简洁有力,不超过30字",
  "summary": "中文摘要,1-2句,客观",
  "body": "中文正文,2-3段,基于给定信息客观转述,不要编造未提供的细节,可点出其意义",
  "category": "从这些里选最贴切的一个:{'、'.join(CATEGORIES)}",
  "tags": ["2-4个中文标签"],
  "stocks": [{{"name":"公司/标的中文名","ticker":"股票代码如NVDA/0700.HK,不确定就留空字符串","reason":"为何与这条新闻相关,一句话"}}]
}}
要求:stocks 只放确实强相关的上市标的,没有就给空数组 [];绝对不要编造价格、涨跌幅或任何行情数字。

英文标题:{n.get('title','')}
英文摘要:{n.get('summary','')}
来源:{n.get('source','')}
"""
    try:
        out = extract_json(call_qwen(prompt, max_tokens=1500, system=ENRICH_SYS))
        cat = out.get('category', '').strip()
        stocks = []
        for s in (out.get('stocks') or [])[:4]:
            if isinstance(s, dict) and s.get('name'):
                stocks.append({'name': s.get('name', ''), 'ticker': s.get('ticker', ''),
                               'reason': s.get('reason', '')})
        return {
            'id': n['id'],
            'title': out.get('title') or n.get('title', ''),
            'summary': out.get('summary') or n.get('summary', ''),
            'body': out.get('body', ''),
            'category': cat if cat in CATEGORIES else n.get('category', '前沿科技'),
            'tags': out.get('tags') or n.get('tags', []),
            'source': n.get('source', ''),
            'time': n.get('time', ''),
            'url': n.get('url', ''),
            'stocks': stocks,
        }
    except Exception as e:
        print(f"  ⚠️ 第{n['id']}条富化失败,保留英文兜底: {e}")
        n.setdefault('body', '')
        n.setdefault('stocks', [])
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


def main():
    raw = generate_all_news()
    for i, n in enumerate(raw, 1):
        n['id'] = i
    print(f"\n抓到 {len(raw)} 条英文新闻,开始 Qwen 富化...")

    enriched = []
    for n in raw:
        print(f"  [{n['id']}/{len(raw)}] {n.get('title','')[:40]}")
        enriched.append(enrich_one(n))

    print("\n生成今日综述...")
    digest = make_digest(enriched)

    with open('news_data_latest.js', 'w', encoding='utf-8') as f:
        f.write('const newsData = ')
        json.dump(enriched, f, ensure_ascii=False, indent=2)
        f.write(';\n')
        f.write('const newsDigest = ')
        json.dump(digest, f, ensure_ascii=False, indent=2)
        f.write(';\n')

    zh = sum(1 for n in enriched if n.get('body'))
    print(f"\n✅ 已写入 news_data_latest.js:共 {len(enriched)} 条,其中 {zh} 条成功中文富化")


if __name__ == '__main__':
    main()
