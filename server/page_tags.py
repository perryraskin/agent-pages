"""Shared, offline Page tagging and discovery. Agents own tags, never the reader."""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{0,120}$')
ALIASES = {}
RULES = {}


def normalize_tags(tags):
    if not isinstance(tags, list) or not tags or len(tags) > 16:
        raise ValueError('tags must be a nonempty list of at most 16 descriptive strings')
    out = []
    for tag in tags:
        if not isinstance(tag, str):
            raise ValueError('each tag must be a string')
        tag = unicodedata.normalize('NFKD', tag.strip().lower()).encode('ascii', 'ignore').decode()
        tag = re.sub(r'[^a-z0-9]+', '-', tag).strip('-')
        tag = ALIASES.get(tag, tag)
        if not tag or len(tag) > 48:
            raise ValueError('each tag must contain letters or numbers and be at most 48 characters')
        if tag not in out:
            out.append(tag)
    return sorted(out)


def infer_tags(slug, title, tsx=''):
    # Title/slug dominate: unrelated product mentions in long fleet tables must not pollute tags.
    text = re.sub(r'[-_]', ' ', slug) + ' ' + title.lower()
    tags = [tag for tag, pattern in RULES.items() if re.search(pattern, text, re.I)]
    if not tags:
        # Extract meaningful subject words, never TSX/component names or arbitrary private body text.
        stop = {'the', 'and', 'for', 'with', 'from', 'page', 'new', 'untitled', 'a', 'an', 'to', 'of'}
        tags = [w for w in re.findall(r'[a-z][a-z0-9]{2,}', text.lower()) if w not in stop][:4]
    return normalize_tags(tags or ['reference'])


def ensure_tags(slug, meta, tsx=''):
    meta = dict(meta)
    meta['tags'] = (normalize_tags(meta['tags']) if 'tags' in meta
                    else infer_tags(slug, meta.get('title', slug), tsx))
    return meta


def catalog(root=ROOT, query='', tags=None, status=None):
    """Pages matching every query word and tag. Each carries `status` (work status; see page_work.py),
    and status='working'|'stalled'|... keeps only Pages in that state."""
    from page_work import load as load_work, public as public_work  # sibling module; lazy to avoid a cycle
    required = set(normalize_tags(tags)) if tags else set()
    terms = re.findall(r'[a-z0-9]+', query.lower())
    pages = []
    for m in sorted((Path(root) / 'src').glob('*/meta.json')):
        if not SLUG.fullmatch(m.parent.name):
            continue
        meta = ensure_tags(m.parent.name, json.loads(m.read_text()))
        haystack = ' '.join([m.parent.name, meta.get('title', ''), *meta['tags']]).lower()
        haystack = re.sub(r'[^a-z0-9]+', ' ', haystack)
        if not required.issubset(meta['tags']) or not all(term in haystack for term in terms):
            continue
        work = public_work(load_work(root, m.parent.name))
        if status and work['state'] != status:
            continue
        pages.append({'slug': m.parent.name, **meta, 'status': work})
    return sorted(pages, key=lambda p: p.get('updated_at', ''), reverse=True)


def tag_counts(pages):
    return dict(sorted(Counter(t for p in pages for t in p['tags']).items()))


TAG_STYLE = """.hp-tag-bar{display:flex;flex-wrap:wrap;gap:6px;max-width:1120px;margin:18px auto 0;padding:0 20px;font:500 12px/1.5 -apple-system,BlinkMacSystemFont,sans-serif;color:#52796c}.hp-tag-bar span{max-width:100%;overflow-wrap:anywhere;border-radius:999px;padding:4px 10px;background:rgba(82,121,108,.09)}@media(prefers-color-scheme:dark){.hp-tag-bar{color:#a5c4b7}.hp-tag-bar span{background:rgba(165,196,183,.10)}}"""


def tag_header(tags):
    import html
    tags = normalize_tags(tags)
    chips = ''.join('<span>' + html.escape(t) + '</span>' for t in tags)
    return ('<!--hermes-page-tags:start--><style>' + TAG_STYLE + '</style>'
            '<aside class="hp-tag-bar" aria-label="Page tags">' + chips + '</aside><!--hermes-page-tags:end-->')


def decorate_content(raw, tags):
    # Outside React's root: metadata-only retags never break hydration or require a library fetch.
    header = tag_header(tags)
    if '<!--hermes-page-tags:start-->' in raw:
        return re.sub(r'<!--hermes-page-tags:start-->[\s\S]*?<!--hermes-page-tags:end-->', lambda _: header, raw, count=1)
    return re.sub(r'<body\b[^>]*>', lambda m: m.group(0) + header, raw, count=1, flags=re.I)


if __name__ == '__main__':
    # Build gate: direct builder invocations cannot publish untagged Pages either.
    import sys
    errors = []
    headers = {}
    for base in ('src', 'samples'):
        for m in (ROOT / base).glob('*/meta.json'):
            try:
                headers[m.parent.name] = tag_header(json.loads(m.read_text()).get('tags'))
            except ValueError as e:
                errors.append(m.parent.name + ': ' + str(e))
    if errors:
        sys.exit('\n'.join(errors))
    if '--headers' in sys.argv:
        print(json.dumps(headers))
