#!/usr/bin/env python3
"""Collect dated public news into a reviewable, resumable backfill manifest."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch_rss import FEEDS, UA, clean_text, fetch_feed, parse_date, relative_time
from enrich_news import canonical_url
from news_export import write_json

WORDPRESS = {
    'TechCrunch': 'https://techcrunch.com/wp-json/wp/v2/posts',
    'Ars Technica': 'https://arstechnica.com/wp-json/wp/v2/posts',
    'MIT Tech Review': 'https://www.technologyreview.com/wp-json/wp/v2/posts',
    'SpaceNews': 'https://spacenews.com/wp-json/wp/v2/posts',
    'Quanta': 'https://api.quantamagazine.org/wp-json/wp/v2/posts',
    'The Robot Report': 'https://www.therobotreport.com/wp-json/wp/v2/posts',
    'Electrek': 'https://electrek.co/wp-json/wp/v2/posts',
    '量子位': 'https://www.qbitai.com/wp-json/wp/v2/posts',
}


def aware(value):
    dt = parse_date(value)
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def within(item, start, end):
    dt = aware(item.get('_ts', ''))
    return bool(dt and start <= dt < end)


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response), response.headers


def candidate(title, url, date, source, category, summary='', content='', image=''):
    dt = aware(date)
    return {'title': clean_text(title, 220), 'url': url, '_ts': dt.isoformat() if dt else '',
            'source': source, 'category': category, 'summary': clean_text(summary, 420),
            'content': clean_text(content or summary, 2800), 'image': image,
            'tags': [], 'time': relative_time(dt)}


def collect_wordpress(source, category, start, end):
    items = []
    for page in range(1, 101):
        params = {'after': start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
                  'before': end.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
                  'per_page': 100, 'page': page, 'orderby': 'date', 'order': 'desc',
                  '_fields': 'link,date_gmt,title,excerpt,content,jetpack_featured_media_url'}
        rows, headers = get_json(WORDPRESS[source] + '?' + urlencode(params))
        if not isinstance(rows, list):
            raise ValueError('WordPress API did not return posts')
        for row in rows:
            items.append(candidate(row['title']['rendered'], row['link'], row['date_gmt'],
                                   source, category, row.get('excerpt', {}).get('rendered', ''),
                                   row.get('content', {}).get('rendered', ''),
                                   row.get('jetpack_featured_media_url', '')))
        if len(rows) < 100 or page >= int(headers.get('X-WP-TotalPages', 101)):
            return items, True
        time.sleep(0.25)
    return items, False


def collect_aihot(start, end):
    items, cursors, cursor = [], set(), None
    for page in range(100):
        params = {'mode': 'selected', 'take': 100}
        if cursor:
            params['cursor'] = cursor
        data, _ = get_json('https://aihot.virxact.com/api/public/items?' + urlencode(params))
        rows = data.get('items') or []
        dates = []
        for row in rows:
            date = row.get('publishedAt') or row.get('generatedAt') or ''
            item = candidate(row.get('title') or row.get('title_en', ''),
                             row.get('url') or row.get('sourceUrl') or '', date,
                             'AIHOT精选', '人工智能', row.get('summary', ''))
            if item['url'] and within(item, start, end):
                items.append(item)
            dt = aware(date)
            if dt:
                dates.append(dt)
        if not data.get('hasNext') or (dates and max(dates) < start):
            return items, True
        cursor = data.get('nextCursor')
        if not cursor or cursor in cursors:
            return items, False
        cursors.add(cursor)
        time.sleep(0.2)
    return items, False


def collect_hn(start, end):
    items = []
    for page in range(100):
        params = {'tags': 'story', 'numericFilters':
                  f'created_at_i>={int(start.timestamp())},created_at_i<{int(end.timestamp())},points>=50',
                  'hitsPerPage': 100, 'page': page}
        data, _ = get_json('https://hn.algolia.com/api/v1/search_by_date?' + urlencode(params))
        for row in data.get('hits', []):
            if row.get('url'):
                items.append(candidate(row.get('title', ''), row['url'], row['created_at'],
                                       'Hacker News', '人工智能', row.get('story_text') or ''))
        if page + 1 >= data.get('nbPages', 0):
            return items, True
        time.sleep(0.25)
    return items, False


def collect_source(feed, start, end):
    source, url, category = feed
    report = {'source': source, 'archiveComplete': False, 'methods': [], 'errors': []}
    items = []
    try:
        items.extend(fetch_feed(source, url, category, limit=None))
        report['methods'].append('full_rss')
    except Exception as exc:
        report['errors'].append('rss:' + type(exc).__name__)
    try:
        if source in WORDPRESS:
            extra, complete = collect_wordpress(source, category, start, end)
            items.extend(extra)
            report.update(archiveComplete=complete)
            report['methods'].append('wordpress_date_archive')
        elif source == 'Hacker News':
            extra, complete = collect_hn(start, end)
            items.extend(extra)
            report['archiveComplete'] = complete
            report['methods'].append('hn_date_search_points_50')
    except Exception as exc:
        report['errors'].append('archive:' + type(exc).__name__)
    items = [n for n in items if within(n, start, end)]
    report['count'] = len({canonical_url(n['url']) for n in items})
    report['oldestFound'] = min((n['_ts'] for n in items), default=None)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return items, report


def collect(start, end, output):
    all_items, reports = [], []
    try:
        items, complete = collect_aihot(start, end)
        report = {'source': 'AIHOT精选', 'count': len(items), 'archiveComplete': complete,
                  'methods': ['cursor_archive'], 'errors': [],
                  'oldestFound': min((n['_ts'] for n in items), default=None)}
        all_items.extend(items)
    except Exception as exc:
        report = {'source': 'AIHOT精选', 'count': 0, 'archiveComplete': False,
                  'errors': [type(exc).__name__]}
    reports.append(report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for items, report in pool.map(lambda feed: collect_source(feed, start, end), FEEDS):
            all_items.extend(items)
            reports.append(report)
    unique = {}
    for item in all_items:
        key = canonical_url(item['url'])
        if key not in unique or len(item.get('content', '')) > len(unique[key].get('content', '')):
            unique[key] = item
    result = {'start': start.isoformat(), 'end': end.isoformat(),
              'collectedAt': datetime.now(timezone.utc).isoformat(), 'sources': reports,
              'items': sorted(unique.values(), key=lambda n: n['_ts'])}
    write_json(output, result)
    print(json.dumps({'output': str(output), 'candidates': len(unique)}, ensure_ascii=False), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    start, end = aware(args.start), aware(args.end)
    if not start or not end or start >= end:
        parser.error('A valid start < end is required')
    collect(start, end, args.output)
