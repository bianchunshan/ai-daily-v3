"""Versioned JSON exports shared by the updater and the website."""
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path('data')


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(filename, value):
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == encoded:
        return
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(encoded, encoding='utf-8')
    os.replace(temp, path)


def read_json(filename, default):
    try:
        return json.loads(Path(filename).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def export_news(items, front, digest):
    index, shards = [], {}
    for n in items:
        index.append({
            **{k: n.get(k, '') for k in ('id', 'title', 'category', 'source', 'ts', 'url')},
            'summary': str(n.get('summary', ''))[:180],
            'tags': n.get('tags', [])[:6],
            'stocks': [{k: s.get(k, '') for k in ('name', 'ticker')} for s in n.get('stocks', [])[:4]],
        })
        shards.setdefault(str(n['id'])[:2], {})[str(n['id'])] = n
    version = hashlib.sha256(json.dumps(index, ensure_ascii=False).encode()).hexdigest()[:16]
    for shard, articles in shards.items():
        write_json(DATA_DIR / 'articles' / (shard + '.json'), articles)
    write_json(DATA_DIR / 'index.json', index)
    write_json(DATA_DIR / 'feed.json', {
        'version': version, 'items': front, 'digest': digest, 'total': len(items),
        'categories': dict(Counter(n.get('category', '') for n in items)),
        'sources': dict(Counter(n.get('source', '') for n in items)),
    })
    return version


def write_status(*, added=0, total=None, latest=None, pending=0, exhausted=0, sources=None, error=None):
    previous = read_json(DATA_DIR / 'status.json', {})
    timestamp = now()
    if sources and not any(source.get('ok') for source in sources):
        error = error or 'all_sources_failed'
    status = {
        **previous, 'checkedAt': timestamp, 'added': added,
        'pendingRetries': pending, 'exhaustedRetries': exhausted,
        'state': 'error' if error else 'ok', 'error': error,
    }
    if total is not None:
        status['total'] = total
    if latest:
        status['latestPublishedAt'] = latest
    if added:
        status['lastIngestedAt'] = timestamp
    if sources is not None:
        status['sources'] = sources
    write_json(DATA_DIR / 'status.json', status)
    return status
