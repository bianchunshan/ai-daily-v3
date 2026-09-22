#!/usr/bin/env python3
"""Read IT Home's public daily archives; article bodies are fetched by the updater."""
import argparse
from datetime import timedelta, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from news_export import write_json
from scripts.collect_news_history import aware, candidate, within
from scripts.collect_sitemap_history import request


class Archive(HTMLParser):
    def __init__(self):
        super().__init__()
        self.item, self.capture, self.items = None, False, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'li':
            self.item = {'date': '', 'url': '', 'title': []}
        if self.item is not None and tag == 'a':
            if attrs.get('data-ot'):
                self.item['date'] = attrs['data-ot']
            if attrs.get('class') == 't':
                self.item['url'] = attrs.get('href', '')
                self.capture = True

    def handle_data(self, data):
        if self.capture and self.item is not None:
            self.item['title'].append(data)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.capture = False
        if tag == 'li' and self.item is not None:
            if self.item['url'] and self.item['date']:
                self.items.append(candidate(''.join(self.item['title']), self.item['url'],
                                            self.item['date'], 'IT之家', '消费电子'))
            self.item = None


def collect(start, end, output):
    day = start.astimezone(timezone(timedelta(hours=8))).date()
    last = end.astimezone(timezone(timedelta(hours=8))).date()
    items, errors, days = [], [], []
    while day <= last:
        url = f'https://www.ithome.com/list/{day.isoformat()}.html'
        try:
            parser = Archive()
            parser.feed(request(url))
            if not parser.items:
                raise ValueError('No dated archive entries')
            if any(not n['_ts'] for n in parser.items):
                raise ValueError('Unparseable archive publication dates')
            found = [n for n in parser.items if within(n, start, end)]
            items.extend(found)
            days.append({'date': day.isoformat(), 'count': len(found)})
            print(json.dumps(days[-1]), flush=True)
        except Exception as exc:
            errors.append({'url': url, 'error': type(exc).__name__})
        day += timedelta(days=1)
        time.sleep(0.3)
    report = {'source': 'IT之家', 'count': len(items), 'archiveComplete': not errors,
              'methods': ['daily_public_archive'], 'errors': errors, 'days': days}
    write_json(output, {'start': start.isoformat(), 'end': end.isoformat(),
                        'sources': [report], 'items': sorted(items, key=lambda n: aware(n['_ts']))})
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    collect(aware(args.start), aware(args.end), args.output)
