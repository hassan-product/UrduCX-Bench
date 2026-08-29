"""The adjudication interface.

Kept as one self-contained document with no external assets, because the whole point of
serving it from localhost is that the data never leaves the machine. A page that pulls a
stylesheet from a CDN quietly announces every visit.
"""

from __future__ import annotations

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Adjudication</title><style>
*{box-sizing:border-box}
body{font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;
  background:#f5f7f9;color:#12171d}
.wrap{max-width:1120px;margin:0 auto;padding:22px}
header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}
h1{font-size:14px;font-weight:600;margin:0;letter-spacing:.03em;text-transform:uppercase}
.count{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;color:#5a6673}
.bar{height:3px;background:#e0e5ea;border-radius:2px;overflow:hidden;margin-bottom:20px}
.bar i{display:block;height:100%;background:#1b6558;transition:width .25s}
.card{background:#fff;border:1px solid #e0e5ea;border-radius:8px;padding:20px;margin-bottom:14px}
.text{font-size:19px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
.meta{margin-top:12px;font:12px ui-monospace,Menlo,monospace;color:#6b7682}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:860px){.cols{grid-template-columns:1fr}}
.grp{font:11px ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.09em;
  color:#8992a0;margin:14px 0 5px}
label.opt{display:block;padding:6px 9px;border-radius:5px;cursor:pointer;font-size:14px}
label.opt:hover{background:#eef1f4}
label.opt.sel{background:#1b6558;color:#fff}
input[type=radio],input[type=checkbox]{margin-right:7px}
#def{position:sticky;top:22px;background:#fbfcfd;border:1px solid #e0e5ea;border-radius:8px;
  padding:16px;font-size:13.5px;min-height:200px}
#def h3{margin:0 0 8px;font:12px ui-monospace,Menlo,monospace;color:#1b6558}
#def .ex{margin:7px 0 0;padding-left:10px;border-left:2px solid #ccd4dc;color:#3d454e}
#def .no{border-left-color:#9c4436}
.extras{margin-top:16px;padding-top:14px;border-top:1px solid #e0e5ea;font-size:14px}
.extras label{display:block;margin:7px 0;cursor:pointer}
select,textarea{width:100%;padding:8px;border:1px solid #d3d9e0;border-radius:5px;
  font:13px inherit;margin-top:6px}
button{background:#1b6558;color:#fff;border:0;padding:11px 26px;border-radius:6px;
  font-size:15px;font-weight:600;cursor:pointer;margin-top:16px}
button:disabled{background:#b3bbc4;cursor:not-allowed}
button.ghost{background:transparent;color:#6b7682;font-weight:400;padding:11px 12px}
button:focus-visible,label.opt:focus-within{outline:2px solid #1b6558;outline-offset:2px}
#reveal{display:none;background:#fff;border:1px solid #e0e5ea;border-left:3px solid #1b6558;
  border-radius:6px;padding:14px 16px;margin-bottom:14px;font-size:14px}
#reveal b{font:12px ui-monospace,Menlo,monospace}
#shown{background:#fff;border:1px solid #e0e5ea;border-left:3px solid #9c4436;
  border-radius:6px;padding:14px 16px;margin-bottom:14px;font-size:14px}
.done{text-align:center;padding:70px 20px}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body><div class="wrap">
<header><h1 id="mode">Adjudication</h1><div class="count" id="count"></div></header>
<div class="bar"><i id="prog"></i></div>
<div id="reveal"></div><div id="app"></div>
</div><script>
let CFG=null,item=null,back=0,prev=null;

async function boot(){CFG=await (await fetch('./config')).json();
  document.getElementById('mode').textContent=CFG.mode+' — '+CFG.title;next();}

async function next(){const r=await (await fetch('./next')).json();
  document.getElementById('count').textContent=r.done+' / '+r.total+' judged';
  document.getElementById('prog').style.width=(r.total?100*r.done/r.total:0)+'%';
  if(!r.item){document.getElementById('app').innerHTML='<div class="card done"><h2>Done.</h2>'+
    '<p>'+r.done+' judgements saved.</p><p class="count">Close this tab; stop the server with Ctrl-C.</p></div>';
    return;}
  item=r.item;render();}

function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML}

function render(){let o='';
  for(const g in CFG.groups){o+='<div class="grp">'+esc(g.replace(/_/g,' '))+'</div>';
    CFG.groups[g].forEach(id=>{o+='<label class="opt" onmouseenter="showDef(\\''+id+'\\')">'+
      '<input type="radio" name="label" value="'+esc(id)+'" onchange="pick(this)">'+esc(id)+'</label>';});}
  o+='<div class="grp">no match</div><label class="opt" onmouseenter="showDef(null)">'+
    '<input type="radio" name="label" value="__none__" onchange="pick(this)">none of these fit</label>'+
    '<div id="why" style="display:none;margin:6px 0 0 10px">';
  CFG.reasons.forEach(r=>{o+='<label class="opt"><input type="radio" name="why" value="'+esc(r[0])+
    '" onchange="enable()">'+esc(r[1])+'</label>';});
  o+='</div>';

  let flags='';CFG.flags.forEach(f=>{flags+='<label><input type="checkbox" name="flag" value="'+
    esc(f)+'"> '+esc(f.replace(/_/g,' '))+'</label>';});

  const shown=item.predictions?'<div id="shown"><b>predictions shown before you chose</b> — '+
    Object.entries(item.predictions).map(([m,v])=>esc(m)+' <code>'+esc(v)+'</code>').join(' · ')+
    '<br>this judgement is recorded as not blind</div>':'';

  const metaBits=Object.entries(item.meta||{}).slice(0,5)
    .map(([k,v])=>esc(k)+' '+esc(v)).join(' · ');

  document.getElementById('app').innerHTML=shown+
    '<div class="card"><div class="text" dir="auto">'+esc(item.text)+'</div>'+
    '<div class="meta">'+metaBits+'</div></div>'+
    '<div class="card"><div class="cols"><div>'+o+
    '<div class="extras"><label>second, genuinely separate issue<select id="sec">'+
    '<option value="">— none —</option></select></label>'+flags+
    '<textarea id="notes" rows="2" placeholder="note (optional)"></textarea>'+
    '<button id="go" disabled onclick="save(false)">Confirm</button>'+
    '<button class="ghost" onclick="save(true)">Skip</button>'+
    '<button class="ghost" onclick="goBack()">◀ redo an earlier one</button>'+
    '</div></div><div><div id="def"><h3>hover a label</h3>'+
    '<p>Its definition, examples and boundary note appear here.</p></div></div></div></div>';
}

function showDef(id){const d=document.getElementById('def');
  if(!id){d.innerHTML='<h3>none of these fit</h3><p>Use this when no label genuinely '+
    'applies. Do not force an item into the nearest one — a forced label is a wrong '+
    'label that looks like a right one.</p>';return}
  const l=CFG.defs[id];if(!l){d.innerHTML='<h3>'+esc(id)+'</h3>';return}
  d.innerHTML='<h3>'+esc(id)+'</h3><p>'+esc(l.definition)+'</p>'+
    (l.positive_examples||[]).map(e=>'<p class="ex" dir="auto">✓ '+esc(e)+'</p>').join('')+
    (l.negative_example?'<p class="ex no" dir="auto">✗ '+esc(l.negative_example)+'</p>':'')+
    (l.negative_rationale?'<p class="ex no">'+esc(l.negative_rationale)+'</p>':'');}

function pick(el){document.querySelectorAll('label.opt').forEach(l=>l.classList.remove('sel'));
  el.closest('label').classList.add('sel');
  const none=el.value==='__none__';
  document.getElementById('why').style.display=none?'block':'none';
  const sec=document.getElementById('sec');
  sec.innerHTML='<option value="">— none —</option>'+CFG.ids.filter(i=>i!==el.value)
    .map(i=>'<option value="'+esc(i)+'">'+esc(i)+'</option>').join('');
  enable();}

function enable(){const p=document.querySelector('input[name=label]:checked');
  const w=document.querySelector('input[name=why]:checked');
  document.getElementById('go').disabled=!p||(p.value==='__none__'&&!w);}

async function save(skip){const p=document.querySelector('input[name=label]:checked');
  const w=document.querySelector('input[name=why]:checked');
  const flags={};document.querySelectorAll('input[name=flag]:checked').forEach(f=>flags[f.value]=true);
  if(w)flags['reason:'+w.value]=true;
  const body={item_id:item.id,skipped:!!skip,
    label:skip?null:p.value,secondary:skip?null:(document.getElementById('sec').value||null),
    flags:skip?{}:flags,notes:skip?'':document.getElementById('notes').value};
  const res=await (await fetch('./save',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
  reveal(res,body.label);back=0;prev=null;next();}

function reveal(res,mine){const r=document.getElementById('reveal');
  if(!res.predictions||!Object.keys(res.predictions).length){r.style.display='none';return}
  const vals=Object.values(res.predictions);
  r.style.display='block';
  r.innerHTML='you chose <b>'+esc(mine)+'</b> · '+
    Object.entries(res.predictions).map(([m,v])=>esc(m)+' <b>'+esc(v)+'</b>').join(' · ')+
    (new Set(vals).size===1?' — they agreed.':' — <b>they disagreed.</b>');}

async function goBack(){const r=await (await fetch('./back?steps='+(back+1))).json();
  if(!r.item){alert('No earlier judgement to redo.');return}
  back=r.steps;item=r.item;prev=r.previous;render();restore(prev);
  document.getElementById('reveal').style.display='none';}

function restore(p){if(!p)return;
  const radio=document.querySelector('input[name=label][value="'+(p.label||'')+'"]');
  if(radio){radio.checked=true;pick(radio);}
  Object.keys(p.flags||{}).forEach(f=>{
    if(f.startsWith('reason:')){const w=document.querySelector('input[name=why][value="'+f.slice(7)+'"]');
      if(w){w.checked=true;}}
    else{const c=document.querySelector('input[name=flag][value="'+f+'"]');if(c)c.checked=true;}});
  if(p.secondary){const s=document.getElementById('sec');if(s)s.value=p.secondary;}
  document.getElementById('notes').value=p.notes||'';enable();
  const h=document.createElement('div');h.className='meta';h.style.color='#8a5a2b';
  h.textContent='revising — you had chosen: '+(p.label||'skipped');
  document.querySelector('.card').appendChild(h);}
boot();
</script></body></html>"""
