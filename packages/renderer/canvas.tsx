// Hermes stand-in for Grok Bot's `grok/canvas` page toolkit.
// Pages import components and hooks from 'grok/canvas'; the build aliases that import here.
// Everything renders to plain semantic HTML so the server-rendered page reads fine without JS;
// interactive bits (Segmented) hydrate when JS is available.
import React, { useState, useMemo, useEffect, useRef, useCallback, useId, Fragment } from 'react';

export { useState, useMemo, useEffect, useRef, useCallback, Fragment };

type Kids = { children?: React.ReactNode };
type Tone = 'info' | 'success' | 'warning' | 'danger' | string;

const cx = (...c: (string | false | undefined | null)[]) => c.filter(Boolean).join(' ');
const isUrl = (s: string) => /^https?:\/\//.test(s);
const host = (s: string) => { try { return new URL(s).hostname.replace(/^www\./, ''); } catch { return s; } };
const toneClass = (t?: Tone) => (t ? `tone-${t}` : 'tone-neutral');

// Values may be plain text/nodes or { text|label, tone } objects (coloured text).
type Val = React.ReactNode | { text?: React.ReactNode; label?: React.ReactNode; tone?: Tone };
const isToned = (v: any): v is { text?: React.ReactNode; label?: React.ReactNode; tone?: Tone } =>
  v && typeof v === 'object' && !React.isValidElement(v) && !Array.isArray(v) && ('text' in v || 'label' in v);
const val = (v: Val): React.ReactNode =>
  isToned(v) ? <span className={cx('toned', v.tone && toneClass(v.tone))}>{v.text ?? v.label}</span> : (v as React.ReactNode);

export function Page({ title, summary, width, sources, children }:
  Kids & { title?: string; summary?: string; width?: 'column' | 'wide' | string; sources?: string[] }) {
  return (
    <main className={cx('page', width === 'wide' ? 'page-wide' : 'page-column')} id="top">
      <header className="page-masthead" aria-label="Hermes Pages">
        <div className="page-brand">Hermes</div>
        <p className="page-byline">Made for you</p>
      </header>
      <article className="page-paper">
      <header className="page-head">
        {title && <h1>{title}</h1>}
        {summary && <p className="page-summary">{summary}</p>}
      </header>
      <div className="page-body">{children}</div>
      {sources && sources.length > 0 && (
        <footer className="page-sources">
          <h2>Sources</h2>
          <ol>{sources.map((s, i) => <li key={i}>{isUrl(s) ? <a href={s}>{host(s)}</a> : s}</li>)}</ol>
        </footer>
      )}
      </article>
    </main>
  );
}

export function Section({ heading, caption, id, children }: Kids & { heading?: string; caption?: string; id?: string }) {
  return (
    <section className="section" id={id}>
      {heading && <h2>{heading}</h2>}
      {caption && <p className="caption">{caption}</p>}
      <div className="section-body">{children}</div>
    </section>
  );
}

export function Text({ children }: Kids) {
  if (typeof children === 'string' && children.includes('\n\n'))
    return <>{children.split(/\n{2,}/).map((p, i) => <p key={i} className="text">{p}</p>)}</>;
  return <p className="text">{children}</p>;
}

export function Callout({ tone, lead, children }: Kids & { tone?: Tone; lead?: string }) {
  return (
    <aside className={cx('callout', toneClass(tone))}>
      {lead && <strong className="callout-lead">{lead}</strong>}
      {children && <div className="callout-body">{children}</div>}
    </aside>
  );
}

export function Quote({ cite, children }: Kids & { cite?: string }) {
  return (
    <blockquote className="quote">
      <div>{children}</div>
      {cite && <cite>{isUrl(cite) ? <a href={cite}>{host(cite)}</a> : cite}</cite>}
    </blockquote>
  );
}

export function Divider() { return <hr className="divider" />; }

export function BackToTop() { return <p className="back-to-top"><a href="#top">↑ Back to top</a></p>; }

export function Group({ children }: Kids) { return <div className="group">{children}</div>; }

export function View({ children }: Kids) { return <div className="view">{children}</div>; }

export function Grid({ columns = 2, children }: Kids & { columns?: number }) {
  return <div className="grid" style={{ ['--cols' as any]: columns }}>{children}</div>;
}

export function Status({ tone, children }: Kids & { tone?: Tone }) {
  return <span className={cx('status', toneClass(tone))}>{children}</span>;
}

export function Table({ columns = [], align = [], rows = [], emphasis }:
  { columns?: Val[]; align?: string[]; rows?: Val[][]; emphasis?: number }) {
  const al = (i: number) => (align[i] === 'end' ? 'right' : align[i] === 'center' ? 'center' : 'left');
  return (
    <div className="table-wrap" data-columns={columns.length} data-mobile-layout={columns.length >= 3 ? "cards" : "table"}>
      <table className="table" role="table">
        {columns.length > 0 && (
          <thead role="rowgroup"><tr role="row">{columns.map((c, i) => <th role="columnheader" key={i} scope="col" style={{ textAlign: al(i) }}>{val(c)}</th>)}</tr></thead>
        )}
        <tbody role="rowgroup">
          {rows.map((r, ri) => (
            <tr role="row" key={ri}>{r.map((cell, ci) => (
              <td role="cell" key={ci} style={{ textAlign: al(ci) }} className={ci === emphasis ? 'em' : undefined}>{columns[ci] != null && <span className="table-cell-label" aria-hidden="true">{val(columns[ci])}</span>}<span className="table-cell-value">{val(cell)}</span></td>
            ))}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Properties({ items = [] }: { items?: { label: string; value: Val }[] }) {
  return (
    <dl className="properties">
      {items.map((it, i) => <div key={i} className="prop"><dt>{it.label}</dt><dd>{val(it.value)}</dd></div>)}
    </dl>
  );
}

export function Rows({ rows = [] }: { rows?: { title: string; detail?: string; status?: { label: string; tone?: Tone } }[] }) {
  return (
    <ul className="rows">
      {rows.map((r, i) => (
        <li key={i} className="row">
          <div className="row-main">
            <span className="row-title">{r.title}</span>
            {r.detail && <span className="row-detail">{val(r.detail)}</span>}
          </div>
          {r.status && <Status tone={r.status.tone}>{r.status.label}</Status>}
        </li>
      ))}
    </ul>
  );
}

type Opt = string | { label: string; value: string };
const optValue = (o: Opt) => (typeof o === 'string' ? o : o.value);
const optLabel = (o: Opt) => (typeof o === 'string' ? o : o.label);

export function Segmented({ options = [], value, onChange }: { options?: Opt[]; value?: string; onChange?: (v: string) => void }) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o, i) => {
        const v = optValue(o);
        return (
          <button key={i} type="button" role="tab" aria-selected={v === value}
            className={cx('seg', v === value && 'seg-on')} onClick={() => onChange && onChange(v)}>
            {optLabel(o)}
          </button>
        );
      })}
    </div>
  );
}

export function Checklist({ items = [] }: { items?: { text: string; done?: boolean; meta?: string }[] }) {
  return (
    <ul className="checklist">
      {items.map((it, i) => (
        <li key={i} className={cx('check', it.done && 'check-done')}>
          <span className="box" aria-hidden="true">{it.done ? '✓' : ''}</span>
          <span className="check-text">{val(it.text)}{it.meta && <span className="meta"> · {it.meta}</span>}</span>
        </li>
      ))}
    </ul>
  );
}

export function Steps({ steps = [] }: { steps?: { title: string; detail?: string }[] }) {
  return (
    <ol className="steps">
      {steps.map((s, i) => (
        <li key={i} className="step">
          <span className="step-n">{i + 1}</span>
          <div><div className="step-title">{s.title}</div>{s.detail && <div className="step-detail">{s.detail}</div>}</div>
        </li>
      ))}
    </ol>
  );
}

export function BulletList({ items = [], marker }: { items?: (string | { text: string })[]; marker?: string }) {
  const custom = marker && marker !== 'disc' && marker !== 'bullet';
  return (
    <ul className={cx('bullets', custom && 'bullets-custom')} style={custom ? { ['--marker' as any]: JSON.stringify(marker) } : undefined}>
      {items.map((it, i) => <li key={i}>{val(it)}</li>)}
    </ul>
  );
}

export function NumberedList({ items = [] }: { items?: (string | { text: string })[] }) {
  return <ol className="numbered">{items.map((it, i) => <li key={i}>{val(it)}</li>)}</ol>;
}

export function TableOfContents({ items = [] }: { items?: { id?: string; label: string }[] }) {
  return (
    <nav className="toc" aria-label="Contents">
      <div className="toc-title">Contents</div>
      <ol>{items.map((it, i) => <li key={i}>{it.id ? <a href={`#${it.id}`}>{it.label}</a> : it.label}</li>)}</ol>
    </nav>
  );
}

export function LinkCards({ links = [], numbered }: { links?: { href: string; title: string; site?: string; date?: string }[]; numbered?: boolean }) {
  return (
    <div className="linkcards">
      {links.map((l, i) => (
        <a key={i} className="linkcard" href={l.href}>
          {numbered && <span className="lc-n">{i + 1}</span>}
          <span className="lc-body">
            <span className="lc-title">{l.title}</span>
            <span className="lc-site">{l.site || host(l.href)}{l.date ? ` · ${l.date}` : ''}</span>
          </span>
        </a>
      ))}
    </div>
  );
}

export function Metrics({ metrics = [] }: { metrics?: { label: string; value: string; detail?: string; tone?: Tone }[] }) {
  return (
    <div className="metrics">
      {metrics.map((m, i) => (
        <div key={i} className={cx('metric', toneClass(m.tone))}>
          <div className="metric-label">{m.label}</div>
          <div className="metric-value">{val(m.value)}</div>
          {m.detail && <div className="metric-detail">{m.detail}</div>}
        </div>
      ))}
    </div>
  );
}

export function Bars({ bars = [], emphasis }: { bars?: { label: string; value: number; display?: string; meta?: string }[]; emphasis?: number }) {
  const max = Math.max(1, ...bars.map(b => b.value || 0));
  return (
    <div className="bars">
      {bars.map((b, i) => (
        <div key={i} className={cx('bar', i === emphasis && 'bar-em')}>
          <div className="bar-label">{b.label}{b.meta && <span className="meta"> · {b.meta}</span>}</div>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(1.5, (100 * (b.value || 0)) / max)}%` }} /></div>
          <div className="bar-value">{b.display ?? String(b.value)}</div>
        </div>
      ))}
    </div>
  );
}

const PIE_COLORS = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)'];

export function Pie({ label, parts = [] }: { label?: string; parts?: { label: string; value: number; display?: string }[] }) {
  const total = parts.reduce((s, p) => s + (p.value || 0), 0) || 1;
  let acc = 0;
  const R = 15.915; // circumference ≈ 100 so dash lengths are percentages
  return (
    <figure className="pie">
      {label && <figcaption>{label}</figcaption>}
      <div className="pie-row">
        <svg viewBox="0 0 42 42" className="pie-svg" role="img" aria-label={label}>
          <circle cx="21" cy="21" r={R} fill="none" stroke="var(--track)" strokeWidth="7" />
          {parts.map((p, i) => {
            const pct = (100 * (p.value || 0)) / total;
            const el = <circle key={i} cx="21" cy="21" r={R} fill="none" stroke={PIE_COLORS[i % PIE_COLORS.length]}
              strokeWidth="7" strokeDasharray={`${pct} ${100 - pct}`} strokeDashoffset={25 - acc} />;
            acc += pct;
            return el;
          })}
        </svg>
        <ul className="legend">
          {parts.map((p, i) => (
            <li key={i}><span className="swatch" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
              <span>{p.label}</span><span className="legend-v">{p.display ?? String(p.value)}</span></li>
          ))}
        </ul>
      </div>
    </figure>
  );
}

export function ProsCons({ prosHeading = 'Pros', consHeading = 'Cons', pros = [], cons = [] }:
  { prosHeading?: string; consHeading?: string; pros?: { text: string }[]; cons?: { text: string }[] }) {
  return (
    <div className="proscons">
      <div className="pc pc-pros"><h3>{prosHeading}</h3><ul>{pros.map((p, i) => <li key={i}>{val(p)}</li>)}</ul></div>
      <div className="pc pc-cons"><h3>{consHeading}</h3><ul>{cons.map((p, i) => <li key={i}>{val(p)}</li>)}</ul></div>
    </div>
  );
}

// Layered flow diagram: nodes placed by breadth-first distance from the sources, edges drawn as SVG curves.
// Two drawings of the same graph, switched by CSS (works without JS): the wide one for larger screens, and a
// phone one that always runs top to bottom with boxes sized to the widest row, drawn at (about) natural size so
// text stays readable. A phone row of up to 3 boxes fits a 390 px screen; wider rows scroll inside the diagram.
type DNode = { id: string; label: string; detail?: string; kind?: string };
type DEdge = { from: string; to: string; label?: string };

function diagramLayers(nodes: DNode[], edges: DEdge[]) {
  // Rows by breadth-first distance from the starting nodes, so loops (results flowing back to the start)
  // don't stretch the layout or leave empty rows.
  const ids = new Set(nodes.map(n => n.id));
  const valid = edges.filter(e => ids.has(e.from) && ids.has(e.to) && e.from !== e.to);
  const hasIn = new Set(valid.map(e => e.to));
  const layer: Record<string, number> = {};
  const queue = nodes.filter(n => !hasIn.has(n.id)).map(n => n.id);
  if (!queue.length && nodes.length) queue.push(nodes[0].id);
  queue.forEach(id => (layer[id] = 0));
  for (let i = 0; i < queue.length; i++)
    for (const e of valid) if (e.from === queue[i] && !(e.to in layer)) { layer[e.to] = layer[queue[i]] + 1; queue.push(e.to); }
  const deepest = Math.max(0, ...Object.values(layer));
  nodes.forEach(n => { if (!(n.id in layer)) layer[n.id] = deepest + 1; });
  const rows: string[][] = [];
  nodes.forEach(n => (rows[layer[n.id]] ??= []).push(n.id));
  return rows.filter(Boolean);
}

// Phone geometry by the widest row: [box width, box height]. Rows wider than 3 use the 3-box size and scroll.
const NARROW: Record<number, [number, number]> = { 1: [280, 72], 2: [140, 84], 3: [92, 100] };

function DiagramSvg({ nodes, edges, layers, down, narrow }:
  { nodes: DNode[]; edges: DEdge[]; layers: string[][]; down: boolean; narrow: boolean }) {
  const marker = 'arrow-' + useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const span = Math.max(...layers.map(l => l.length), 1);
  const [W, H] = narrow ? NARROW[Math.min(span, 3)] : [168, 64];
  const GX = narrow ? 10 : down ? 24 : 64, GY = narrow ? 44 : down ? 56 : 20;
  const pos: Record<string, { x: number; y: number }> = {};
  layers.forEach((row, li) => row.forEach((id, k) => {
    const offset = ((span - row.length) * ((down ? W + GX : H + GY))) / 2;
    pos[id] = down ? { x: offset + k * (W + GX), y: li * (H + GY) } : { x: li * (W + GX), y: offset + k * (H + GY) };
  }));
  const inner = { w: down ? span * (W + GX) - GX : layers.length * (W + GX) - GX,
                  h: down ? layers.length * (H + GY) - GY : span * (H + GY) - GY };
  // An edge back to an earlier (or the same) layer goes round the outside in its own lane: right of a top-down
  // drawing, below a left-to-right one. Straight, it would cut through the boxes in between.
  const back = (e: DEdge) => (down ? pos[e.to].y <= pos[e.from].y : pos[e.to].x <= pos[e.from].x);
  const hasBack = edges.some(e => pos[e.from] && pos[e.to] && back(e));
  const LANE = 30;
  const width = inner.w + (down && hasBack ? LANE : 0), height = inner.h + (!down && hasBack ? LANE : 0);
  const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  // Wide: at least its natural width up to 720 px (the box scrolls). Phone: natural size, shrinking a little to
  // fit up to 3 boxes a row, never enlarged; wider rows keep natural size and scroll.
  const style = narrow ? { width: width + 8, maxWidth: span <= 3 ? '100%' : 'none' } : { minWidth: Math.min(width + 8, 720) };
  return (
    <svg viewBox={`-4 -4 ${width + 8} ${height + 8}`} className={cx('diagram-svg', narrow ? 'diagram-narrow' : 'diagram-wide')}
      style={style} role="img" aria-hidden={narrow || undefined}>
      <defs>
        <marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)" />
        </marker>
      </defs>
      {edges.filter(e => pos[e.from] && pos[e.to]).map((e, i) => {
        const a = pos[e.from], b = pos[e.to];
        if (back(e)) {
          const r = 8;
          const d = down
            ? (() => { const L = inner.w + LANE / 2, sy = a.y + H / 2, ty = b.y + H / 2;
                return `M${a.x + W},${sy} H${L - r} Q${L},${sy} ${L},${sy - r} V${ty + r} Q${L},${ty} ${L - r},${ty} H${b.x + W + 2}`; })()
            : (() => { const L = inner.h + LANE / 2, sx = a.x + W / 2, tx = b.x + W / 2;
                return `M${sx},${a.y + H} V${L - r} Q${sx},${L} ${sx - r},${L} H${tx + r} Q${tx},${L} ${tx},${L - r} V${b.y + H + 2}`; })();
          return <path key={i} d={d} fill="none" stroke="var(--muted)" strokeWidth="1.4" markerEnd={`url(#${marker})`} />;
        }
        const [x1, y1, x2, y2] = down ? [a.x + W / 2, a.y + H, b.x + W / 2, b.y] : [a.x + W, a.y + H / 2, b.x, b.y + H / 2];
        const d = down ? `M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2 - 2}`
                       : `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2 - 2},${y2}`;
        return <path key={i} d={d} fill="none" stroke="var(--muted)" strokeWidth="1.4" markerEnd={`url(#${marker})`} />;
      })}
      {nodes.map(n => {
        const p = pos[n.id];
        return (
          <foreignObject key={n.id} x={p.x} y={p.y} width={W} height={H}>
            <div className={cx('node', `node-${byId[n.id].kind || 'box'}`)} title={n.detail}>
              <div className="node-label">{n.label}</div>
              {n.detail && <div className="node-detail">{n.detail}</div>}
            </div>
          </foreignObject>
        );
      })}
      {/* Labels last, over everything, each on a halo in the paper colour so its line never runs through it. */}
      {edges.filter(e => e.label && pos[e.from] && pos[e.to]).map((e, i) => {
        const a = pos[e.from], b = pos[e.to];
        if (back(e)) {  // on its lane, halfway along
          const [lx, ly] = down ? [inner.w + LANE / 2, (a.y + b.y + H) / 2] : [(a.x + b.x + W) / 2, inner.h + LANE / 2];
          return <text key={i} x={lx} y={ly} dy="0.35em" className="edge-label" textAnchor="middle"
            transform={down ? `rotate(-90 ${lx} ${ly})` : undefined}>{e.label}</text>;
        }
        const [x1, y1, x2, y2] = down ? [a.x + W / 2, a.y + H, b.x + W / 2, b.y] : [a.x + W, a.y + H / 2, b.x, b.y + H / 2];
        // Where edges fan out from one box, label near the far end (they are apart there); where they fan in,
        // near the start; otherwise in the middle. Point on the same cubic curve as the line.
        const fanOut = edges.filter(o => o.from === e.from && pos[o.to]).length > 1;
        const fanIn = edges.filter(o => o.to === e.to && pos[o.from]).length > 1;
        const t = fanOut && !fanIn ? 0.7 : fanIn && !fanOut ? 0.3 : 0.5;
        const ease = 3 * t * t - 2 * t * t * t;  // cubic with both control points level with their ends
        const [lx, ly] = down ? [x1 + (x2 - x1) * ease, y1 + (y2 - y1) * t] : [x1 + (x2 - x1) * t, y1 + (y2 - y1) * ease];
        // On the phone drawing, fanned labels sit one box apart: shorten one that would run into its neighbour
        // (the wide drawing and the diagram's details keep it whole).
        const room = narrow && (fanOut || fanIn) ? Math.max(8, Math.floor((W + GX) / 6.4)) : Infinity;
        const label = e.label!.length > room ? e.label!.slice(0, room - 1).trimEnd() + '…' : e.label;
        return <text key={i} x={lx} y={ly} dy="0.35em" className="edge-label" textAnchor="middle">
          {label !== e.label && <title>{e.label}</title>}{label}</text>;
      })}
    </svg>
  );
}

export function Diagram({ direction, nodes = [], edges = [] }: { direction?: string; nodes?: DNode[]; edges?: DEdge[] }) {
  const down = /down|vertical|tb|column/i.test(direction || '');
  const layers = diagramLayers(nodes, edges);
  return (
    <figure className="diagram">
      <DiagramSvg nodes={nodes} edges={edges} layers={layers} down={down} narrow={false} />
      <DiagramSvg nodes={nodes} edges={edges} layers={layers} down narrow />
      {nodes.some(n => n.detail) && (
        <details className="diagram-key"><summary>Diagram details</summary>
          <dl>{nodes.map(n => <div key={n.id}><dt>{n.label}</dt><dd>{n.detail}</dd></div>)}</dl>
        </details>
      )}
    </figure>
  );
}

// Sequence diagram: actors as columns with lifelines, messages as arrows top to bottom.
export function Sequence({ actors = [], messages = [] }:
  { actors?: { id: string; label: string }[]; messages?: { from: string; to: string; label?: string }[] }) {
  const COL = 150, TOP = 44, STEP = 46;
  const x: Record<string, number> = {};
  actors.forEach((a, i) => (x[a.id] = i * COL + COL / 2));
  const width = Math.max(actors.length, 1) * COL, height = TOP + messages.length * STEP + 24;
  return (
    <figure className="diagram sequence">
      <svg viewBox={`0 0 ${width} ${height}`} className="diagram-svg" style={{ minWidth: Math.min(width, 640) }} role="img">
        <defs>
          <marker id="seq-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--text)" />
          </marker>
        </defs>
        {actors.map(a => (
          <g key={a.id}>
            <line x1={x[a.id]} y1={TOP - 6} x2={x[a.id]} y2={height - 6} stroke="var(--line)" strokeDasharray="4 4" />
            <foreignObject x={x[a.id] - COL / 2 + 8} y={2} width={COL - 16} height={TOP - 10}>
              <div className="node node-box seq-actor"><div className="node-label">{a.label}</div></div>
            </foreignObject>
          </g>
        ))}
        {messages.filter(m => m.from in x && m.to in x).map((m, i) => {
          const y = TOP + 18 + i * STEP, x1 = x[m.from], x2 = x[m.to];
          const self = x1 === x2;
          return (
            <g key={i}>
              {self
                ? <path d={`M${x1},${y} h28 v14 h-26`} fill="none" stroke="var(--text)" strokeWidth="1.3" markerEnd="url(#seq-arrow)" />
                : <line x1={x1} y1={y} x2={x2 + (x2 > x1 ? -3 : 3)} y2={y} stroke="var(--text)" strokeWidth="1.3" markerEnd="url(#seq-arrow)" />}
              {m.label && <text x={self ? x1 + 34 : (x1 + x2) / 2} y={y - 6} className="seq-label" textAnchor={self ? 'start' : 'middle'}>{m.label}</text>}
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

// A2UI-compatible, local-only surfaces remain inside the Hermes Page document.
export { A2UISurface } from './a2ui';
export { JsonSurface } from './json-surface';
