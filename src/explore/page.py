"""The corpus explorer interface.

One self-contained document, no external assets, for the same reason the rest of the
tooling is local: a page that fetches a stylesheet from a CDN announces every visit to
data that was supposed to stay put.

Written for someone deciding what to look at, not someone reading a report. Filters are
always visible and always combinable; every count updates against whatever is selected.
"""

from __future__ import annotations

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corpus explorer</title><style>
:root{--bg:#f4f6f8;--card:#fff;--ink:#12171d;--soft:#5a6673;--faint:#8992a0;--line:#e0e5ea;
  --go:#1b6558;--warn:#9c4436;--goSoft:#e6f0ed;--warnSoft:#f7ebe8}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0e1218;--card:#171d25;
  --ink:#e7edf3;--soft:#a7b2be;--faint:#7b8592;--line:#252d37;--go:#5cb5a2;--warn:#d4867a;
  --goSoft:#152420;--warnSoft:#241713}}
*{box-sizing:border-box}
body{font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;
  background:var(--bg);color:var(--ink)}
.shell{display:grid;grid-template-columns:264px 1fr;gap:20px;max-width:1400px;
  margin:0 auto;padding:18px 22px 60px}
@media(max-width:900px){.shell{grid-template-columns:1fr}}
aside{position:sticky;top:18px;align-self:start;max-height:calc(100vh - 40px);
  overflow-y:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px 18px;
  margin-bottom:14px}
h1{font:600 13px/1 inherit;letter-spacing:.05em;text-transform:uppercase;margin:0 0 14px;
  color:var(--soft)}
h2{font-size:15px;font-weight:600;margin:0 0 4px}
h2 .sub{font:400 13px inherit;color:var(--faint);margin-left:8px}
h3{font:600 11px ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.09em;
  color:var(--faint);margin:16px 0 6px}
h3:first-child{margin-top:0}
input[type=search],input[type=number]{width:100%;padding:8px 10px;border:1px solid var(--line);
  border-radius:6px;background:var(--card);color:var(--ink);font:14px inherit}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:12px inherit;padding:4px 10px;border:1px solid var(--line);border-radius:13px;
  background:var(--card);color:var(--soft);cursor:pointer;white-space:nowrap}
.chip:hover{border-color:var(--go);color:var(--ink)}
.chip.on{background:var(--go);border-color:var(--go);color:#fff}
.chip.tag.on{background:var(--warn);border-color:var(--warn)}
button.act{background:var(--go);color:#fff;border:0;padding:9px 16px;border-radius:6px;
  font:600 14px inherit;cursor:pointer;width:100%;margin-top:10px}
button.ghost{background:none;border:1px solid var(--line);color:var(--soft);padding:8px 14px;
  border-radius:6px;font:14px inherit;cursor:pointer;width:100%;margin-top:8px}
button:focus-visible,.chip:focus-visible,input:focus-visible{outline:2px solid var(--go);
  outline-offset:2px}
nav{display:flex;gap:16px;margin-bottom:14px;flex-wrap:wrap}
.tab{background:none;border:0;padding:6px 2px;font:600 13px/1 inherit;letter-spacing:.04em;
  text-transform:uppercase;color:var(--faint);cursor:pointer;border-bottom:2px solid transparent}
.tab.on{color:var(--ink);border-bottom-color:var(--go)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(126px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden;
  margin-bottom:14px}
.stat{background:var(--card);padding:14px 16px}
.stat b{display:block;font:600 24px/1.1 inherit;font-variant-numeric:tabular-nums}
.stat span{font:11px ui-monospace,Menlo,monospace;text-transform:uppercase;
  letter-spacing:.07em;color:var(--faint)}
table{width:100%;border-collapse:collapse;font-size:14px;table-layout:fixed}
th,td{text-align:left;padding:7px 10px 7px 0;border-bottom:1px solid var(--line);
  overflow:hidden;text-overflow:ellipsis}
th{font:400 11px ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.08em;
  color:var(--faint);white-space:nowrap}
td.n{font-family:ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;
  text-align:right;white-space:nowrap}
.meter{position:relative;height:14px;background:var(--line);border-radius:7px;overflow:hidden}
.meter i{position:absolute;left:0;top:0;bottom:0;background:var(--go);border-radius:7px}
.meter.bad i{background:var(--warn)}
.rev{border-bottom:1px solid var(--line);padding:14px 0}
.rev:last-child{border-bottom:0}
.rev .txt{font-size:15px;line-height:1.65;white-space:pre-wrap;word-break:break-word}
.rev .meta{margin-top:7px;font:11px ui-monospace,Menlo,monospace;color:var(--faint)}
.pill{display:inline-block;padding:1px 7px;border-radius:9px;background:var(--goSoft);
  color:var(--go);font:11px ui-monospace,Menlo,monospace;margin-left:6px}
.pill.model{background:var(--line);color:var(--soft)}
.note{font-size:13px;color:var(--soft);margin:8px 0 0}
.caution{background:var(--warnSoft);border:1px solid var(--warn);border-radius:7px;
  padding:12px 14px;margin:10px 0 0;font-size:13px;line-height:1.55}
.pager{display:flex;gap:8px;align-items:center;margin-top:14px}
.pager button{background:none;border:1px solid var(--line);color:var(--soft);padding:6px 12px;
  border-radius:6px;cursor:pointer;font:13px inherit}
.pager span{font:12px ui-monospace,Menlo,monospace;color:var(--faint)}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body><div class="shell">
<aside><div class="card" id="filters"></div></aside>
<main>
  <nav>
    <button class="tab on" data-tab="overview">Overview</button>
    <button class="tab" data-tab="releases">Releases</button>
    <button class="tab" data-tab="trend">Over time</button>
    <button class="tab" data-tab="reviews">Reviews</button>
    <button class="tab" data-tab="labels">Issue types</button>
  </nav>
  <div id="stats" class="stats"></div>
  <div id="body"></div>
</main></div><script>
let F=null,STATE={platform:[],product:[],rating:[],language:[],year:[],tag:[],label:[],
  q:'',labelled:false,page:0},TAB='overview',R=null;

function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);
  return d.innerHTML}
function human(s){const w=String(s).replace(/_/g,' ');return w.charAt(0).toUpperCase()+w.slice(1)}
function qs(){const p=new URLSearchParams();
  ['platform','product','rating','language','year','tag','label'].forEach(k=>{
    STATE[k].forEach(v=>p.append(k,v));});
  if(STATE.q)p.set('q',STATE.q);
  if(STATE.labelled)p.set('labelled','1');
  p.set('page',STATE.page);return p.toString()}

async function boot(){F=await (await fetch('./facets')).json();paintFilters();load();}

function group(title,key,values,cls){
  return '<h3>'+esc(title)+'</h3><div class="chips">'+values.map(v=>{
    const on=STATE[key].includes(String(v.id!==undefined?v.id:v));
    const id=String(v.id!==undefined?v.id:v);
    const lab=v.label!==undefined?v.label:human(v);
    return '<button class="chip '+(cls||'')+(on?' on':'')+'" data-k="'+esc(key)+
      '" data-v="'+esc(id)+'">'+esc(lab)+'</button>';}).join('')+'</div>';}

function paintFilters(){
  document.getElementById('filters').innerHTML='<h1>Filters</h1>'+
    '<input type="search" id="q" placeholder="search text, any script" value="'+
      esc(STATE.q)+'">'+
    group('Provider','product',F.products)+
    group('Rating','rating',[1,2,3,4,5])+
    group('Language','language',F.languages)+
    group('Platform','platform',F.platforms)+
    group('Year','year',F.years)+
    group('Mentions','tag',F.tags,'tag')+
    (F.labels.length?group('Issue type','label',F.labels):'')+
    '<button class="ghost" data-act="labelled">'+
      (STATE.labelled?'✓ ':'')+'only rows with an issue label</button>'+
    '<button class="act" data-act="export">Export for judging</button>'+
    '<button class="ghost" data-act="clear">Clear all filters</button>'+
    '<p class="note">'+F.total.toLocaleString()+' reviews · '+
      F.labelled.toLocaleString()+' carry an issue label</p>';
  const q=document.getElementById('q');
  q.oninput=()=>{clearTimeout(window._t);
    window._t=setTimeout(()=>{STATE.q=q.value;STATE.page=0;load();},280);};}

async function load(){
  R=await (await fetch('./report?'+qs())).json();
  paintStats();paintBody();}

function paintStats(){const s=R.summary;
  document.getElementById('stats').innerHTML=
    stat(s.total.toLocaleString(),'reviews')+
    stat(s.share+'%','of corpus')+
    stat(s.bad_pct+'%','rated 1–2★')+
    stat(s.median_words,'median words')+
    stat(s.labelled.toLocaleString(),'with a label')+
    stat(s.span||'—','date span');}
function stat(v,l){return '<div class="stat"><b>'+esc(v)+'</b><span>'+esc(l)+'</span></div>'}

function meter(pct,bad){return '<div class="meter'+(bad?' bad':'')+'"><i style="width:'+
  Math.min(100,pct)+'%"></i></div>'}

function bar(rows,title,note){
  if(!rows.length)return '';
  let h='<div class="card"><h2>'+esc(title)+'</h2>'+(note?'<p class="note">'+note+'</p>':'')+
    '<table><colgroup><col style="width:34%"><col style="width:14%"><col style="width:16%">'+
    '<col style="width:36%"></colgroup><thead><tr><th>'+esc(title)+'</th>'+
    '<th class="n">reviews</th><th class="n">1–2★</th><th>share negative</th></tr></thead><tbody>';
  rows.forEach(r=>{h+='<tr><td>'+esc(human(r.key))+'</td><td class="n">'+
    r.total.toLocaleString()+'</td><td class="n">'+r.bad_pct+'%</td><td>'+
    meter(r.bad_pct,r.bad_pct>=60)+'</td></tr>';});
  return h+'</tbody></table></div>';}

function paintBody(){const b=document.getElementById('body');
  if(TAB==='overview'){b.innerHTML=bar(R.byProduct,'Provider')+bar(R.byLanguage,'Language')+
    bar(R.byPlatform,'Platform')+bar(R.byYear,'Year');}
  else if(TAB==='releases'){
    if(!R.releases.length){b.innerHTML='<div class="card"><h2>No releases with enough '+
      'reviews</h2><p class="note">A version needs at least 40 reviews in the current '+
      'filter to appear. A release showing 100% negative on nine reviews is noise wearing '+
      'a headline.</p></div>';return;}
    let h='<div class="card"><h2>Negative share by app version'+
      '<span class="sub">worst first</span></h2>'+
      '<p class="note">Rating and version are both recorded on every review, so this needs '+
      'no labelling and carries no model error. It answers whether a release made things '+
      'worse — and whether the next one fixed it.</p>'+
      '<table><colgroup><col style="width:22%"><col style="width:20%"><col style="width:12%">'+
      '<col style="width:12%"><col style="width:34%"></colgroup><thead><tr><th>app</th>'+
      '<th>version</th><th class="n">reviews</th><th class="n">1–2★</th>'+
      '<th>share negative</th></tr></thead><tbody>';
    R.releases.forEach(r=>{h+='<tr><td>'+esc(human(r.product))+'</td><td>'+esc(r.version)+
      '</td><td class="n">'+r.total+'</td><td class="n">'+r.bad_pct+'%</td><td>'+
      meter(r.bad_pct,r.bad_pct>=60)+'</td></tr>';});
    b.innerHTML=h+'</tbody></table></div>';}
  else if(TAB==='trend'){
    let h='<div class="card"><h2>Volume and negative share by month</h2>'+
      '<table><colgroup><col style="width:18%"><col style="width:16%"><col style="width:14%">'+
      '<col style="width:52%"></colgroup><thead><tr><th>month</th><th class="n">reviews</th>'+
      '<th class="n">1–2★</th><th>share negative</th></tr></thead><tbody>';
    R.trend.forEach(t=>{h+='<tr><td>'+esc(t.month)+'</td><td class="n">'+
      t.total.toLocaleString()+'</td><td class="n">'+t.bad_pct+'%</td><td>'+
      meter(t.bad_pct,t.bad_pct>=60)+'</td></tr>';});
    b.innerHTML=h+'</tbody></table><p class="note">A spike in volume with a spike in '+
      'negative share is what an outage looks like from outside.</p></div>';}
  else if(TAB==='reviews'){
    let h='<div class="card"><h2>Reviews<span class="sub">'+
      R.summary.total.toLocaleString()+' match</span></h2>';
    if(!R.reviews.length)h+='<p class="note">Nothing matches these filters.</p>';
    R.reviews.forEach(r=>{h+='<div class="rev"><div class="txt" dir="auto">'+esc(r.text)+
      '</div><div class="meta">'+esc(human(r.product))+' · '+(r.rating??'?')+'★ · '+
      esc(r.language)+' · '+esc(r.date)+(r.version?' · v'+esc(r.version):'')+
      (r.label?'<span class="pill'+(r.label_source==='model'?' model':'')+'">'+
        esc(human(r.label))+(r.label_source==='model'?' (model)':' (judged)')+'</span>':'')+
      '</div></div>';});
    h+='<div class="pager"><button data-act="prev">← previous</button>'+
      '<span>page '+(R.page+1)+' of '+R.pages+'</span>'+
      '<button data-act="next">next →</button></div>';
    b.innerHTML=h+'</div>';}
  else{
    if(!R.labelMix.length){b.innerHTML='<div class="card"><h2>No issue labels here</h2>'+
      '<p class="note">Issue types exist only where a review has actually been labelled. '+
      'Filter to something narrow, export it, and judge it in the adjudication tool — that '+
      'is how this column grows.</p></div>';return;}
    const m=R.labelMix[0];
    let h='<div class="card"><h2>Issue types<span class="sub">'+m.of_labelled+
      ' labelled reviews</span></h2>'+
      '<div class="caution">These counts cover only the <b>'+m.of_labelled+
      '</b> reviews in this filter that carry a label, out of '+
      R.summary.total.toLocaleString()+' matching. '+m.human+
      ' were judged by a person; the rest are model output, which this corpus measured at '+
      'about 61% agreement with a human. Read the shape, not the rate.</div>'+
      '<table><colgroup><col style="width:40%"><col style="width:14%"><col style="width:12%">'+
      '<col style="width:34%"></colgroup><thead><tr><th>issue</th><th class="n">reviews</th>'+
      '<th class="n">share</th><th>share of labelled</th></tr></thead><tbody>';
    R.labelMix.forEach(r=>{h+='<tr><td>'+esc(human(r.label))+'</td><td class="n">'+
      r.total+'</td><td class="n">'+r.share+'%</td><td>'+meter(r.share)+'</td></tr>';});
    b.innerHTML=h+'</tbody></table></div>';}}

document.addEventListener('click',e=>{
  const chip=e.target.closest('.chip');
  if(chip){const k=chip.dataset.k,v=chip.dataset.v;
    const i=STATE[k].indexOf(v);
    if(i>=0)STATE[k].splice(i,1);else STATE[k].push(v);
    STATE.page=0;paintFilters();load();return;}
  const tab=e.target.closest('.tab');
  if(tab){TAB=tab.dataset.tab;
    document.querySelectorAll('.tab').forEach(t=>t.className='tab'+
      (t.dataset.tab===TAB?' on':''));
    paintBody();return;}
  const act=e.target.closest('[data-act]');
  if(!act)return;
  const a=act.dataset.act;
  if(a==='clear'){STATE={platform:[],product:[],rating:[],language:[],year:[],tag:[],
    label:[],q:'',labelled:false,page:0};paintFilters();load();}
  else if(a==='labelled'){STATE.labelled=!STATE.labelled;STATE.page=0;paintFilters();load();}
  else if(a==='export'){window.location='./export?'+qs();}
  else if(a==='next'&&R.page+1<R.pages){STATE.page=R.page+1;load();}
  else if(a==='prev'&&R.page>0){STATE.page=R.page-1;load();}});
boot();
</script></body></html>"""
