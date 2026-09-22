import io
import unittest
from unittest.mock import patch

from fetch_rss import ArticleParagraph, FeedReturnedHTML, fetch_feed


class FeedTests(unittest.TestCase):
    def test_article_body_ignores_navigation_comments_and_scripts(self):
        parser = ArticleParagraph()
        parser.feed('<nav>Navigation</nav><div id="paragraph"><p>News</p><div>More</div><script>noise()</script></div><div>Comments</div>')
        self.assertEqual(' '.join(parser.parts), 'News More')

    def test_html_challenge_is_not_treated_as_empty_feed(self):
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'<!doctype html><html>Verify</html>')):
            with self.assertRaises(FeedReturnedHTML):
                fetch_feed('Example', 'https://example.com/feed', 'AI')

    def test_rss_with_unescaped_ampersand(self):
        xml = b'<rss><channel><item><title>AI & chips</title><link>https://example.com/news</link></item></channel></rss>'
        with patch('urllib.request.urlopen', return_value=io.BytesIO(xml)):
            items = fetch_feed('Example', 'https://example.com/feed', 'AI')
        self.assertEqual(items[0]['title'], 'AI & chips')


if __name__ == '__main__':
    unittest.main()
