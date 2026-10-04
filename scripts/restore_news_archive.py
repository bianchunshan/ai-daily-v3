#!/usr/bin/env python3
"""Restore missing enriched articles from a reviewed Git snapshot, without model calls."""

import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import enrich_news as news
from news_export import read_json, write_json


def missing_articles(current, historical):
    ids = {n['id'] for n in current}
    urls = {news.canonical_url(n.get('url')) for n in current}
    result = []
    for item in historical:
        url = news.canonical_url(item.get('url'))
        if not item.get('id') or not url or not item.get('body'):
            continue
        if item['id'] in ids or url in urls:
            continue
        result.append(item)
        ids.add(item['id'])
        urls.add(url)
    return result


def restore_archive(ref, apply=False):
    """Caller must hold the updater lock while writing or publishing."""
    ref = subprocess.check_output(['git', 'rev-parse', '--verify', ref + '^{commit}'], text=True).strip()
    raw = subprocess.check_output(['git', 'show', ref + ':news_data_latest.js'], text=True)
    historical = json.loads(news._extract_array(raw, 'newsData'))
    current = news.read_existing()
    restored = missing_articles(current, historical)
    merged = news.merge_articles(current + restored)
    assert {n['id'] for n in current}.issubset({n['id'] for n in merged})
    report = {'ref': ref, 'before': len(current), 'restored': len(restored), 'after': len(merged),
              'categories': dict(Counter(n.get('category') for n in restored)), 'applied': apply}
    if apply and restored:
        feed = read_json('data/feed.json', None)
        if not isinstance(feed, dict):
            raise SystemExit('Current feed missing; refusing to replace the digest.')
        news.write_data(merged, feed.get('digest', {}))
        status = read_json('data/status.json', {})
        status['total'] = len(merged)
        write_json('data/status.json', status)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True, help='Reviewed historical commit')
    parser.add_argument('--apply', action='store_true', help='Write exports under the updater lock')
    args = parser.parse_args()
    os.chdir(ROOT)
    with open('/tmp/ai-daily-grok-update.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Updater is running; retry when it releases the lock.')
        print(json.dumps(restore_archive(args.ref, args.apply), ensure_ascii=False))


if __name__ == '__main__':
    main()
