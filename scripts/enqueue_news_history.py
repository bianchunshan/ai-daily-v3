#!/usr/bin/env python3
"""Import a dated manifest without racing the existing scheduled updater."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backfill_queue as backfill
from enrich_news import canonical_url, read_existing, read_seen
from news_export import read_json, write_json
from scripts.collect_news_history import aware, within
from scripts.run_local_grok_update import LOCK_FILE, REPO_DIR, push_changes


def enqueue_manifest(path):
    with Path(path).open() as handle:
        manifest = json.load(handle)
    start, end = aware(manifest['start']), aware(manifest['end'])
    if not start or not end or start >= end or any(not within(n, start, end) for n in manifest['items']):
        raise ValueError('Every candidate must have a verified date within the requested range')
    with LOCK_FILE.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.chdir(REPO_DIR)
        existing = read_existing()
        known = set(read_seen(existing)) | {canonical_url(n['url']) for n in existing}
        known.update(read_json('retry_queue.json', {}))
        state = backfill.load()
        added = backfill.enqueue(manifest, state, known, canonical_url)
        backfill.save(state)
        status = read_json('data/status.json', {})
        status['backfill'] = backfill.progress(state)
        write_json('data/status.json', status)
        if not push_changes():
            raise RuntimeError('Queue saved locally; publication pending next scheduled update')
        print(json.dumps({'enqueued': added, **backfill.progress(state)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest')
    args = parser.parse_args()
    enqueue_manifest(args.manifest)
