"""Work status for Hermes Pages: is a Page being worked on right now, by whom, since when.

State lives in src/<slug>/work.json (not in git: it is live runtime state, not content). A Page without
that file is finished. Changing status never rebuilds the Page: the status block in build/<slug>.html is
patched in place and build/live/<slug>.json (the "pulse" open Pages poll) is rewritten.

States set by code: working, needs_input, done, failed. "stalled" is derived: a "working" status whose
lease ran out (no status change or save within lease_minutes) reads as stalled, never as live.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATES = ('working', 'needs_input', 'done', 'failed')
SECTION_STATES = ('pending', 'working', 'done', 'failed')
DEFAULT_LEASE_MIN = 15
MAX_LEASE_MIN = 24 * 60
START, END = '<!--hermes-page-work:start-->', '<!--hermes-page-work:end-->'
STATUS_COMMENT = re.compile(r'\A/\* hermes-page-status:[^\n]*\*/\n')
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')
except Exception:  # pragma: no cover
    ET = dt.timezone.utc


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def parse(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None


def _clip(s, n):
    s = ' '.join(str(s or '').split())
    return s[:n - 1] + '…' if len(s) > n else s


def normalize_sections(items):
    """[str | 'label=state' | {label, state}] -> [{label, state}]. Max 20 parts."""
    if items is None:
        return None
    if not isinstance(items, list) or len(items) > 20:
        raise ValueError('sections must be a list of at most 20 parts')
    out = []
    for it in items:
        if isinstance(it, str):
            label, state = it, 'pending'
            head, sep, tail = it.rpartition('=')
            if sep and tail.strip().lower().replace('-', '_') in SECTION_STATES:
                label, state = head, tail.strip().lower().replace('-', '_')
        elif isinstance(it, dict):
            label, state = it.get('label') or it.get('title') or it.get('name') or '', (it.get('state') or it.get('status') or 'pending')
            state = 'done' if it.get('done') is True else str(state).strip().lower().replace('-', '_')
        else:
            raise ValueError('each section is a label string or {label, state}')
        label = _clip(label, 80)
        if not label:
            raise ValueError('section labels cannot be empty')
        if state not in SECTION_STATES:
            raise ValueError('section state must be one of ' + ', '.join(SECTION_STATES))
        out.append({'label': label, 'state': state})
    return out


def work_file(root, slug):
    return Path(root) / 'src' / slug / 'work.json'


def load(root, slug):
    f = work_file(root, slug)
    try:
        rec = json.loads(f.read_text())
        return rec if isinstance(rec, dict) and rec.get('state') in STATES else None
    except (OSError, ValueError):
        return None


def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.%d.tmp' % os.getpid())
    tmp.write_text(text)
    os.replace(tmp, path)


def new_record(prev, state, note=None, by=None, sections=None, lease_minutes=None, now=None):
    """Next status record. Omitted fields keep their value; a state change clears an omitted note."""
    if state not in STATES:
        raise ValueError('status must be one of ' + ', '.join(STATES))
    now = now or now_utc()
    prev = prev or {}
    same = prev.get('state') == state
    rec = {'state': state}
    rec['by'] = _clip(by, 60) if by is not None else prev.get('by', '')
    rec['note'] = _clip(note, 200) if note is not None else (prev.get('note', '') if same else '')
    sec = normalize_sections(sections) if sections is not None else prev.get('sections', [])
    rec['sections'] = sec or []
    lease = prev.get('lease_minutes', DEFAULT_LEASE_MIN) if lease_minutes in (None, 0) else lease_minutes
    lease = int(lease)
    if not 1 <= lease <= MAX_LEASE_MIN:
        raise ValueError('lease_minutes must be between 1 and %d' % MAX_LEASE_MIN)
    rec['lease_minutes'] = lease
    rec['since'] = prev.get('since') if same and prev.get('since') else iso(now)
    rec['started'] = prev.get('started') or iso(now)  # first time this Page was worked on in this run
    if state == 'working' and prev.get('state') in ('done', 'failed', None):
        rec['started'] = iso(now)
    rec['updated'] = iso(now)
    if state == 'working':
        rec['stale_after'] = iso(now + dt.timedelta(minutes=lease))
    return rec


def save(root, slug, rec):
    _atomic_write(work_file(root, slug), json.dumps(rec, indent=2) + '\n')


def derived_state(rec, now=None):
    if not rec:
        return 'done'
    if rec['state'] == 'working':
        stale = parse(rec.get('stale_after'))
        if stale and (now or now_utc()) > stale:
            return 'stalled'
    return rec['state']


def public(rec, now=None):
    """Status as agents see it. A Page with no work record is finished: {"state": "done"}."""
    if not rec:
        return {'state': 'done'}
    out = {'state': derived_state(rec, now)}
    for k in ('by', 'note', 'since', 'updated', 'stale_after', 'sections'):
        if rec.get(k):
            out[k] = rec[k]
    if rec.get('sections'):
        out['progress'] = '%d of %d parts done' % (sum(s['state'] == 'done' for s in rec['sections']), len(rec['sections']))
    return out


def rev(root, slug):
    """Content version of a Page's source: changes when page.tsx or its title changes."""
    d = Path(root) / 'src' / slug
    if not d.is_dir():
        d = Path(root) / 'samples' / slug
    h = hashlib.sha1()
    try:
        h.update((d / 'page.tsx').read_bytes())
        h.update(b'\0' + json.loads((d / 'meta.json').read_text()).get('title', '').encode())
    except (OSError, ValueError):
        pass
    return h.hexdigest()[:12]


# ---------- rendering (Python renders the static block; the live script re-renders the same markup) ----------

LABEL = {'working': 'Being worked on', 'stalled': 'Stalled', 'needs_input': 'Needs your input',
         'failed': "Didn't finish", 'done': 'Done'}
MARK = {'done': '✓', 'working': '•', 'failed': '✕', 'pending': '○'}

STYLE = """.hp-work{position:sticky;top:0;z-index:30;padding:12px 16px 0;font:13px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif}
.hp-work[hidden]{display:none}
.hp-work-in{max-width:800px;margin:0 auto;background:var(--surface,#fdfcfb);border:1px solid var(--line,#e9e3dd);border-radius:14px;padding:10px 14px;box-shadow:0 6px 20px rgba(50,35,25,.07);color:var(--text,#302a28)}
.hp-work-top{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}
.hp-work-label{font-weight:600;color:var(--heading,#493832);display:inline-flex;align-items:center;gap:7px}
.hp-work-dot{width:8px;height:8px;border-radius:50%;background:var(--accent,#52796c);flex:none;align-self:center}
.hp-work-working .hp-work-dot{animation:hp-work-pulse 1.6s ease-in-out infinite}
.hp-work-stalled .hp-work-dot,.hp-work-needs_input .hp-work-dot{background:var(--warning,#96754c)}
.hp-work-failed .hp-work-dot{background:var(--danger,#a06d63)}
.hp-work-stalled .hp-work-in,.hp-work-needs_input .hp-work-in{background:var(--warning-bg,#f6f1e8)}
.hp-work-failed .hp-work-in{background:var(--danger-bg,#f7eeeb)}
.hp-work-meta{color:var(--muted,#887a73);font-size:12px}
.hp-work-note{margin:2px 0 0;font-size:13px}
.hp-work-parts{list-style:none;margin:6px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted,#887a73)}
.hp-work-parts .p-done{color:var(--success,#52796c)}.hp-work-parts .p-working{color:var(--text,#302a28);font-weight:500}.hp-work-parts .p-failed{color:var(--danger,#a06d63)}
.hp-work-done{position:static;padding-top:14px}
.hp-work-done .hp-work-in{background:transparent;border:0;box-shadow:none;padding:0 8px;text-align:center}
.hp-work-done .hp-work-top{justify-content:center}.hp-work-done .hp-work-label{font-weight:500;color:var(--success,#52796c)}
.hp-work-done .hp-work-dot,.hp-work-done .hp-work-parts{display:none}
@keyframes hp-work-pulse{0%,100%{opacity:1}50%{opacity:.3}}
@media (prefers-reduced-motion:reduce){.hp-work-working .hp-work-dot{animation:none}}
@media print{.hp-work{position:static}}
.hp-who i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--a);margin-right:5px;vertical-align:1px}
.hp-a0{--a:#52796c}.hp-a1{--a:#b4553a}.hp-a2{--a:#3f63ad}.hp-a3{--a:#93488a}.hp-a4{--a:#a77812}
#hp-marks{position:absolute;left:0;top:0;width:0;height:0;pointer-events:none;z-index:25}
.hp-mark{transition:opacity 1.6s ease}.hp-mark.hp-fade{opacity:0}.hp-in{animation:hp-in .45s ease-out}
@keyframes hp-in{from{opacity:0}}
.hp-rect{position:absolute;border-radius:4px;background:var(--a);opacity:.22;mix-blend-mode:multiply}
.hp-rect.hp-blk{border-radius:10px;opacity:.12}
.hp-caret{position:absolute;width:2px;border-radius:1px;background:var(--a);z-index:26;pointer-events:none}
.hp-caret.hp-move{transition:left .25s ease,top .25s ease}
.hp-caret.hp-open .hp-flag{opacity:1;transform:none}.hp-caret.hp-flip .hp-flag{left:auto;right:-1px;border-radius:7px 7px 2px 7px;transform-origin:100% 100%}.hp-caret::before{content:'';position:absolute;left:-2px;top:-5px;width:6px;height:6px;border-radius:50%;background:var(--a)}.hp-flag{opacity:0;transform:translateY(5px) scale(.7);transform-origin:0 100%;transition:opacity .35s ease,transform .35s ease;position:absolute;left:-1px;bottom:100%;margin-bottom:4px;background:var(--a);color:#fff;font:600 11px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;padding:1px 7px;border-radius:7px 7px 7px 2px;white-space:nowrap;box-shadow:0 2px 6px rgba(40,28,20,.14)}
@media (prefers-color-scheme:dark){.hp-a0{--a:#a5c4b7}.hp-a1{--a:#ec9f84}.hp-a2{--a:#9fb6ee}.hp-a3{--a:#d9a1cf}.hp-a4{--a:#e3c06a}
.hp-rect{mix-blend-mode:screen;opacity:.26}.hp-rect.hp-blk{opacity:.14}.hp-flag{color:#1e1917}}
@media (prefers-reduced-motion:reduce){.hp-mark,.hp-caret.hp-move,.hp-flag{transition:none}.hp-in{animation:none}}
@media print{#hp-marks{display:none}}"""


def _clock(s):
    t = parse(s)
    if not t:
        return ''
    t = t.astimezone(ET)
    today = dt.datetime.now(ET).date()
    hm = t.strftime('%I:%M %p').lstrip('0')
    return hm if t.date() == today else t.strftime('%b ') + str(t.day) + ', ' + hm


def inner_html(rec):
    """Static markup of the status card (no relative times: those need a live clock)."""
    if not rec:
        return ''
    st = rec['state']
    e = html.escape
    meta = [e(rec['by'])] if rec.get('by') else []
    if st == 'working':
        meta += ['started ' + _clock(rec.get('since')), 'updated ' + _clock(rec.get('updated'))]
    elif st == 'done':
        meta.append('finished ' + _clock(rec.get('updated')))
    else:
        meta.append(_clock(rec.get('updated')))
    parts = rec.get('sections') or []
    out = ['<div class="hp-work-in"><div class="hp-work-top"><span class="hp-work-label"><span class="hp-work-dot"></span>',
           e(LABEL[st]), '</span>']
    out.append('<span class="hp-work-meta">' + ' · '.join(m for m in meta if m) + '</span></div>')
    if rec.get('note'):
        out.append('<p class="hp-work-note">' + e(rec['note']) + '</p>')
    if parts:
        out.append('<ul class="hp-work-parts">' + ''.join(
            '<li class="p-%s">%s %s</li>' % (p['state'], MARK[p['state']], e(p['label'])) for p in parts) + '</ul>')
    out.append('</div>')
    return ''.join(out)


LIVE_JS = r"""(function(){
var box=document.getElementById('hp-work');if(!box||window.__hpLive)return;window.__hpLive=1;
var proto=location.protocol;if(proto!=='https:'&&proto!=='http:')return;
var slug=box.getAttribute('data-slug'),rev=box.getAttribute('data-rev'),tried='',work=null,edit=null,timer=0,fails=0,last=null,first=true,busy=false;
try{work=JSON.parse(box.getAttribute('data-work')||'null')}catch(e){}
var p=location.pathname,m=p.match(/\/v1\/pages\/([a-z0-9-]+)\/content$/),pulse,page,prev;
if(m){pulse=p.replace(/content$/,'live');page=p;prev=p.replace(/content$/,'previous')}
else{var b=p.replace(/[^\/]*$/,'');pulse=b+'live/'+slug+'.json';page=b+slug+'.html';prev=b+'live/'+slug+'.prev.html'}
var LABEL={working:'Being worked on',stalled:'Stalled',needs_input:'Needs your input',failed:"Didn't finish",done:'Done'};
var MARK={done:'✓',working:'•',failed:'✕',pending:'○'};
var reduce=false;try{reduce=matchMedia('(prefers-reduced-motion: reduce)').matches}catch(e){}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function ago(s){var t=Date.parse(s);if(!t)return'';var d=Math.max(0,(Date.now()-t)/1000);
 if(d<45)return'just now';if(d<3600)return Math.round(d/60)+' min ago';if(d<86400)return Math.round(d/3600)+' h ago';
 return new Date(t).toLocaleDateString(undefined,{month:'short',day:'numeric'})}
function clock(s){var t=Date.parse(s);return t?new Date(t).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}):''}
function state(w){if(!w)return'';if(w.state==='working'&&w.stale_after&&Date.now()>Date.parse(w.stale_after))return'stalled';return w.state}
function hue(n){n=String(n||'');var h=0;for(var i=0;i<n.length;i++)h=(h*31+n.charCodeAt(i))>>>0;return h%5}
function who(n){return'<span class="hp-who hp-a'+hue(n)+'"><i></i>'+esc(n)+'</span>'}
function render(){var st=state(work);if(!st){if(!box.hidden){box.hidden=true;box.innerHTML='';box.className='hp-work';last=''}return}
 var meta=[];if(work.by)meta.push(who(work.by));
 if(st==='working')meta.push('started '+clock(work.since),'updated '+ago(work.updated));
 else if(st==='stalled')meta.push('no update since '+clock(work.updated)+' ('+ago(work.updated)+')');
 else if(st==='done')meta.push('finished '+clock(work.updated));else meta.push(ago(work.updated));
 var parts=work.sections||[],i;
 var h='<div class="hp-work-in"><div class="hp-work-top"><span class="hp-work-label"><span class="hp-work-dot"></span>'+LABEL[st]+'</span><span class="hp-work-meta">'+meta.join(' · ')+'</span></div>';
 if(work.note)h+='<p class="hp-work-note">'+esc(work.note)+'</p>';
 if(parts.length){h+='<ul class="hp-work-parts">';for(i=0;i<parts.length;i++)h+='<li class="p-'+esc(parts[i].state)+'">'+(MARK[parts[i].state]||'')+' '+esc(parts[i].label)+'</li>';h+='</ul>'}
 h+='</div>';var cls='hp-work hp-work-'+st;
 if(box.className!==cls)box.className=cls;if(box.hidden)box.hidden=false;if(last!==h){box.innerHTML=h;last=h}
 caretShow()}

/* ---- presence: what changed, and who is changing it (overlay only; React's DOM is never touched) ---- */
var SEL='h1,h2,h3,h4,h5,p,li,tr,dt,dd,blockquote,figcaption,pre,.metric,.bar,.node,.lc-body,.callout-lead,.legend li';
function textOf(el){var w=document.createTreeWalker(el,4),n,out=[];while((n=w.nextNode()))if(/\S/.test(n.nodeValue))out.push(n.nodeValue);return out.join(' ').replace(/\s+/g,' ').trim()}
function blocks(root){var out=[];if(!root)return out;var all=root.querySelectorAll(SEL);
 for(var i=0;i<all.length;i++){var el=all[i];if(el.querySelector(SEL))continue;var t=textOf(el);if(t)out.push({el:el,t:t})}return out}
function lcs(a,b,eq){var n=a.length,mm=b.length;if(!n||!mm||n*mm>1500000)return null;var L=new Uint16Array((n+1)*(mm+1)),W=mm+1,i,j;
 for(i=n-1;i>=0;i--)for(j=mm-1;j>=0;j--)L[i*W+j]=eq(a[i],b[j])?L[(i+1)*W+j+1]+1:Math.max(L[(i+1)*W+j],L[i*W+j+1]);
 var pairs=[];i=0;j=0;while(i<n&&j<mm){if(eq(a[i],b[j])){pairs.push([i,j]);i++;j++}else if(L[(i+1)*W+j]>=L[i*W+j+1])i++;else j++}return pairs}
function rangeAt(el,s,e){var w=document.createTreeWalker(el,4),n,pos=0,r=document.createRange(),started=false;
 while((n=w.nextNode())){if(!/\S/.test(n.nodeValue))continue;var v=n.nodeValue,len=v.length;
  if(!started&&s<pos+len){r.setStart(n,Math.max(0,s-pos));started=true}
  if(started&&e<=pos+len){r.setEnd(n,Math.max(0,e-pos));return r}pos+=len+1}
 return started?r:null}
function words(el){/* tokens of the block's text nodes with offsets in the joined text */
 var w=document.createTreeWalker(el,4),n,pos=0,out=[],re=/\S+/g,mt;
 while((n=w.nextNode())){if(!/\S/.test(n.nodeValue))continue;re.lastIndex=0;while((mt=re.exec(n.nodeValue)))out.push({w:mt[0],s:pos+mt.index,e:pos+mt.index+mt[0].length});pos+=n.nodeValue.length+1}return out}
function wordMarks(oldT,nb,out){var nw=words(nb.el),ow=oldT.split(' ');
 var pr=nw.length<=400&&ow.length<=400?lcs(ow,nw,function(x,y){return x===y.w}):null;
 if(!pr){out.push({el:nb.el});return}var keep={},i;for(i=0;i<pr.length;i++)keep[pr[i][1]]=1;
 var changed=0,run=null;for(i=0;i<nw.length;i++)if(!keep[i])changed++;
 if(!changed)return;if(changed>0.6*nw.length){out.push({el:nb.el});return}
 for(i=0;i<=nw.length;i++){if(i<nw.length&&!keep[i]){if(!run)run={s:nw[i].s,e:nw[i].e};else run.e=nw[i].e}
  else if(run){var r=rangeAt(nb.el,run.s,run.e);if(r)out.push({range:r});else out.push({el:nb.el});run=null}}}
function diff(oldT,nb){var out=[],pr=lcs(oldT,nb,function(x,y){return x===y.t}),i,j;
 if(!pr){var cnt={};for(i=0;i<oldT.length;i++)cnt[oldT[i]]=(cnt[oldT[i]]||0)+1;
  for(j=0;j<nb.length;j++){if(cnt[nb[j].t])cnt[nb[j].t]--;else out.push({el:nb[j].el})}return out}
 pr.push([oldT.length,nb.length]);var oi=0,ni=0;
 for(var k=0;k<pr.length;k++){var og=oldT.slice(oi,pr[k][0]),ng=nb.slice(ni,pr[k][1]);
  for(i=0;i<ng.length;i++){if(i<og.length)wordMarks(og[i],ng[i],out);else out.push({el:ng[i].el})}
  oi=pr[k][0]+1;ni=pr[k][1]+1}return out}
var layer=null,marks=[],caret=null,caretAt=null,author='',io=null;
function ensureLayer(){if(layer&&layer.parentNode)return;layer=document.createElement('div');layer.id='hp-marks';layer.setAttribute('aria-hidden','true');document.body.appendChild(layer)}
function rectsOf(mk){var rs=[],i,b,X=window.scrollX,Y=window.scrollY;if(mk.range){try{var cr=mk.range.getClientRects();for(i=0;i<cr.length;i++)if(cr[i].width>1)rs.push({l:cr[i].left-2+X,t:cr[i].top-1+Y,w:cr[i].width+4,h:cr[i].height+2})}catch(e){}}
 else if(mk.el&&mk.el.isConnected){b=mk.el.getBoundingClientRect();if(b.width>1&&b.height>1)rs.push({l:b.left-5+X,t:b.top-3+Y,w:b.width+10,h:b.height+6,blk:1})}return rs}
function layout(){if(!layer)return;
 for(var i=0;i<marks.length;i++){var mk=marks[i],rs=rectsOf(mk);mk.rs=rs;
  while(mk.g.childNodes.length>rs.length)mk.g.removeChild(mk.g.lastChild);
  for(var j=0;j<rs.length;j++){var d=mk.g.childNodes[j];if(!d){d=document.createElement('div');mk.g.appendChild(d);if(io)io.observe(d)}
   d.className='hp-rect'+(rs[j].blk?' hp-blk':'');d.style.cssText='left:'+rs[j].l+'px;top:'+rs[j].t+'px;width:'+rs[j].w+'px;height:'+rs[j].h+'px'}}
 caretPlace()}
var lay=0;function relayout(){if(lay)return;lay=requestAnimationFrame(function(){lay=0;layout()})}
function clearMarks(){for(var i=0;i<marks.length;i++)if(marks[i].g.parentNode)marks[i].g.parentNode.removeChild(marks[i].g);marks=[]}
function settle(mk){if(mk.done)return;mk.done=1;setTimeout(function(){mk.g.classList.add('hp-fade');
 setTimeout(function(){if(mk.g.parentNode)mk.g.parentNode.removeChild(mk.g);marks=marks.filter(function(x){return x!==mk})},reduce?0:1700)},reduce?4500:2600)}
function show(list,name){clearMarks();if(!list.length)return;ensureLayer();author=name||'';var cls='hp-mark hp-a'+hue(author);
 if(!io&&window.IntersectionObserver)io=new IntersectionObserver(function(es){es.forEach(function(e){if(!e.isIntersecting)return;
  for(var i=0;i<marks.length;i++)if(marks[i].g===e.target.parentNode)settle(marks[i])})},{threshold:0.5});
 for(var i=0;i<list.length;i++){var g=document.createElement('div');g.className=cls+(reduce?'':' hp-in');layer.appendChild(g);list[i].g=g;marks.push(list[i])}
 layout();if(!io)marks.forEach(settle);
 var best=null;marks.forEach(function(mk){var r=mk.rs&&mk.rs[mk.rs.length-1];if(!r)return;var y=r.t,x=r.l+r.w;
  if(!best||y>best.y+2||(Math.abs(y-best.y)<=2&&x>best.x))best={mk:mk,y:y,x:x}});
 caretAt=best?best.mk:null;caretShow(true)}
function endRect(mk){/* the end of the last line of text the edit touched, in document coordinates */
 var r=mk.range;if(!r&&mk.el&&mk.el.isConnected){r=document.createRange();r.selectNodeContents(mk.el)}if(!r)return null;
 var cr;try{cr=r.getClientRects()}catch(e){return null}for(var i=cr.length-1;i>=0;i--)if(cr[i].width>0||cr[i].height>0)
  return{x:cr[i].right+window.scrollX,y:cr[i].top+window.scrollY,h:cr[i].height};return null}
function caretPlace(){if(!caret)return;var q=caretAt&&endRect(caretAt);
 if(!q||state(work)!=='working'){caret.style.display='none';return}
 caret.style.cssText='left:'+(q.x+1)+'px;top:'+q.y+'px;height:'+q.h+'px';
 var f=caret.firstChild;if(f){caret.classList.remove('hp-flip');if(q.x+f.offsetWidth+12>document.documentElement.clientWidth)caret.classList.add('hp-flip')}}
var flagOpen=false,flagTimer=0;
function caretShow(fresh){/* the name flag shows when an edit lands, then folds into the caret (as in Notes) */
 if(state(work)!=='working'||!caretAt||!author){if(caret)caret.style.display='none';return}ensureLayer();
 if(!caret){caret=document.createElement('div');caret.innerHTML='<span class="hp-flag"></span>';layer.appendChild(caret)}
 if(fresh){flagOpen=true;clearTimeout(flagTimer);flagTimer=setTimeout(function(){flagOpen=false;if(caret)caret.classList.remove('hp-open')},3200)}
 caret.className='hp-caret hp-a'+hue(author)+(reduce?'':' hp-move')+(flagOpen?' hp-open':'');
 if(caret.firstChild.textContent!==author)caret.firstChild.textContent=author;caretPlace()}
function remember(){if(document.hidden||!work)return;try{localStorage.setItem('hp-seen:'+slug,JSON.stringify({rev:rev,t:blocks(document.getElementById('root')).map(function(x){return x.t}),at:Date.now()}))}catch(e){}}
function seen(){try{return JSON.parse(localStorage.getItem('hp-seen:'+slug)||'null')}catch(e){return null}}
function editor(){return(edit&&edit.rev===rev&&edit.by)||(work&&work.by)||'Hermes'}
function showFresh(list,root){/* on open: a near-total rewrite is not worth painting, only who is where */
 var n=blocks(root).length;show(list,editor());if(list.length>Math.max(3,0.6*n))clearMarks()}
function sinceLastLook(){/* first pulse after opening: what changed since this reader last looked, as far as we can know */
 if(!work)return;var s=seen(),st=state(work),root=document.getElementById('root');
 if(s&&s.rev&&s.rev!==rev&&s.t){showFresh(diff(s.t,blocks(root)),root);remember();return}
 if(s&&s.rev===rev){remember();if(st==='working'&&edit&&edit.rev===rev)lastEditFrom(true);return}
 if(edit&&edit.rev===rev&&edit.prev_rev&&(st!=='done'||Date.now()-Date.parse(edit.at)<6e5))lastEditFrom(false);else remember()}
function lastEditFrom(caretOnly){fetch(prev,{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw r.status;return r.text()}).then(function(t){
 var d=new DOMParser().parseFromString(t,'text/html'),ob=blocks(d.getElementById('root')).map(function(x){return x.t}),list=diff(ob,blocks(document.getElementById('root')));
 if(caretOnly){show(list,editor());clearMarks()}else showFresh(list,document.getElementById('root'));remember()}).catch(function(){remember()})}
/* ---- content swap ---- */
function anchorOf(bs){var top=(box.hidden?0:box.getBoundingClientRect().bottom)+4;for(var i=0;i<bs.length;i++){var r=bs[i].el.getBoundingClientRect();if(r.bottom>top)return{i:i,t:bs[i].t,y:r.top,n:bs.length}}return null}
function reanchor(a,bs,y){if(!a){window.scrollTo(0,y);return}var best=-1,bd=1e9;for(var i=0;i<bs.length;i++)if(bs[i].t===a.t){var d=Math.abs(i/bs.length-a.i/a.n);if(d<bd){bd=d;best=i}}
 if(best<0){window.scrollTo(0,y);return}window.scrollBy(0,bs[best].el.getBoundingClientRect().top-a.y)}
function tabs(root){var gs=root.querySelectorAll('.segmented'),out=[];for(var i=0;i<gs.length;i++){var bs=gs[i].querySelectorAll('.seg'),k=-1;for(var j=0;j<bs.length;j++)if(bs[j].classList.contains('seg-on'))k=j;out.push(k)}return out}
function hydrated(el){for(var k in el)if(k.indexOf('__react')===0)return true;return false}
function swap(doc,name,done){var nb=doc.getElementById('hp-work'),nr=doc.getElementById('root'),old=document.getElementById('root');
 if(!nb||!nr||!old){done();return}var y=window.scrollY,code=null,ss=doc.querySelectorAll('body > script:not([id])');
 if(ss.length)code=ss[ss.length-1].textContent;
 var ob=blocks(old),oldT=ob.map(function(x){return x.t}),a=anchorOf(ob),tb=tabs(old);
 if(doc.title)document.title=doc.title;
 ['.hp-tag-bar','.hp-foot'].forEach(function(q){var x=document.querySelector(q),n=doc.querySelector(q);if(x&&n&&x.outerHTML!==n.outerHTML)x.outerHTML=n.outerHTML});
 clearMarks();var fresh=document.createElement('div');fresh.id='root';fresh.innerHTML=nr.innerHTML;old.parentNode.replaceChild(fresh,old);
 reanchor(a,blocks(fresh),y);rev=nb.getAttribute('data-rev');
 if(code){var s=document.createElement('script');s.textContent=code;document.body.appendChild(s);s.parentNode.removeChild(s)}
 var tries=0;(function wait(){var seg=fresh.querySelector('.seg');
  if(tries++<60&&!(hydrated(fresh)&&(!seg||hydrated(seg)))){requestAnimationFrame(wait);return}
  var gs=fresh.querySelectorAll('.segmented');for(var i=0;i<gs.length&&i<tb.length;i++){var bs=gs[i].querySelectorAll('.seg');if(tb[i]>=0&&bs[tb[i]]&&!bs[tb[i]].classList.contains('seg-on'))bs[tb[i]].click()}
  requestAnimationFrame(function(){var nbs=blocks(fresh);reanchor(a,nbs,y);if(work)show(diff(oldT,nbs),name);remember();done()})})()}
function next(){var st=state(work),ms=st==='working'?3000:st==='needs_input'?8000:st==='stalled'?15000:60000;
 ms=Math.min(120000,ms*Math.pow(2,Math.min(fails,5)));clearTimeout(timer);timer=setTimeout(poll,ms)}
function poll(){if(document.hidden||busy){next();return}busy=true;
 fetch(pulse+(pulse.indexOf('?')<0?'?':'&')+'t='+Date.now(),{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw r.status;return r.json()}).then(function(j){
  fails=0;work=j.work||null;edit=j.edit||null;render();
  if(j.rev&&j.rev!==rev&&j.rev!==tried){tried=j.rev;first=false;
   return fetch(page,{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw r.status;return r.text()}).then(function(t){
    var d=new DOMParser().parseFromString(t,'text/html'),nb=d.getElementById('hp-work'),nrev=nb&&nb.getAttribute('data-rev');
    if(nrev&&nrev!==rev)return new Promise(function(res){swap(d,(edit&&edit.rev===nrev&&edit.by)||(work&&work.by)||'Hermes',res)})})}
  if(first){first=false;sinceLastLook()}
 }).catch(function(){fails++}).then(function(){busy=false;next()})}
render();setInterval(function(){if(!document.hidden)render()},20000);
window.addEventListener('resize',relayout);if(window.ResizeObserver)new ResizeObserver(relayout).observe(document.body);
document.addEventListener('visibilitychange',function(){if(document.hidden)remember();else poll()});
window.addEventListener('pagehide',remember);
timer=setTimeout(poll,600)})();"""


def block(slug, rev_, rec):
    """Status card + live updater, placed in the shell outside React's root."""
    st = rec['state'] if rec else ''
    cls = 'hp-work hp-work-' + st if rec else 'hp-work'
    data = html.escape(json.dumps(rec, separators=(',', ':')) if rec else 'null', quote=True)
    return (START + '<style>' + STYLE + '</style>'
            + '<div id="hp-work" class="%s" role="status" aria-live="polite" data-slug="%s" data-rev="%s" data-work="%s"%s>'
            % (cls, html.escape(slug), html.escape(rev_), data, '' if rec else ' hidden')
            + inner_html(rec) + '</div><script id="hp-live">' + LIVE_JS + '</script>' + END)


def pulse(slug, rev_, rec, edit=None):
    """What open Pages poll. edit: the last content save {rev, prev_rev, by, at}; prev_rev's HTML is kept at
    build/live/<slug>.prev.html so a reader can see what that save changed."""
    out = {'slug': slug, 'rev': rev_, 'work': rec}
    if edit:
        out['edit'] = edit
    return out


def edit_file(root, slug):
    return Path(root) / 'build' / 'live' / (slug + '.edit.json')


def record_edit(root, slug, old_html, new_html, by):
    """Before a freshly built Page replaces the live one: keep the old HTML and note who made the change."""
    root = Path(root)
    new_rev = html_rev(new_html)
    old_rev = html_rev(old_html) if old_html else ''
    if old_rev and old_rev == new_rev:
        return
    if old_html:
        _atomic_write(root / 'build' / 'live' / (slug + '.prev.html'), old_html)
    else:
        (root / 'build' / 'live' / (slug + '.prev.html')).unlink(missing_ok=True)
    _atomic_write(edit_file(root, slug), json.dumps({'rev': new_rev, 'prev_rev': old_rev, 'by': _clip(by, 60),
                                                     'at': iso(now_utc())}))


def live_files(root, slug):
    """Every per-Page file under build/ (for deletion)."""
    b = Path(root) / 'build'
    return [b / (slug + '.html'), b / 'og' / (slug + '.png'), b / 'live' / (slug + '.json'),
            b / 'live' / (slug + '.prev.html'), edit_file(root, slug)]


def html_rev(raw):
    m = re.search(r'id="hp-work"[^>]*\bdata-rev="([0-9a-f]*)"', raw)
    return m.group(1) if m else ''


def sync(root, slug, rec=None, patch=True):
    """Make build/<slug>.html's status block and build/live/<slug>.json match the current work record."""
    root = Path(root)
    rec = load(root, slug) if rec is None else rec
    f = root / 'build' / (slug + '.html')
    if not f.is_file():
        return False
    raw = f.read_text()
    r = html_rev(raw) or rev(root, slug)
    if patch:
        new = block(slug, r, rec)
        if START in raw:
            out = re.sub(re.escape(START) + r'[\s\S]*?' + re.escape(END), lambda _: new, raw, count=1)
        else:
            out = re.sub(r'(<div id="root">)', lambda m: new + m.group(1), raw, count=1)
        if out != raw:
            _atomic_write(f, out)
    try:
        edit = json.loads(edit_file(root, slug).read_text())
    except (OSError, ValueError):
        edit = None
    _atomic_write(root / 'build' / 'live' / (slug + '.json'), json.dumps(pulse(slug, r, rec, edit)))
    return True


def strip_status_comment(tsx):
    """Drop the status line(s) pages_read / `pages.py read` put in front of the source."""
    while STATUS_COMMENT.match(tsx):
        tsx = STATUS_COMMENT.sub('', tsx, count=1)
    return tsx


def status_comment(rec):
    return '/* hermes-page-status: ' + json.dumps(public(rec)).replace('*/', '* /') + ' */\n'


def headers(root=ROOT, slugs=None):
    """For build.mjs: per Page, the tag bar and status block HTML plus the work state for the index."""
    from page_tags import tag_header
    root = Path(root)
    out, errors = {}, []
    for base in ('src', 'samples'):
        for m in sorted((root / base).glob('*/meta.json')):
            slug = m.parent.name
            if slugs and slug not in slugs:
                continue
            try:
                tags = tag_header(json.loads(m.read_text()).get('tags'))
            except ValueError as e:
                errors.append(slug + ': ' + str(e))
                continue
            rec = load(root, slug)
            out[slug] = {'tags': tags, 'work': block(slug, rev(root, slug), rec), 'state': derived_state(rec) if rec else ''}
    if errors:
        raise SystemExit('\n'.join(errors))
    return out


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    if '--headers' in sys.argv:
        print(json.dumps(headers(ROOT)))
