import tempfile
import unittest
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import enrich_news as e

class PipelineTests(unittest.TestCase):
    def test_temporary_failure_is_not_exclusion(self):
        with patch.object(e,'enrich_one',side_effect=TimeoutError()):
            self.assertEqual(e.process_one({'url':'https://example.org'})['status'],'retry')
        with patch.object(e,'enrich_one',return_value=None):
            self.assertEqual(e.process_one({'url':'https://example.org'})['status'],'excluded')

    def test_retry_backoff_and_exhaustion(self):
        queue={};raw={'url':'https://example.org/story','title':'测试'}
        with patch.object(e.time,'time',return_value=1000):
            e.update_retry(queue,raw,{'status':'retry','error':'TimeoutError'})
            self.assertEqual(queue[raw['url']]['nextAttemptAt'],1600)
            for _ in range(4):e.update_retry(queue,raw,{'status':'retry','error':'TimeoutError'})
            self.assertTrue(queue[raw['url']]['exhausted'])
            e.update_retry(queue,raw,{'status':'success'})
            self.assertEqual(queue,{})

    def test_title_requires_chinese_independently(self):
        item={'title':'NVIDIA launches new GPU','summary':'中文摘要'*20,'body':'中文正文'*30}
        self.assertFalse(e.is_usable_chinese_item(item))
        item['title']='英伟达发布新款GPU'
        self.assertTrue(e.is_usable_chinese_item(item))

if __name__=='__main__':unittest.main()
