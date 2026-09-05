"""Export existing articles without fetching feeds or calling a model."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from enrich_news import read_existing, _frontend_slice, LIST_KEYS
from news_export import export_news

items = read_existing()
text = Path('news_data_latest.js').read_text(encoding='utf-8')
digest = json.loads(text.split(';\nvar newsDigest = ', 1)[1].strip().removesuffix(';'))
front = [{k: n[k] for k in LIST_KEYS if k in n} for n in _frontend_slice(items)]
version = export_news(items, front, digest)
print(json.dumps({'articles': len(items), 'version': version}))
