import unittest
from unittest.mock import patch

import backfill_queue as b
from enrich_news import canonical_url
from scripts.collect_news_history import aware, within, collect_aihot
from scripts.collect_sitemap_history import parse_article
from scripts.collect_ithome_history import Archive


def item(number):
    return {'url': f'https://example.com/{number}', '_ts': '2026-09-16T10:00:00+00:00'}


class BackfillTests(unittest.TestCase):
    def test_ithome_archive_keeps_time_and_title(self):
        parser = Archive()
        parser.feed('<li><a class="c" data-ot="2026-09-12T23:38:55.0400000+08:00">Tech</a><a class="t" href="https://www.ithome.com/1/001/659.htm">Public story</a><i>23:38:55</i></li>')
        self.assertEqual(len(parser.items), 1)
        self.assertEqual(parser.items[0]['title'], 'Public story')
        self.assertTrue(parser.items[0]['_ts'].startswith('2026-09-12T23:38:55'))

    def test_sitemap_metadata_preserves_published_not_modified_date(self):
        html = '<script type="application/ld+json">{"@graph":[{"@type":"NewsArticle","headline":"Chip news","datePublished":"2026-09-13T10:00:00Z","dateModified":"2026-09-22T10:00:00Z","description":"Public summary"}]}</script>'
        parsed = parse_article(html, 'https://example.com/news', 'Example', 'AI')
        self.assertEqual(parsed['_ts'], '2026-09-13T10:00:00+00:00')
        self.assertEqual(parsed['summary'], 'Public summary')

    def test_modified_date_alone_is_not_a_publication_date(self):
        html = '<meta property="og:title" content="Story"><meta property="article:modified_time" content="2026-09-22T10:00:00Z">'
        self.assertEqual(parse_article(html, 'https://example.com/news', 'Example', 'AI')['_ts'], '')

    def test_reserves_half_for_history(self):
        fresh = [item(i) for i in range(100)]
        history = {n['url']: n for n in [item(i) for i in range(100, 200)]}
        batch = b.select_batch(fresh, history, 50, canonical_url)
        self.assertEqual(len(batch), 50)
        self.assertEqual(sum(n['url'] in history for n in batch), 25)

    def test_history_runs_without_fresh_news(self):
        history = {n['url']: n for n in [item(i) for i in range(100)]}
        self.assertEqual(len(b.select_batch([], history, 50, canonical_url)), 50)

    def test_duplicate_candidates_do_not_waste_capacity(self):
        fresh = [item(i) for i in range(10)]
        history = {n['url']: n for n in [item(i) for i in range(100)]}
        batch = b.select_batch(fresh, history, 50, canonical_url)
        self.assertEqual(len(batch), 50)
        self.assertEqual(len({n['url'] for n in batch}), 50)

    def test_short_history_does_not_limit_fresh(self):
        self.assertEqual(len(b.select_batch([item(i) for i in range(100)], {}, 50, canonical_url)), 50)

    def test_enqueue_deduplicates_existing_and_pending(self):
        manifest = {'start': 'a', 'end': 'b', 'sources': [], 'items': [item(1), item(2), item(2)]}
        state = {'items': {}}
        self.assertEqual(b.enqueue(manifest, state, {item(1)['url']}, canonical_url), 1)
        self.assertEqual(b.enqueue(manifest, state, set(), canonical_url), 1)
        self.assertEqual(len(state['items']), 2)

    def test_only_selected_history_is_removed(self):
        state = {'items': {n['url']: n for n in [item(1), item(2)]}}
        b.record(state, item(1), {'status': 'retry'}, canonical_url)
        b.record(state, item(3), {'status': 'success'}, canonical_url)
        self.assertEqual(state['processed'], 1)
        self.assertEqual(state['retryQueued'], 1)
        self.assertIn(item(2)['url'], state['items'])

    def test_handled_exclusion_is_not_requeued_after_seen_window_expires(self):
        state = {'items': {item(1)['url']: item(1)}}
        b.record(state, item(1), {'status': 'excluded'}, canonical_url)
        manifest = {'start': 'a', 'end': 'b', 'sources': [], 'items': [item(1)]}
        self.assertEqual(b.enqueue(manifest, state, set(), canonical_url), 0)

    def test_supplemental_manifest_is_sorted_by_date(self):
        early, late = item(1), item(2)
        early['_ts'] = '2026-09-12T00:00:00+08:00'
        state = {'items': {late['url']: late}}
        manifest = {'start': 'a', 'end': 'b', 'sources': [], 'items': [early]}
        b.enqueue(manifest, state, set(), canonical_url)
        self.assertEqual(next(iter(state['items'])), early['url'])

    def test_range_uses_beijing_midnight_and_rejects_unknown_dates(self):
        start, end = aware('2026-09-12T00:00:00+08:00'), aware('2026-09-23T00:00:00+08:00')
        self.assertTrue(within({'_ts': '2026-09-11T16:00:00Z'}, start, end))
        self.assertFalse(within({'_ts': '2026-09-11T15:59:59Z'}, start, end))
        self.assertFalse(within({'_ts': ''}, start, end))

    def test_aihot_paginates_and_stops_at_range_boundary(self):
        pages = [({'items': [{'title': 'Test', 'url': 'https://example.com/1', 'publishedAt': '2026-09-16T00:00:00Z'}],
                   'hasNext': True, 'nextCursor': 'next'}, {}),
                 ({'items': [{'title': 'Old', 'url': 'https://example.com/2', 'publishedAt': '2026-09-10T00:00:00Z'}],
                   'hasNext': True, 'nextCursor': 'older'}, {})]
        with patch('scripts.collect_news_history.get_json', side_effect=pages) as fetch, patch('scripts.collect_news_history.time.sleep'):
            items, complete = collect_aihot(aware('2026-09-12T00:00:00Z'), aware('2026-09-23T00:00:00Z'))
        self.assertTrue(complete)
        self.assertEqual(len(items), 1)
        self.assertIn('cursor=next', fetch.call_args.args[0])
