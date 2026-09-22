"""Backfill accounting; the regular runner owns all writes under its existing lock."""
from datetime import datetime
from news_export import read_json, write_json

FILE = 'backfill_queue.json'


def load():
    return read_json(FILE, {'items': {}, 'processed': 0, 'imported': 0, 'excluded': 0, 'retryQueued': 0})


def progress(state):
    return {k: state.get(k, 0) for k in ('processed', 'imported', 'excluded', 'retryQueued')} | {
        'pending': len(state.get('items', {})), 'start': state.get('start'), 'end': state.get('end')}


def select_batch(fresh, history, cap, canonical, history_cap=25):
    """Reserve room for both streams, using unused slots for the other stream."""
    historical = list(history.values())
    budget = min(max(0, history_cap), cap, len(historical))
    regular = fresh[:cap - budget]
    selected = regular + historical[:cap - len(regular)]
    selected += fresh[len(regular):]
    selected += historical[cap - len(regular):]
    unique = {}
    for item in selected:
        unique.setdefault(canonical(item['url']), item)
    return list(unique.values())[:cap]


def record(state, raw, outcome, canonical):
    key = canonical(raw['url'])
    if state.get('items', {}).pop(key, None) is None:
        return
    state.setdefault('handled', []).append(key)
    state['processed'] = state.get('processed', 0) + 1
    field = {'success': 'imported', 'excluded': 'excluded', 'retry': 'retryQueued'}[outcome['status']]
    state[field] = state.get(field, 0) + 1


def save(state):
    if state.get('start'):
        write_json(FILE, state)


def enqueue(manifest, state, known, canonical):
    state.setdefault('items', {})
    known = set(known) | set(state.get('handled', []))
    added = 0
    for item in manifest['items']:
        key = canonical(item['url'])
        if key not in known and key not in state['items']:
            state['items'][key] = item
            added += 1
    state['items'] = dict(sorted(state['items'].items(), key=lambda pair: datetime.fromisoformat(pair[1]['_ts'])))
    reports = {r['source']: r for r in state.get('sources', [])}
    reports.update({r['source']: r for r in manifest['sources']})
    state.update(start=manifest['start'], end=manifest['end'], sources=list(reports.values()))
    state['collected'] = len(manifest['items'])
    state['enqueued'] = state.get('enqueued', 0) + added
    return added
