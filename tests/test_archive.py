import os
from pathlib import Path
import tempfile
import unittest

import enrich_news as news
from news_export import read_json, write_status
from scripts.restore_news_archive import missing_articles


def article(number):
    return {'id': f'{number:016x}', 'url': f'https://example.org/{number}', 'title': 'Archived article',
            'body': 'Existing enriched content', 'category': 'AI', 'ts': '2026-09-12T00:00:00+08:00'}


class ArchiveTests(unittest.TestCase):
    def test_category_over_2000_keeps_every_article_and_stable_id(self):
        original = [article(i) for i in range(2100)]
        merged = news.merge_articles([article(2100)] + original)
        self.assertEqual(len(merged), 2101)
        self.assertTrue({n['id'] for n in original}.issubset({n['id'] for n in merged}))
        self.assertLessEqual(len(news._frontend_slice(merged)), news.FRONTEND_MAX)

    def test_merge_prefers_repaired_content_without_duplicate_urls(self):
        old = article(1)
        new = {**old, 'body': 'Repaired', 'url': old['url'] + '?utm_source=test'}
        merged = news.merge_articles([new, old])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['body'], 'Repaired')
        self.assertEqual(merged[0]['id'], old['id'])

    def test_recovery_does_not_replace_current_or_duplicate_articles(self):
        one, two = article(1), article(2)
        self.assertEqual(missing_articles([one], [one, two, two]), [two])
        self.assertEqual(missing_articles([one, two], [one, two]), [])

    def test_corrupt_archive_is_not_treated_as_empty(self):
        before = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertEqual(news.read_existing(), [])
                Path('news_data_latest.js').write_text('var newsData = [broken];')
                with self.assertRaises(ValueError):
                    news.read_existing()
            finally:
                os.chdir(before)

    def test_status_partial_and_recovery_preserve_last_ingestion(self):
        before = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                first = write_status(added=1, sources=[{'ok': True}])
                for change in [{'pending': 1}, {'exhausted': 15}, {'sources': [{'ok': True}, {'ok': False}]}]:
                    self.assertEqual(write_status(**change)['state'], 'partial')
                self.assertEqual(write_status(sources=[{'ok': False}])['state'], 'error')
                self.assertEqual(write_status(sources=[{'ok': True}])['state'], 'ok')
                self.assertEqual(read_json('data/status.json', {})['lastIngestedAt'], first['lastIngestedAt'])
            finally:
                os.chdir(before)
