#!/usr/bin/env python3
"""Extend a history manifest using publisher sitemaps and public article metadata."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from enrich_news import canonical_url
from fetch_rss import UA
from news_export import read_json, write_json
from scripts.collect_news_history import aware, candidate, within


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.scripts, self.buffer = {}, [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('property') or attrs.get('name', '')] = attrs.get('content', '')
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self.buffer = []

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.buffer is not None:
            try:
                self.scripts.append(json.loads(''.join(self.buffer)))
            except ValueError:
                pass
            self.buffer = None


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def parse_article(html, url, source, category):
    parser = Metadata()
    parser.feed(html)
    article = next((n for script in parser.scripts for n in nodes(script)
                    if n.get('datePublished') and (n.get('headline') or n.get('name'))), {})
    meta = parser.meta
    return candidate(article.get('headline') or article.get('name') or meta.get('og:title', ''),
                     url, article.get('datePublished') or meta.get('article:published_time', ''),
                     source, category, article.get('description') or meta.get('description') or meta.get('og:description', ''),
                     article.get('articleBody', ''), meta.get('og:image', ''))


def request(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read(8_000_000).decode('utf-8', 'replace')


def months(start, end):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def extend(path, selected=None):
    manifest = read_json(path, {})
    start, end = aware(manifest['start']), aware(manifest['end'])
    existing = {canonical_url(n['url']): n for n in manifest['items']}
    sources = [
        ('The Verge', '消费电子', lambda y, m: f'https://www.theverge.com/sitemaps/entries/{y}/{m}'),
        ("Tom's Hardware", '半导体与先进制造', lambda y, m: f'https://www.tomshardware.com/sitemap-{y}-{m:02d}.xml'),
        ('Space.com', '商业航天', lambda y, m: f'https://www.space.com/sitemap-{y}-{m:02d}.xml'),
        ('Engadget', '消费电子', None),
    ]
    for source, category, sitemap in sources:
        if selected and source not in selected:
            continue
        report = next(r for r in manifest['sources'] if r['source'] == source)
        urls = set()
        errors = []
        maps = [sitemap(year, month) for year, month in months(start, end)] if sitemap else []
        if source == 'Engadget':
            try:
                root = ET.fromstring(request('https://www.engadget.com/sitemap_index.xml'))
                for entry in root:
                    fields = {n.tag.split('}')[-1]: n.text for n in entry}
                    modified = aware(fields.get('lastmod', ''))
                    if '/post-sitemap' in fields.get('loc', '') and (not modified or modified >= start):
                        maps.append(fields['loc'])
            except Exception as exc:
                errors.append({'url': 'https://www.engadget.com/sitemap_index.xml', 'error': type(exc).__name__})
        for map_url in maps:
            try:
                root = ET.fromstring(request(map_url))
                for entry in root:
                    fields = {n.tag.split('}')[-1]: n.text for n in entry}
                    modified = aware(fields.get('lastmod', ''))
                    if fields.get('loc') and (not modified or modified >= start):
                        urls.add(fields['loc'])
            except Exception as exc:
                errors.append({'url': map_url, 'error': type(exc).__name__})
        todo = sorted(url for url in urls if canonical_url(url) not in existing)
        print(json.dumps({'source': source, 'articlePagesToCheck': len(todo)}, ensure_ascii=False), flush=True)

        def fetch(url):
            try:
                item = parse_article(request(url), url, source, category)
                if not item['_ts'] or not item['title']:
                    return None, {'url': url, 'error': 'missing_publication_metadata'}
                return item if within(item, start, end) else None, None
            except Exception as exc:
                return None, {'url': url, 'error': type(exc).__name__}
            finally:
                time.sleep(0.4)

        added = 0
        with ThreadPoolExecutor(max_workers=3) as pool:
            for index, (item, error) in enumerate(pool.map(fetch, todo), 1):
                if item:
                    existing[canonical_url(item['url'])] = item
                    added += 1
                if error:
                    errors.append(error)
                if index % 50 == 0:
                    print(json.dumps({'source': source, 'checked': index, 'added': added, 'errors': len(errors)}), flush=True)
        report['methods'].append('monthly_sitemap_publication_metadata')
        report['sitemapErrors'] = errors
        report['archiveComplete'] = bool(urls) and not errors
        report['count'] = sum(n['source'] == source for n in existing.values())
        manifest['items'] = sorted(existing.values(), key=lambda n: aware(n['_ts']))
        write_json(path, manifest)
        print(json.dumps({'source': source, 'added': added, 'errors': len(errors), 'totalCandidates': len(existing)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest')
    parser.add_argument('--sources', help='Comma-separated source names to extend')
    args = parser.parse_args()
    extend(args.manifest, args.sources.split(',') if args.sources else None)
