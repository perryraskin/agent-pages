"""Page kinds: the one table of Page shapes, their budgets and the writing rules.

Every reader of Page kinds (pages.py, check.py, the connector broker, Larry's iMessage plugin) imports this
module, so the numbers live here and nowhere else.

A Page's kind is stored in its meta.json ("kind"). New Pages get DEFAULT unless a kind is given at creation.
Pages without a kind (made before kinds existed) are not checked. The kind is the user's choice: it is set when the
Page is created and changed later only with `pages.py kind SLUG KIND`, never by a save. The one kind nobody
chooses is `dashboard` (no limit): it belongs to the status boards in DASHBOARDS and to nothing else.

Budgets are checked on the rendered Page body (not the masthead, tags, status card or footer), after every tab
of a Segmented view has been shown. "words" counts the summary line and all body text outside visuals
(diagram, sequence, table, bar chart, pie); a visual has its own limits instead.
"""
import json

DEFAULT = 'brief'

# Limits per kind. Missing key = no limit. min_* = at least that many.
KINDS = {
    'brief': {
        'label': 'Brief',
        'use': 'the default: a short answer, with at most one picture',
        'budget': {'words': 150, 'visuals': 1, 'tables': 1, 'table_rows': 5, 'boxes': 8, 'sections': 1, 'items': 5,
                   'tabs': 0},
        'shape': 'about 150 words, at most one visual (a diagram, a chart, or one table of at most 5 rows), '
                 'at most one section heading, at most 5 rows or bullets',
    },
    'diagram': {
        'label': 'Diagram',
        'use': 'one picture of how something fits together',
        'budget': {'words': 60, 'visuals': 1, 'min_diagrams': 1, 'tables': 0, 'boxes': 8, 'sections': 0,
                   'items': 3, 'tabs': 0},
        'shape': 'exactly one diagram of at most 8 boxes, about 60 words outside it, no tables',
    },
    'compare': {
        'label': 'Compare',
        'use': 'options side by side, with one pick',
        'budget': {'words': 150, 'visuals': 1, 'min_tables': 1, 'tables': 1, 'table_cols': 6, 'table_rows': 8,
                   'sections': 1, 'items': 3, 'tabs': 0},
        'shape': 'one table (at most 6 columns and 8 rows), one clear pick, about 150 words outside the table',
    },
    'report': {
        'label': 'Report',
        'use': 'long form, only when the user asks for a full report or a deep dive',
        'budget': {'words': 1200, 'visuals': 5, 'tables': 3, 'table_rows': 15, 'boxes': 12, 'sections': 6,
                   'items': 30, 'tabs': 4},
        'shape': 'long form with a ceiling: about 1,200 words, at most 6 sections, 3 tables (15 rows each) '
                 'and 5 visuals in all',
    },
    'dashboard': {
        'label': 'Dashboard',
        'use': 'a status board that a scheduled job rewrites; never chosen, only the Pages in DASHBOARDS',
        'budget': {},
        'shape': 'no size limit',
    },
}
# A status board is not an answer to the user, so it has no budget. Nobody can pick this kind: only the slugs
# listed here have it, they get it when they are created, and they cannot be given another kind.
DASHBOARD = 'dashboard'
DASHBOARDS = ('fleet-health', 'fleet-roster-auto', 'routing-log')
# The kinds a Page can be given by choice (CLI --kind, the broker's kind=, Larry's page.kind).
NAMES = tuple(k for k in KINDS if k != DASHBOARD)

# What each budget key means, for the rejection message ("brief allows 150 words, this has 412").
_NOUNS = {
    'words': ('words', 'words'), 'visuals': ('visual', 'visuals'), 'tables': ('table', 'tables'),
    'table_rows': ('table row', 'table rows'), 'table_cols': ('table column', 'table columns'),
    'boxes': ('diagram box', 'diagram boxes'), 'sections': ('section heading', 'section headings'),
    'items': ('row or bullet', 'rows or bullets'), 'tabs': ('tab', 'tabs'),
}
# Measured value for each budget key (table_rows/cols/boxes are per visual: the largest one counts).
_MEASURE = {'table_rows': 'max_table_rows', 'table_cols': 'max_table_cols', 'boxes': 'max_boxes'}


def normalize(kind, slug=None):
    """A valid kind name or ValueError. With `slug`, the kind must also suit that Page: a status board
    (DASHBOARDS) is always a dashboard, and no other Page can be one."""
    k = str(kind or '').strip().lower()
    if slug in DASHBOARDS:
        if k != DASHBOARD:
            raise ValueError(f'{slug} is a status board and stays a {DASHBOARD} (no size limit); to change that, '
                             f'take it out of DASHBOARDS in scripts/page_kinds.py')
        return k
    if k == DASHBOARD:
        raise ValueError(f'{DASHBOARD} cannot be chosen: it is only for the status boards in DASHBOARDS '
                         f'(scripts/page_kinds.py): {", ".join(DASHBOARDS)}')
    if k not in NAMES:
        raise ValueError(f'kind must be one of {", ".join(NAMES)} (got {kind!r})')
    return k


def for_new(slug, kind=None):
    """The kind a new Page gets: a status board is a dashboard whatever was asked, any other Page gets `kind`
    (default brief)."""
    return DASHBOARD if slug in DASHBOARDS else normalize(kind or DEFAULT, slug)


def _n(count, key):
    one, many = _NOUNS[key]
    return f'{count:,} {one if count == 1 else many}'


def overages(kind, m):
    """Budget overages of measured Page `m` (from MEASURE_JS) as plain sentences; [] when it fits."""
    if kind not in KINDS or not isinstance(m, dict):
        return []
    out = []
    for key, limit in KINDS[kind]['budget'].items():
        if key.startswith('min_'):
            what = key[4:]
            have = m.get(what, 0)
            if have < limit:
                noun = 'diagram' if what == 'diagrams' else 'table'
                out.append(f'{kind} needs {limit} {noun}{"" if limit == 1 else "s"}, this has {have}')
            continue
        have = m.get(_MEASURE.get(key, key), 0) or 0
        if have > limit:
            per = ' in one visual' if key in _MEASURE else ''
            out.append(f'{kind} allows {_n(limit, key)}{per}, this has {have:,}')
    return out


def rejection(kind, over):
    """The message a writer gets when a save is over its kind's budget."""
    lines = [f'NOT SAVED: this Page is a {kind} and is over its budget:']
    lines += [f'- {o}' for o in over]
    lines += ['Cut it down until it fits; do not change the kind (that is the user\'s choice). '
              'Leave out anything he did not ask for; detail belongs in your final message, not the Page.']
    return '\n'.join(lines)


WRITING_RULES = [
    "Answer the user's own words, nothing more. Lead with the answer or the picture.",
    'Plain words and short sentences: he reads on his phone.',
    'Leave out how you found it, evidence trails, caveats about what you did not do, IDs, hashes, file paths '
    'and exact timestamps.',
    'Detail goes in your final message, not the Page.',
    'Diagram boxes: a label of up to 3 words and a detail of up to 8.',
]


def kinds_table():
    """One line per kind, for the components reference."""
    return '\n'.join(f'- {name}{" (default)" if name == DEFAULT else ""}: {k["use"]}; {k["shape"]}.'
                     for name, k in KINDS.items() if name in NAMES)


def writer_block(kind=None):
    """What a Page writer is told about shape and length. With a kind: this Page's budget; without: all kinds."""
    head = (f'This Page is a {kind}: {KINDS[kind]["shape"]}.' if kind in KINDS else
            f'Page kinds (a new Page is a {DEFAULT} unless the user asked for another shape):\n{kinds_table()}')
    return '\n'.join([
        head,
        'A save over the budget is rejected and the old version stays; cut it rather than change the kind '
        '(the kind is the user\'s choice).',
        'Writing rules:', *[f'- {r}' for r in WRITING_RULES],
    ])


def kind_of(meta):
    """The stored kind of a Page's meta dict, or None for an unchecked (pre-kinds) Page."""
    k = (meta or {}).get('kind')
    return k if k in KINDS else None


# Runs inside the rendered Page (headless Chrome, check.py). measure() looks at the current view; merge()
# keeps, for every distinct piece of content, the most times it was seen in any one view, so every tab of a
# Segmented view counts once.
MEASURE_JS = r'''
window.__hpKinds = (() => {
  const VIS = '.diagram, .table-wrap, .bars, .pie';
  const ITEMS = '.rows > li, .bullets > li, .numbered > li, .checklist > li, .steps > li, .properties > .prop, ' +
                '.metrics > .metric, .linkcards > a, .proscons li';
  const words = s => (s || '').split(/\s+/).filter(w => /[A-Za-z0-9]/.test(w)).length;
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const seen = {};  // bucket -> key -> {n, w, ...}
  const add = (bucket, list) => {
    const b = (seen[bucket] ??= {}), counts = {};
    for (const it of list) {
      const k = it.key; counts[k] = (counts[k] || 0) + 1;
      if (!b[k] || b[k].n < counts[k]) b[k] = { ...it, n: counts[k] };
    }
  };
  function measure() {
    const body = document.querySelector('.page-body');
    if (!body) return;
    const texts = [];
    const sum = document.querySelector('.page-summary');
    if (sum) texts.push({ key: 'summary|' + norm(sum.textContent), w: words(sum.textContent) });
    const walk = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const t = norm(n.nodeValue);
      if (!t || n.parentElement.closest(VIS + ', .segmented, details, script, style')) continue;
      texts.push({ key: 't|' + t, w: words(t) });
    }
    add('texts', texts);
    add('visuals', [...body.querySelectorAll(VIS)].filter(v => !v.parentElement.closest(VIS)).map(v => {
      const table = v.matches('.table-wrap');
      const rows = table ? v.querySelectorAll('tbody tr').length : 0;
      const cols = table ? Math.max(0, ...[...v.querySelectorAll('tr')].map(r => r.children.length)) : 0;
      return { key: 'v|' + v.className + '|' + norm(v.textContent).slice(0, 400),
               type: table ? 'table' : v.matches('.diagram') ? 'diagram' : 'chart',
               rows, cols,
               // a Diagram draws its boxes twice (wide and phone layouts): count the first drawing only
               boxes: v.matches('.diagram') ? (v.querySelector('svg')?.querySelectorAll('.node').length || 0) : 0 };
    }));
    add('sections', [...body.querySelectorAll('.section > h2')].map(h => ({ key: 's|' + norm(h.textContent) })));
    add('items', [...body.querySelectorAll(ITEMS)].map(li => ({ key: 'i|' + norm(li.textContent).slice(0, 300) })));
    add('tabs', [...body.querySelectorAll('.seg')].map(s => ({ key: 'g|' + norm(s.textContent) })));
  }
  function result() {
    const all = b => Object.values(seen[b] || {});
    const total = (b, f) => all(b).reduce((s, it) => s + it.n * (f ? f(it) : 1), 0);
    const vis = all('visuals');
    const ofType = t => vis.filter(v => v.type === t).reduce((s, v) => s + v.n, 0);
    return { words: total('texts', it => it.w), visuals: total('visuals'), diagrams: ofType('diagram'),
             tables: ofType('table'), charts: ofType('chart'),
             max_table_rows: Math.max(0, ...vis.map(v => v.rows)), max_table_cols: Math.max(0, ...vis.map(v => v.cols)),
             max_boxes: Math.max(0, ...vis.map(v => v.boxes)), sections: total('sections'), items: total('items'),
             tabs: all('tabs').length };
  }
  return { measure, result };
})();
'''


if __name__ == '__main__':  # print the table, for people
    print(json.dumps(KINDS, indent=1))
