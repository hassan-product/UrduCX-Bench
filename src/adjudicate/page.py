"""The adjudication interface.

One self-contained document with no external assets, because the point of serving from
localhost is that the data never leaves the machine - a page that pulls a stylesheet from
a CDN quietly announces every visit.

Two views: judging, and the results computed from those judgements. Switching pass or
turning blindness off are controls here rather than command-line flags, so a session can
move between them without restarting and losing its place.
"""

from __future__ import annotations

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Adjudication</title><style>
:root{--bg:#f4f6f8;--card:#fff;--ink:#12171d;--soft:#5a6673;--faint:#8992a0;--line:#e0e5ea;
  --go:#1b6558;--warn:#9c4436;--goSoft:#e6f0ed;--warnSoft:#f7ebe8}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0e1218;--card:#171d25;
  --ink:#e7edf3;--soft:#a7b2be;--faint:#7b8592;--line:#252d37;--go:#5cb5a2;--warn:#d4867a;
  --goSoft:#152420;--warnSoft:#241713}}
*{box-sizing:border-box}
body{font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;
  background:var(--bg);color:var(--ink)}
.wrap{max-width:1140px;margin:0 auto;padding:18px 22px 60px}
nav{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:12px}
.tab{background:none;border:0;padding:6px 2px;font:600 13px/1 inherit;letter-spacing:.04em;
  text-transform:uppercase;color:var(--faint);cursor:pointer;border-bottom:2px solid transparent}
.tab.on{color:var(--ink);border-bottom-color:var(--go)}
.spacer{flex:1}
select,.toggle{font:13px inherit;padding:5px 8px;border:1px solid var(--line);
  border-radius:5px;background:var(--card);color:var(--ink);cursor:pointer}
.toggle.off{border-color:var(--warn);color:var(--warn);background:var(--warnSoft)}
.count{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--soft)}
.bar{height:3px;background:var(--line);border-radius:2px;overflow:hidden;margin-bottom:18px}
.bar i{display:block;height:100%;background:var(--go);transition:width .25s}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:20px;
  margin-bottom:14px}
.text{font-size:19px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
.meta{margin-top:12px;font:12px ui-monospace,Menlo,monospace;color:var(--faint)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.grp{font:11px ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.09em;
  color:var(--faint);margin:14px 0 5px}
label.opt{display:block;padding:6px 9px;border-radius:5px;cursor:pointer;font-size:14px}
label.opt:hover{background:var(--bg)}
label.opt.sel{background:var(--go);color:#fff}
input[type=radio],input[type=checkbox]{margin-right:7px}
#def{position:sticky;top:18px;background:var(--bg);border:1px solid var(--line);
  border-radius:8px;padding:16px;font-size:13.5px;min-height:210px}
#def h3{margin:0 0 8px;font:12px ui-monospace,Menlo,monospace;color:var(--go)}
#def .ex{margin:7px 0 0;padding-left:10px;border-left:2px solid var(--line);color:var(--soft)}
#def .no{border-left-color:var(--warn)}
.extras{margin-top:16px;padding-top:14px;border-top:1px solid var(--line);font-size:14px}
.extras label{display:block;margin:7px 0;cursor:pointer}
textarea{width:100%;padding:8px;border:1px solid var(--line);border-radius:5px;
  font:13px inherit;margin-top:6px;background:var(--card);color:var(--ink)}
button.go{background:var(--go);color:#fff;border:0;padding:11px 26px;border-radius:6px;
  font:600 15px inherit;cursor:pointer;margin-top:16px}
button.go:disabled{background:var(--faint);cursor:not-allowed}
button.ghost{background:none;border:0;color:var(--soft);font:400 15px inherit;
  padding:11px 12px;cursor:pointer;margin-top:16px}
button:focus-visible,select:focus-visible,label.opt:focus-within{outline:2px solid var(--go);
  outline-offset:2px}
#reveal{display:none;background:var(--card);border:1px solid var(--line);
  border-left:3px solid var(--go);border-radius:6px;padding:13px 16px;margin-bottom:14px;font-size:14px}
#shown{background:var(--warnSoft);border:1px solid var(--warn);border-radius:6px;
  padding:13px 16px;margin-bottom:14px;font-size:14px;color:var(--warn)}
b.mono{font:600 12px ui-monospace,Menlo,monospace}
.done{text-align:center;padding:70px 20px}
/* No min-width: a table that overflows scrolls its first column out of view, leaving
   numbers with nothing to identify them. Below the breakpoint the estimate bar is
   dropped instead - it is a second reading of numbers already in the row. */
table{width:100%;border-collapse:collapse;font-size:14px;margin:8px 0 2px;
  table-layout:fixed}
col.c-name{width:34%}col.c-num{width:15%}col.c-rate{width:13%}col.c-ci{width:17%}
col.c-gauge{width:21%}
@media(max-width:760px){
  col.c-gauge,th.gauge-h,td.gauge-c{display:none}
  col.c-name{width:40%}col.c-num{width:19%}col.c-rate{width:17%}col.c-ci{width:24%}
  table{font-size:13px}
}
th,td{text-align:left;padding:8px 10px 8px 0;border-bottom:1px solid var(--line);
  vertical-align:middle}
th{font:400 11px ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.08em;
  color:var(--faint);white-space:nowrap}
td.name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
td.n{font-family:ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;text-align:right;
  white-space:nowrap}
td.rate{font-weight:600}
/* Estimate with its interval. The band is the finding; the tick is only its midpoint,
   so the band is drawn solid and the tick kept small. */
.gauge{position:relative;height:16px;margin-right:4px}
.gauge::before{content:"";position:absolute;left:0;right:0;top:7px;height:2px;
  background:var(--line);border-radius:1px}
.gauge i{position:absolute;top:5px;height:6px;background:var(--go);opacity:.32;border-radius:3px}
.gauge b{position:absolute;top:2px;width:2px;height:12px;background:var(--go);border-radius:1px}
.t{border-bottom:1px dotted var(--faint);cursor:help}
.t:focus-visible{outline:2px solid var(--go);outline-offset:2px}
/* The plain reading comes first and the statistic sits under it, because a number
   nobody can interpret is not evidence to the person being asked to act on it. */
.verdict{background:var(--goSoft);border:1px solid var(--go);border-radius:8px;
  padding:20px 22px;margin-bottom:14px}
.verdict h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--go);
  margin-bottom:12px}
.verdict ul{margin:0;padding-left:20px}
.verdict li{margin-bottom:9px;font-size:15px;line-height:1.55}
.verdict li:last-child{margin-bottom:0}
.lede{font-size:14px;line-height:1.6;color:var(--soft);margin:0 0 4px}
.fine{font:12px ui-monospace,Menlo,monospace;color:var(--faint);margin:6px 0 0}
.caution{background:var(--warnSoft);border:1px solid var(--warn);border-radius:7px;
  padding:14px 16px;margin:12px 0 0}
.caution h3{margin:0 0 6px;font-size:13px;font-weight:600;color:var(--warn)}
.caution p{margin:0 0 6px;font-size:13.5px;line-height:1.55;color:var(--ink)}
.caution p:last-child{margin:0}
.helpbtn{background:none;border:1px solid var(--line);border-radius:50%;width:26px;
  height:26px;color:var(--soft);cursor:pointer;font:600 13px inherit;padding:0}
.helpbtn:hover{border-color:var(--go);color:var(--go)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:8px;
  padding:20px 22px;margin-bottom:14px}
.panel h2{margin-bottom:10px}
.panel dl{margin:0}
.panel dt{font:600 13px inherit;margin-top:12px}
.panel dt:first-child{margin-top:0}
.panel dd{margin:2px 0 0;font-size:13.5px;color:var(--soft);line-height:1.55}
.dismiss{background:none;border:0;color:var(--faint);cursor:pointer;font:13px inherit;
  padding:6px 0 0}
.labelname{font-size:14px}
.labelid{font:11px ui-monospace,Menlo,monospace;color:var(--faint);margin-left:6px}
label.opt.sel .labelid{color:rgba(255,255,255,.72)}
.note{font-size:13px;color:var(--soft);margin:8px 0 0}
.chip{font:13px inherit;padding:5px 11px;margin:0 7px 7px 0;border:1px solid var(--line);
  border-radius:14px;background:var(--card);color:var(--soft);cursor:pointer}
.chip:hover{border-color:var(--go);color:var(--ink)}
.chip.on{background:var(--go);border-color:var(--go);color:#fff}
.warnnote{color:var(--warn)}
h2{font-size:15px;font-weight:600;margin:0 0 4px}
h2 .sub{font:400 13px inherit;color:var(--faint);margin-left:8px}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body><div class="wrap">
<nav>
  <button class="tab on" id="tJudge" onclick="show('judge')">Judge</button>
  <button class="tab" id="tScore" onclick="show('score')">Results</button>
  <span class="spacer"></span>
  <select id="mode" onchange="setPass()" title="which pass to work through"></select>
  <button class="toggle" id="blind" onclick="toggleBlind()"></button>
  <button class="helpbtn" id="help" onclick="toggleHelp()" title="what the terms mean">?</button>
  <span class="count" id="count"></span>
</nav>
<div class="bar"><i id="prog"></i></div>
<div id="glossary" style="display:none"></div>
<div id="judge"><div id="intro"></div><div id="reveal"></div><div id="app"></div></div>
<div id="score" style="display:none"></div>
</div><script>
let CFG=null,item=null,back=0,view='judge';

async function boot(){CFG=await (await fetch('./config')).json();paintState(CFG);
  showIntro();next();}

function paintState(s){
  const m=document.getElementById('mode');
  if(!m.options.length){CFG.modes.forEach(x=>{const o=document.createElement('option');
    o.value=x;m.appendChild(o);});}
  [...m.options].forEach(o=>{o.textContent=o.value+' ('+(s.counts[o.value]??0)+')';});
  m.value=s.mode;
  const b=document.getElementById('blind');
  b.textContent=s.blind?'blind':'predictions shown';
  b.className='toggle'+(s.blind?'':' off');
  b.title=s.blind?'model answers are withheld until you commit':
    'judgements made now are recorded as not blind and excluded from scoring by default';
  document.getElementById('count').textContent=s.done+' / '+s.total;
  document.getElementById('prog').style.width=(s.total?100*s.done/s.total:0)+'%';
}

function show(v){view=v;
  document.getElementById('judge').style.display=v==='judge'?'':'none';
  document.getElementById('score').style.display=v==='score'?'':'none';
  document.getElementById('tJudge').className='tab'+(v==='judge'?' on':'');
  document.getElementById('tScore').className='tab'+(v==='score'?' on':'');
  if(v==='score')loadScore();}

async function setPass(){const r=await post('./pass',{mode:document.getElementById('mode').value});
  paintState(r);document.getElementById('reveal').style.display='none';next();}

async function toggleBlind(){const r=await post('./pass',{blind:!CFG.blind});
  CFG.blind=r.blind;paintState(r);next();}

async function post(url,body){return (await (await fetch(url,{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json());}

function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);
  return d.innerHTML}

// Label ids are written for code; the person reading them is not. The id stays on
// screen because it is what gets recorded, but it stops being the thing you read first.
function human(id){const w=String(id).replace(/_/g,' ');
  return w.charAt(0).toUpperCase()+w.slice(1);}

function toggleHelp(){const g=document.getElementById('glossary');
  if(g.style.display!=='none'){g.style.display='none';return}
  g.style.display='';
  g.innerHTML='<div class="panel"><h2>What the terms mean</h2><dl>'+
    Object.entries(GLOSS).map(([k,v])=>'<dt>'+esc(GLOSS_NAMES[k]||k)+'</dt><dd>'+
    esc(v)+'</dd>').join('')+'</dl>'+
    '<button class="dismiss" onclick="toggleHelp()">close</button></div>';}

function showIntro(){if(localStorage.getItem('adj_intro')==='seen')return;
  document.getElementById('intro').innerHTML='<div class="panel">'+
    '<h2>What you are doing here</h2>'+
    '<p class="lede">You are reading one item at a time and deciding which label it '+
    'belongs to. Your answers become the yardstick everything else is measured against.</p>'+
    '<p class="lede"><b>You will not see what the models guessed until after you commit.</b> '+
    'Being shown two candidate answers and asked which is better is a preference, not an '+
    'independent judgement — and the whole value of your labels is that they are '+
    'independent.</p>'+
    '<p class="lede">Some items are ones the models already agree on. They are mixed in '+
    'and look identical to the rest. They are there to catch the case where every model '+
    'is confidently wrong about the same thing.</p>'+
    '<p class="lede">Open <b>Results</b> at any point to see what your answers say so far.</p>'+
    '<button class="dismiss" id="hideintro">got it — hide this</button></div>';
  document.getElementById('hideintro').onclick=()=>{
    localStorage.setItem('adj_intro','seen');
    document.getElementById('intro').innerHTML='';};}

async function next(){const r=await (await fetch('./next')).json();
  CFG.blind=r.blind;paintState(r);
  if(!r.item){document.getElementById('app').innerHTML='<div class="card done">'+
    '<h2>Nothing left in this pass.</h2><p class="note">'+r.done+' of '+r.total+
    ' judged. Switch pass above, or open Results.</p></div>';return;}
  item=r.item;render();}

function render(){let o='';
  for(const g in CFG.groups){o+='<div class="grp">'+esc(g.replace(/_/g,' '))+'</div>';
    CFG.groups[g].forEach(id=>{o+='<label class="opt" data-def="'+esc(id)+'">'+
      '<input type="radio" name="label" value="'+esc(id)+'" onchange="pick(this)">'+
      '<span class="labelname">'+esc(human(id))+'</span>'+
      '<span class="labelid">'+esc(id)+'</span></label>';});}
  o+='<div class="grp">no match</div><label class="opt" data-def="">'+
    '<input type="radio" name="label" value="__none__" onchange="pick(this)">'+
    'none of these fit</label><div id="why" style="display:none;margin:6px 0 0 10px">';
  CFG.reasons.forEach(r=>{o+='<label class="opt"><input type="radio" name="why" value="'+
    esc(r[0])+'" onchange="enable()">'+esc(r[1])+'</label>';});
  o+='</div>';
  let flags='';CFG.flags.forEach(f=>{flags+='<label><input type="checkbox" name="flag" '+
    'value="'+esc(f)+'"> '+esc(f.replace(/_/g,' '))+'</label>';});
  const shown=item.predictions?'<div id="shown"><b>predictions shown before you chose</b> — '+
    Object.entries(item.predictions).map(([m,v])=>esc(m)+' <b class="mono">'+esc(v)+'</b>')
    .join(' · ')+'<br>this judgement is recorded as not blind</div>':'';
  const bits=Object.entries(item.meta||{}).slice(0,5).map(([k,v])=>esc(k)+' '+esc(v)).join(' · ');
  document.getElementById('app').innerHTML=shown+
    '<div class="card"><div class="text" dir="auto">'+esc(item.text)+'</div>'+
    '<div class="meta">'+bits+'</div></div>'+
    '<div class="card"><div class="cols"><div>'+o+
    '<div class="extras"><label>second, genuinely separate issue'+
    '<select id="sec" style="width:100%;margin-top:6px"><option value="">— none —</option>'+
    '</select></label>'+flags+
    '<textarea id="notes" rows="2" placeholder="note (optional)"></textarea>'+
    '<button class="go" id="go" disabled onclick="save(false)">Confirm</button>'+
    '<button class="ghost" onclick="save(true)">Skip</button>'+
    '<button class="ghost" onclick="goBack()">◀ redo earlier</button>'+
    '</div></div><div><div id="def"><h3>hover a label</h3>'+
    '<p class="note">Its definition, examples and boundary note appear here.</p>'+
    '</div></div></div></div>';}

function showDef(id){const d=document.getElementById('def');
  if(!id){d.innerHTML='<h3>none of these fit</h3><p class="note">Use this when no label '+
    'genuinely applies. Forcing an item into the nearest one produces a wrong label that '+
    'looks like a right one.</p>';return}
  const l=CFG.defs[id];if(!l){d.innerHTML='<h3>'+esc(id)+'</h3>';return}
  d.innerHTML='<h3>'+esc(id)+'</h3><p>'+esc(l.definition)+'</p>'+
    (l.positive_examples||[]).map(e=>'<p class="ex" dir="auto">✓ '+esc(e)+'</p>').join('')+
    (l.negative_example?'<p class="ex no" dir="auto">✗ '+esc(l.negative_example)+'</p>':'')+
    (l.negative_rationale?'<p class="ex no">'+esc(l.negative_rationale)+'</p>':'');}

function pick(el){document.querySelectorAll('label.opt').forEach(l=>l.classList.remove('sel'));
  el.closest('label').classList.add('sel');
  document.getElementById('why').style.display=el.value==='__none__'?'block':'none';
  const s=document.getElementById('sec');
  s.innerHTML='<option value="">— none —</option>'+CFG.ids.filter(i=>i!==el.value)
    .map(i=>'<option value="'+esc(i)+'">'+esc(i)+'</option>').join('');
  enable();}

function enable(){const p=document.querySelector('input[name=label]:checked');
  const w=document.querySelector('input[name=why]:checked');
  document.getElementById('go').disabled=!p||(p.value==='__none__'&&!w);}

async function save(skip){const p=document.querySelector('input[name=label]:checked');
  const w=document.querySelector('input[name=why]:checked');
  const flags={};document.querySelectorAll('input[name=flag]:checked')
    .forEach(f=>flags[f.value]=true);
  if(w)flags['reason:'+w.value]=true;
  const body={item_id:item.id,skipped:!!skip,label:skip?null:p.value,
    secondary:skip?null:(document.getElementById('sec').value||null),
    flags:skip?{}:flags,notes:skip?'':document.getElementById('notes').value};
  const res=await post('./save',body);reveal(res,body.label);back=0;paintState(res);next();}

function reveal(res,mine){const r=document.getElementById('reveal');
  if(!res.predictions||!Object.keys(res.predictions).length){r.style.display='none';return}
  const vals=Object.values(res.predictions);r.style.display='block';
  r.innerHTML='you chose <b class="mono">'+esc(mine)+'</b> · '+
    Object.entries(res.predictions).map(([m,v])=>esc(m)+' <b class="mono">'+esc(v)+'</b>')
    .join(' · ')+(new Set(vals).size===1?' — they agreed.':' — <b>they disagreed.</b>');}

async function goBack(){const r=await (await fetch('./back?steps='+(back+1))).json();
  if(!r.item){alert('No earlier judgement to redo.');return}
  back=r.steps;item=r.item;render();restore(r.previous);
  document.getElementById('reveal').style.display='none';}

function restore(p){if(!p)return;
  const radio=document.querySelector('input[name=label][value="'+(p.label||'')+'"]');
  if(radio){radio.checked=true;pick(radio);}
  Object.keys(p.flags||{}).forEach(f=>{
    if(f.startsWith('reason:')){const w=document.querySelector(
      'input[name=why][value="'+f.slice(7)+'"]');if(w)w.checked=true;}
    else{const c=document.querySelector('input[name=flag][value="'+f+'"]');if(c)c.checked=true;}});
  if(p.secondary){const s=document.getElementById('sec');if(s)s.value=p.secondary;}
  document.getElementById('notes').value=p.notes||'';enable();
  const h=document.createElement('div');h.className='meta warnnote';
  h.textContent='revising — you had chosen: '+(p.label||'skipped');
  document.querySelector('.card').appendChild(h);}

const GLOSS_NAMES={correct:'Got right',rate:'Score',ci:'Could really be',
 estimate:'How sure',joint:'Every model agreed and all were wrong',
 kappa:'Agreement between models',excluded:'Excluded from scoring',
 spread:'Gap between groups',p:'How likely chance alone explains it',
 mde:'What this test could have seen',blind:'Judging blind',controls:'Control items'};

const GLOSS={
 correct:'How many the model got right, out of the items you judged.',
 rate:'Correct divided by judged, as a percentage.',
 ci:'The range the true rate plausibly sits in. Computed as a Wilson interval, which '+
    'stays honest on small samples where the usual formula does not. A wide band means '+
    'few items, not a worse model.',
 estimate:'The bar is the plausible range; the tick is the single best guess. Two rows '+
    'whose bars overlap are not reliably different.',
 joint:'Items where every model gave the same answer and all of them were wrong. '+
    'Agreement between models can never reveal this - they look confident and are not. '+
    'Only a human label exposes it.',
 kappa:'Agreement between two models, discounted for what chance alone would produce. '+
    '1.0 is perfect, 0 is no better than guessing. Above 0.8 is usually called strong.',
 excluded:'Judgements not counted: ones you skipped, and ones made while the model '+
    'answers were on screen. A skipped item is an unanswered question, not a wrong '+
    'answer, and mixing two protocols into one number makes it meaningless.',
 spread:'The gap between the best and worst group. On its own it means little - a gap '+
    'can appear from chance alone.',
 p:'How often pure chance would produce a gap this large. Below 0.05 is the usual bar '+
   'for calling a difference real. 0.7 means seven times in ten, chance alone does this.',
 mde:'The smallest gap this many items could reliably have found. If it is larger than '+
    'the gap you observed, a real difference could be hiding - the result is a ceiling, '+
    'not a zero.',
 blind:'Model answers are withheld until after you commit. Being shown two candidates '+
    'and asked which is better is a preference, not an independent judgement.',
 controls:'Items where the models already agree with each other. Judging them is the '+
    'only way to catch the case where every model is wrong together.'};

function t(key,text){return '<span class="t" tabindex="0" title="'+esc(GLOSS[key])+'">'+
  esc(text)+'</span>';}

function band(r){
  const lo=Math.max(0,r.low),hi=Math.min(100,r.high);
  return '<td class="n">'+r.hits+'/'+r.total+'</td>'+
    '<td class="n rate">'+r.pct.toFixed(1)+'%</td>'+
    '<td class="n">'+lo.toFixed(1)+'–'+hi.toFixed(1)+'</td>'+
    '<td class="gauge-c"><div class="gauge" title="'+r.pct.toFixed(1)+'% — plausible '+
    'range '+lo.toFixed(1)+' to '+hi.toFixed(1)+'"><i style="left:'+lo+'%;width:'+
    Math.max(hi-lo,0.8)+'%"></i><b style="left:'+r.pct+'%"></b></div></td>';}

function head(first){return '<colgroup><col class="c-name"><col class="c-num">'+
  '<col class="c-rate"><col class="c-ci"><col class="c-gauge"></colgroup><thead><tr><th>'+
  esc(first||'measure')+'</th><th class="n">'+t('correct','got right')+
  '</th><th class="n">'+t('rate','score')+'</th><th class="n">'+
  t('ci','could really be')+'</th><th class="gauge-h">'+t('estimate','how sure')+
  '</th></tr></thead>';}

// Rounded, spoken forms. "About two in three" is what a reader takes away; 65.2% is
// what they can check.
function fraction(pct){
  const near=[[90,'about 9 in 10'],[80,'about 4 in 5'],[75,'about 3 in 4'],
    [67,'about 2 in 3'],[60,'about 3 in 5'],[50,'about half'],[40,'about 2 in 5'],
    [33,'about 1 in 3'],[25,'about 1 in 4'],[20,'about 1 in 5'],[10,'about 1 in 10']];
  let best=near[0];
  near.forEach(n=>{if(Math.abs(n[0]-pct)<Math.abs(best[0]-pct))best=n;});
  return best[1];}

function kappaWord(k){if(k==null)return 'unknown';
  if(k>=0.8)return 'strong';if(k>=0.6)return 'moderate';
  if(k>=0.4)return 'weak';return 'little better than chance';}

function chanceWord(p){
  if(p>=0.5)return Math.round(p*10)+' times out of 10';
  if(p>=0.1)return 'about '+Math.round(p*100)+' times in 100';
  return 'fewer than '+Math.max(1,Math.round(p*100))+' times in 100';}

async function loadScore(){const el=document.getElementById('score');
  el.innerHTML='<div class="card"><p class="note">computing…</p></div>';
  const by=CFG.by||'';const s=await (await fetch('./score'+(by?'?by='+by:''))).json();

  if(!s.models.length){el.innerHTML='<div class="card"><h2>Nothing to score yet</h2>'+
    '<p class="lede">'+s.judged+' items judged. Once your data carries model '+
    'predictions, this page compares them against your answers.</p></div>';return;}

  const best=s.models.reduce((a,b)=>b.pct>a.pct?b:a);
  const worst=s.models.reduce((a,b)=>b.pct<a.pct?b:a);

  // The plain reading, first and largest. Everything below it is the evidence.
  let v='<div class="verdict"><h2>What this says</h2><ul>';
  v+='<li>The best model gets <b>'+fraction(best.pct)+'</b> right — '+
    esc(best.model)+' at '+best.pct.toFixed(0)+'%.</li>';
  if(s.models.length>1&&best.low>worst.high){
    v+='<li>'+esc(best.model)+' is <b>genuinely ahead</b> of '+esc(worst.model)+
      '; the gap is bigger than the uncertainty.</li>';}
  else if(s.models.length>1){
    v+='<li>The models score differently, but <b>not by enough to call a winner</b> — '+
      'their plausible ranges overlap.</li>';}
  if(s.joint){v+='<li>When every model agreed with the others, they were still '+
    '<b>all wrong '+fraction(s.joint.pct)+'</b> of those times. Agreement is not proof.</li>';}
  if(s.groups.length){const g=s.groups[0];
    v+='<li>'+(g.significant?'One group is handled <b>measurably worse</b> than the others.'
      :'<b>No group is handled meaningfully worse</b> than another'+
      (g.mde>g.spread?', though this test could not have spotted a small difference.':'.'))+
      '</li>';}
  v+='<li>Based on <b>'+s.scored+'</b> items you judged by hand'+
    (s.excluded?', with '+s.excluded+' set aside':'')+'.</li></ul></div>';

  let h=v;

  h+='<div class="card"><h2>How often each model was right</h2>'+
    '<p class="lede">Out of the '+s.scored+' items you judged. The "could really be" '+
    'column is the range the true figure plausibly sits in — we tested a sample, not '+
    'everything.</p><table>'+head('model')+'<tbody>';
  s.models.forEach(m=>{h+='<tr><td class="name">'+esc(m.model)+'</td>'+band(m)+'</tr>';});
  h+='</tbody></table><p class="note">Two rows whose bars overlap are not reliably '+
    'different, however far apart the scores look.</p></div>';

  if(s.joint){h+='<div class="card"><h2>When every model agreed — were they right?</h2>'+
    '<p class="lede">These are the items where the models all gave the same answer. '+
    'Teams often treat that as a safe signal. On '+fraction(s.joint.pct)+' of them, '+
    'they were all wrong together.</p><table>'+head('')+'<tbody><tr>'+
    '<td class="name">agreed, but wrong</td>'+band(s.joint)+'</tr></tbody></table>'+
    '<p class="note">Models agreeing with each other can never reveal this. Only your '+
    'labels can.</p></div>';}

  if(s.agreement){const k=s.agreement.kappa;
    h+='<div class="card"><h2>Do the models agree with each other?</h2>'+
      '<p class="lede">'+esc(s.agreement.pair)+' give the same answer '+
      s.agreement.pct.toFixed(0)+'% of the time. Allowing for agreements that would '+
      'happen by luck alone, that is <b>'+kappaWord(k)+'</b>'+
      (k!==null&&k<0.6?' — they often reach different conclusions on the same item.':'.')+
      '</p><table>'+head('')+'<tbody><tr><td class="name">same answer</td>'+
      band(s.agreement)+'</tr></tbody></table>'+
      '<p class="fine">'+t('kappa',"Cohen's kappa")+' '+k+'</p></div>';}

  if(s.fields.length){h+='<div class="card"><h2>Break the numbers down</h2>'+
    '<p class="lede">Split the score by anything recorded against your items — to see '+
    'whether one kind of item is handled worse than the rest.</p><p>'+
    s.fields.map(f=>'<button class="chip'+(f===by?' on':'')+'" data-field="'+
      esc(f)+'">'+esc(human(f))+'</button>').join('')+
    (by?'<button class="chip" data-field="">clear</button>':'')+'</p></div>';}

  s.groups.forEach(g=>{
    h+='<div class="card"><h2>'+esc(g.model)+'<span class="sub">split by '+
      esc(human(s.by))+'</span></h2>'+
      '<p class="lede">'+(g.significant
        ? 'One group really is handled worse. A gap this large turns up by chance '+
          chanceWord(g.p)+', so it is unlikely to be luck.'
        : 'No real difference. The '+g.spread.toFixed(0)+'-point gap you can see is the '+
          'kind chance produces on its own — shuffling the groups at random gives a gap '+
          'this big '+chanceWord(g.p)+'.')+'</p>'+
      '<table>'+head(human(s.by))+'<tbody>';
    g.cells.forEach(c=>{h+='<tr><td class="name">'+esc(human(c.group))+'</td>'+
      band(c)+'</tr>';});
    h+='</tbody></table>';
    if(!g.significant&&g.mde>g.spread){
      h+='<div class="caution"><h3>What this test could not have seen</h3>'+
        '<p>It would reliably have caught a gap bigger than <b>'+g.mde.toFixed(0)+
        ' points</b>. You saw '+g.spread.toFixed(0)+'. So a smaller real difference '+
        'could still be hiding — read this as a ceiling, not proof of zero.</p>'+
        (g.needed?'<p>To be sure about a gap this size you would need roughly <b>'+
          g.needed+' items per group</b>.</p>':'')+'</div>';}
    h+='<p class="fine">spread '+g.spread+' pts · '+t('p','p')+' = '+g.p+' · '+
      t('mde','detectable')+' '+g.mde+' pts</p></div>';});

  el.innerHTML=h;}

function setBy(f){CFG.by=f;loadScore();}

// One listener each, rather than a handler written into every element: the markup
// carries data, not code, so nothing in it needs escaping.
document.addEventListener('mouseover',e=>{
  const el=e.target.closest('[data-def]');
  if(el)showDef(el.dataset.def||null);});
document.addEventListener('click',e=>{
  const el=e.target.closest('[data-field]');
  if(el){e.preventDefault();setBy(el.dataset.field);}});
boot();
</script></body></html>"""
