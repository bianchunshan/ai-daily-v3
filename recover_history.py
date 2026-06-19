#!/usr/bin/env python3
"""一次性:从 git 历史恢复所有已中文富化的新闻,去重、按时间倒序,作为累计档基底。
保留当前 newsDigest。同时把所有见过的 URL 写进 seen_urls.json。"""
import subprocess, json
import enrich_news as E

lines = subprocess.check_output(
    ['git', 'log', '--reverse', '--format=%H %aI', '--', 'news_data_latest.js']
).decode().split('\n')

items_by_url = {}     # url -> item(含 ts=首次出现的提交时间)
all_urls = []         # 所有见过的 url(含未富化的,用于去重防重抓)

for line in lines:
    line = line.strip()
    if not line:
        continue
    h, date = line.split(' ', 1)
    try:
        c = subprocess.check_output(['git', 'show', f'{h}:news_data_latest.js']).decode()
    except Exception:
        continue
    arr = E._extract_array(c, 'newsData')
    if not arr:
        continue
    try:
        items = json.loads(arr)
    except Exception:
        continue
    for it in items:
        u = it.get('url')
        if not u:
            continue
        if u not in all_urls:
            all_urls.append(u)
        if u not in items_by_url and it.get('body'):   # 只收已中文富化的
            it = dict(it)
            it['ts'] = it.get('ts') or date            # 首次出现时间作为时间戳
            items_by_url[u] = it

# 最新在上(按真实时间,处理时区)
allitems = sorted(items_by_url.values(), key=E.ts_key, reverse=True)
for i, it in enumerate(allitems, 1):
    it['id'] = i
    it.pop('_ts', None)

# 保留当前 newsDigest 原样
cur = open('news_data_latest.js', encoding='utf-8').read()
idx = cur.find('const newsDigest')
digest_tail = cur[idx:] if idx >= 0 else 'const newsDigest = {"text":"","highlights":[]};\n'

with open('news_data_latest.js', 'w', encoding='utf-8') as f:
    f.write('const newsData = ')
    json.dump(allitems, f, ensure_ascii=False, indent=2)
    f.write(';\n')
    f.write(digest_tail if digest_tail.endswith('\n') else digest_tail + '\n')

json.dump(all_urls[-E.SEEN_MAX:], open('seen_urls.json', 'w', encoding='utf-8'), ensure_ascii=False)

print(f"✅ 恢复累计档:{len(allitems)} 条中文新闻;已见 URL {len(all_urls)} 个")
print("日期分布:", end=' ')
from collections import Counter
print(dict(Counter(it['ts'][:10] for it in allitems)))
