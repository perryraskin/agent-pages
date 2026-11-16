"""Explicit synthetic saves. Never touches the library server or private Pages."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
import page_work as work
ROOT = Path(__file__).resolve().parents[2] / 'apps/web/build/working'
SLUG = 'studio'

def advance(stage):
    rec = work.load(ROOT, SLUG) if stage != 'start' else None
    rec = work.new_record(rec, 'done' if stage == 'done' else 'working',
        by='Aster', note={'start':'Shaping the afternoon.', 'reveal':'Adding the finishing touch.', 'done':'Ready for a creative afternoon.'}[stage],
        sections=['Plan=done', 'Details=' + ('working' if stage == 'start' else 'done')])
    rev = 'aaa' if stage == 'start' else 'bbb'
    raw = (ROOT / ('before.html' if stage == 'start' else 'after.html')).read_text()
    raw = raw.replace('<!--WORK-->', work.block(SLUG, rev, rec))
    target = ROOT / 'build' / (SLUG + '.html')
    if stage == 'start':
        for f in work.live_files(ROOT, SLUG):
            f.unlink(missing_ok=True)
    work.record_edit(ROOT, SLUG, target.read_text() if target.exists() else '', raw, 'Aster')
    work._atomic_write(target, raw)
    work.save(ROOT, SLUG, rec)
    work.sync(ROOT, SLUG, rec)

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['start','reveal','done'])
    advance(p.parse_args().stage)
