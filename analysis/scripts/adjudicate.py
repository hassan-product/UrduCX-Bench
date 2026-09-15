"""Local adjudication tool: produce human gold labels for the Phase 3 diagnostic.

Serves one review at a time and asks for an intent. Two rules make the output usable as
evidence rather than as a preference survey:

1. The annotator never sees either model's answer before committing. Model predictions are
   withheld from the item payload entirely - not merely hidden in the page - and returned
   only in the response to a saved judgement. Being shown two candidate labels and asked
   which is better is not an independent judgement, and a reviewer would say so.

2. The 69 items where the models disagreed are mixed with 100 controls where they agreed,
   shuffled and indistinguishable. Without controls there is no way to show the annotator
   was not simply siding with a preferred model.

Everything stays on the machine: bound to 127.0.0.1, judgements appended to a local JSONL.
Run it, answer, close it; re-running resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from src.label.taxonomy import load_taxonomy

DIR = Path("spike/phase3_diag")
SAMPLE = DIR / "sample_500.jsonl"
JUDGEMENTS = DIR / "adjudications.jsonl"
RECHECK = DIR / "adjudications_recheck.jsonl"
URDU_JUDGEMENTS = DIR / "adjudications_urdu.jsonl"
URDU_WORKLIST = DIR / "urdu_pass_worklist.jsonl"
TAXONOMY = Path("config/taxonomy.yaml")
MODELS = ("claude-sonnet-5", "claude-opus-5")
CONTROLS = 25

# Categories the taxonomy does not contain yet. The models labelled every item against
# the 24 v2 intents, so they could not have chosen any of these - picking one is therefore
# a coverage gap with a name, not a model error, and analysis must not score it as one.
# Each is here because it was measured, not because it felt missing:
#   support_unresponsive     6.0% of the corpus; two v2 intents push it away in their
#                            own negative examples and nothing takes it in
#   card_activation_failed   1.9%; currently scatters across five unrelated intents
# Added to taxonomy v3 on 2026-08-30 after human adjudication showed the scheme was
# missing them. Both models were re-labelled against v3, so they now have the same 26
# options the annotator does and a pick here is scored like any other intent.
V3_CANDIDATES: tuple[tuple[str, str], ...] = ()

NEW_IN_V3 = {"support_unresponsive", "card_activation_failed"}
SUPPORT_TERMS = re.compile(
    r"helpline|help ?line|customer (care|support|service)|complain|no (response|reply)"
    r"|nahi uthat|pick nahe|response nahi|jawab nahi|koi response"
    r"|ہیلپ ?لائن|جواب نہیں|رسپانس نہیں",
    re.I,
)
CARD_TERMS = re.compile(
    r"\b(debit|credit|visa|master ?card|atm card|virtual card|card)\b|کارڈ", re.I
)

SEED = 20260827

# Controls exist to show the annotator was not siding with a preferred model. They do not
# need to mirror the corpus, so they are drawn only from reviews naming something concrete.
# Rubber-stamping "bht achi app" as unclassifiable 30 times costs annotator attention and
# teaches nothing, because both models already agree there.
#
# Disagreements are NOT filtered. There are exactly 100 in the 490 - the whole population,
# not a sample - and the praise/vague ones among them are where the two models split
# systematically on the taxonomy's missing "unhappy but unspecific" category. Removing them
# would delete the finding.
SPECIFIC = re.compile(
    r"\b(rs|rupee|rupees|pkr|otp|cnic|kyc|sim|loan|bill|agent|refund|transfer|deduct"
    r"|deducted|kat|katay|login|password|pin|block|verif|package|bundle|network|signal"
    r"|internet|4g|cash)\b|[0-9]{2,}|روپے|او ٹی پی|بل|قرض|سم",
    re.I,
)


def names_something_concrete(text: str, rating: int | None) -> bool:
    """True when a review points at an identifiable issue rather than a mood."""
    if SPECIFIC.search(text or ""):
        return True
    return (rating or 5) <= 3 and len((text or "").split()) > 12


def load_model_rows(model: str) -> dict[str, dict[str, Any]]:
    """Answered rows for one model, keyed by review id."""
    path = DIR / f"diag_{model.replace('.', '-')}.jsonl"
    rows = {}
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if row["status"] in ("ok", "cached") and "label" in row:
            rows[row["review_id"]] = row
    return rows


def build_worklist(mode: str = "normal", extra: int = 50) -> list[dict[str, Any]]:
    """Build the item list for one pass.

    normal   - all disagreements plus concrete-agreement controls
    controls - only unjudged agreements, to tighten the both-models-wrong estimate
    recheck  - already-judged items, served blind, for test-retest self-agreement
    """
    if mode == "revisit":
        current = int(load_taxonomy(TAXONOMY).version)
        judged = {}
        if URDU_JUDGEMENTS.exists():
            for raw in URDU_JUDGEMENTS.open(encoding="utf-8"):
                if raw.strip():
                    j = json.loads(raw)
                    judged[j["review_id"]] = j
        items = []
        for raw in URDU_WORKLIST.open(encoding="utf-8"):
            row = json.loads(raw)
            previous = judged.get(row["review_id"])
            if previous is None:
                continue
            if int(previous.get("taxonomy_version", 0)) >= current:
                continue  # already re-judged under the current taxonomy
            text = row.get("text_scrubbed") or ""
            model_used_new = any(i in NEW_IN_V3 for i in row["models"].values())
            if not (
                model_used_new or SUPPORT_TERMS.search(text) or CARD_TERMS.search(text)
            ):
                continue
            if previous["human_intent"] in NEW_IN_V3:
                continue
            items.append(
                {
                    "review_id": row["review_id"],
                    "text": text,
                    "product_id": row["product_id"],
                    "rating": row.get("rating"),
                    "language_detected": row["language"],
                    "_models": {m: {"intent": i} for m, i in row["models"].items()},
                    "_kind": "revisit",
                }
            )
        return items

    if mode == "urdu":
        # Separate pass: a fresh, length-matched, unenriched sample drawn to retest the
        # script-gap hypothesis with gold labels. Its own worklist and its own output.
        items = []
        for raw in URDU_WORKLIST.open(encoding="utf-8"):
            row = json.loads(raw)
            items.append(
                {
                    "review_id": row["review_id"],
                    "text": row.get("text_scrubbed") or "",
                    "product_id": row["product_id"],
                    "rating": row.get("rating"),
                    "language_detected": row["language"],
                    "_models": {m: {"intent": i} for m, i in row["models"].items()},
                    "_kind": "urdu_pass",
                }
            )
        random.Random(SEED).shuffle(items)
        return items

    texts = {
        json.loads(line)["review_id"]: json.loads(line)
        for line in SAMPLE.open(encoding="utf-8")
    }
    per_model = {model: load_model_rows(model) for model in MODELS}
    shared = sorted(set.intersection(*(set(rows) for rows in per_model.values())))

    disagreements, agreements = [], []
    for review_id in shared:
        picks = {m: per_model[m][review_id]["label"] for m in MODELS}
        item = {
            "review_id": review_id,
            "text": texts[review_id].get("text_scrubbed") or "",
            "product_id": texts[review_id]["product_id"],
            "rating": texts[review_id].get("rating"),
            "language_detected": texts[review_id]["language"],
            # Kept server-side; never sent until a judgement is saved.
            "_models": {m: picks[m] for m in MODELS},
            "_kind": "disagreement"
            if picks[MODELS[0]]["intent"] != picks[MODELS[1]]["intent"]
            else "control",
        }
        (disagreements if item["_kind"] == "disagreement" else agreements).append(item)

    rng = random.Random(SEED)
    concrete = [
        a for a in agreements if names_something_concrete(a["text"], a["rating"])
    ]

    if mode == "controls":
        # Only agreements, and only ones not already judged: these tighten the
        # "both models wrong together" interval, which is the thinnest number in the set.
        already = done_ids(JUDGEMENTS)
        fresh = [a for a in concrete if a["review_id"] not in already]
        rng.shuffle(fresh)
        return fresh[:extra]

    if mode == "recheck":
        # Blind test-retest: serve items already judged, with the earlier answer never
        # sent. Self-agreement is weaker evidence than a second annotator, but it is
        # measurable by one person and it is what the project plan already called for.
        judged = done_ids(JUDGEMENTS)
        pool = [i for i in disagreements + concrete if i["review_id"] in judged]
        rng.shuffle(pool)
        return pool[:extra]

    worklist = disagreements + rng.sample(concrete, min(CONTROLS, len(concrete)))
    rng.shuffle(worklist)
    return worklist


def done_ids(path: Path = JUDGEMENTS) -> set[str]:
    """Review ids already judged in this pass, so a restart resumes rather than repeats."""
    if not path.exists():
        return set()
    return {
        json.loads(line)["review_id"]
        for line in path.open(encoding="utf-8")
        if line.strip()
    }


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>UrduCX adjudication</title><style>
*{box-sizing:border-box}
body{font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  margin:0;background:#f6f7f9;color:#1a1d21}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}
h1{font-size:15px;font-weight:600;margin:0;letter-spacing:.02em}
.count{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;color:#5b6470}
.bar{height:4px;background:#e3e6ea;border-radius:2px;overflow:hidden;margin-bottom:18px}
.bar i{display:block;height:100%;background:#2f6f4f;transition:width .25s}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:20px;
  margin-bottom:16px}
.review{font-size:19px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
.meta{margin-top:12px;font:12px ui-monospace,Menlo,monospace;color:#6b7480}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:820px){.cols{grid-template-columns:1fr}}
.fam{font:11px ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.08em;
  color:#8a929c;margin:14px 0 6px}
label.opt{display:block;padding:6px 9px;border-radius:6px;cursor:pointer;font-size:14px}
label.opt:hover{background:#eef1f4}
label.opt.sel{background:#2f6f4f;color:#fff}
input[type=radio]{margin-right:7px}
#def{position:sticky;top:20px;background:#fbfcfd;border:1px solid #e3e6ea;
  border-radius:8px;padding:16px;font-size:13.5px;min-height:190px}
#def h3{margin:0 0 8px;font:12px ui-monospace,Menlo,monospace;color:#2f6f4f}
#def .ex{margin:7px 0 0;padding-left:9px;border-left:2px solid #cfd6dd;color:#41474e}
#def .no{border-left-color:#c0554a}
.extras{margin-top:16px;padding-top:14px;border-top:1px solid #e3e6ea;font-size:14px}
.extras label{display:block;margin:7px 0;cursor:pointer}
textarea{width:100%;margin-top:9px;padding:8px;border:1px solid #d6dae0;border-radius:6px;
  font:13px inherit;resize:vertical}
button{background:#2f6f4f;color:#fff;border:0;padding:11px 26px;border-radius:7px;
  font-size:15px;font-weight:600;cursor:pointer;margin-top:16px}
button:disabled{background:#b6bcc4;cursor:not-allowed}
button.ghost{background:transparent;color:#6b7480;font-weight:400;padding:11px 14px}
#reveal{display:none;background:#fff;border:1px solid #e3e6ea;border-left:4px solid #2f6f4f;
  border-radius:8px;padding:16px;margin-bottom:16px;font-size:14px}
#reveal.miss{border-left-color:#c0554a}
#reveal b{font:12px ui-monospace,Menlo,monospace}
.done{text-align:center;padding:70px 20px}
select{width:100%;padding:8px;border:1px solid #d6dae0;border-radius:6px;font:13px inherit}
</style></head><body><div class="wrap">
<header><h1>UrduCX — adjudication</h1><div class="count" id="count"></div></header>
<div class="bar"><i id="prog"></i></div>
<div id="reveal"></div>
<div id="app"></div>
</div>
<script>
let TAX=null, item=null, state={done:0,total:0}, backSteps=0, prev=null;

async function boot(){
  TAX=await (await fetch('/taxonomy')).json();
  next();
}

async function next(){
  const r=await (await fetch('/next')).json();
  state={done:r.done,total:r.total};
  document.getElementById('count').textContent=r.done+' / '+r.total+' judged';
  document.getElementById('prog').style.width=(r.total?100*r.done/r.total:0)+'%';
  if(!r.item){
    document.getElementById('app').innerHTML=
      '<div class="card done"><h2>All done.</h2><p>'+r.done+
      ' judgements saved to <code>spike/phase3_diag/adjudications.jsonl</code>.</p>'+
      '<p class="count">You can close this window and stop the server with Ctrl-C.</p></div>';
    return;
  }
  item=r.item; render();
}

function render(){
  const fams={};
  TAX.intents.forEach(i=>{(fams[i.family]=fams[i.family]||[]).push(i)});
  let opts='';
  for(const f in fams){
    opts+='<div class="fam">'+f.replace(/_/g,' ')+'</div>';
    fams[f].forEach(i=>{
      opts+='<label class="opt" data-id="'+i.id+'" onmouseenter="showDef(\\''+i.id+
        '\\')"><input type="radio" name="intent" value="'+i.id+
        '" onchange="pick(this)">'+i.id+'</label>';
    });
  }
  opts+='<div class="fam">no match</div><label class="opt" data-id="unclassifiable" '+
    'onmouseenter="showDef(null)"><input type="radio" name="intent" '+
    'value="unclassifiable" onchange="pick(this)">none of these fit</label>'+
    '<div id="whybox" style="display:none;margin:8px 0 0 9px">'+
    '<div class="fam">why does none fit?</div>'+
    '<label class="opt"><input type="radio" name="why" value="praise">'+
    'praise / positive, no complaint</label>'+
    '<label class="opt"><input type="radio" name="why" value="vague">'+
    'unhappy, but names no specific failure</label>'+
    '<label class="opt"><input type="radio" name="why" value="unreadable">'+
    'unreadable fragment or nonsense</label>'+
    '<label class="opt"><input type="radio" name="why" value="offtopic">'+
    'a real, specific issue that no intent covers</label></div>';

  let sec='<option value="">— none —</option>';
  TAX.intents.forEach(i=>{sec+='<option value="'+i.id+'">'+i.id+'</option>'});

  document.getElementById('app').innerHTML=
   (item.models ? '<div class="card" style="border-left:4px solid #8a5a2b">'+
      '<div class="meta" style="margin:0 0 6px">model answers — shown before you choose, '+
      'so this judgement is recorded as not blind</div>'+
      '<div><b>Sonnet 5</b> <code>'+esc(item.models['claude-sonnet-5'])+'</code>'+
      ' &nbsp;·&nbsp; <b>Opus 5</b> <code>'+esc(item.models['claude-opus-5'])+'</code>'+
      (item.models['claude-sonnet-5']===item.models['claude-opus-5']
        ? ' — they agree' : ' — <b>they disagree</b>')+'</div></div>' : '')+
   '<div class="card"><div class="review" dir="auto">'+esc(item.text)+'</div>'+
   '<div class="meta">'+item.product_id+' · '+(item.rating??'?')+'\\u2605 · '+
   item.language_detected+'</div></div>'+
   '<div class="card"><div class="cols"><div>'+opts+
   '<div class="extras">'+
   '<label>second, genuinely separate problem<br><select id="sec">'+sec+'</select></label>'+
   '<label><input type="checkbox" id="refund"> they ask for money back</label>'+
   '<textarea id="notes" rows="2" placeholder="note (optional)"></textarea>'+
   '<button id="go" disabled onclick="save()">Confirm</button>'+
   '<button class="ghost" onclick="save(true)">Skip</button>'+
   '<button class="ghost" id="backbtn" onclick="goBack()">◀ redo an earlier one</button>'+
   '</div></div><div><div id="def"><h3>hover an intent</h3>'+
   '<p>Its definition, examples and boundary note appear here.</p></div></div>'+
   '</div></div>';
}

async function goBack(){
  const r=await (await fetch('/back?steps='+(backSteps+1))).json();
  if(!r.item){alert('No earlier judgement to redo.');return}
  backSteps=r.steps; item=r.item; prev=r.previous; render(); restore(prev);
  document.getElementById('reveal').style.display='none';
}

// Put the earlier answer back into the form so a revisit edits rather than restarts.
function restore(p){
  if(!p) return;
  const radio=document.querySelector('input[name=intent][value="'+p.human_intent+'"]');
  if(radio){radio.checked=true; pick(radio);}
  if(p.unclassifiable_reason){
    const w=document.querySelector('input[name=why][value="'+p.unclassifiable_reason+'"]');
    if(w){w.checked=true; document.getElementById('go').disabled=false;}
  }
  if(p.human_intent_secondary){
    const sec=document.getElementById('sec');
    if(sec) sec.value=p.human_intent_secondary;
  }
  document.getElementById('refund').checked=!!p.human_refund_requested;
  document.getElementById('notes').value=p.notes||'';
  const h=document.createElement('div');
  h.className='meta';
  h.style.cssText='margin-top:10px;color:#8a5a2b';
  h.textContent='revising an earlier judgement — you had chosen: '+p.human_intent;
  document.querySelector('.card').appendChild(h);
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

document.addEventListener('change', e=>{
  if(e.target.name==='why') document.getElementById('go').disabled=false;
});

function showDef(id){
  const d=document.getElementById('def');
  if(!id){d.innerHTML='<h3>none of these fit</h3><p>Use this when the review is praise, '+
    'an unreadable fragment, or about something no intent covers. Do not force it into '+
    'the nearest box.</p>';return}
  const i=TAX.intents.find(x=>x.id===id);
  d.innerHTML='<h3>'+i.id+'</h3><p>'+esc(i.definition)+'</p>'+
    i.positive_examples.map(e=>'<p class="ex" dir="auto">✓ '+esc(e)+'</p>').join('')+
    '<p class="ex no" dir="auto">✗ '+esc(i.negative_example)+'</p>'+
    '<p class="ex no">'+esc(i.negative_rationale)+'</p>';
}

function pick(el){
  document.querySelectorAll('label.opt').forEach(l=>l.classList.remove('sel'));
  el.closest('label').classList.add('sel');
  const unc = el.value==='unclassifiable';
  document.getElementById('whybox').style.display = unc?'block':'none';
  document.getElementById('go').disabled = unc && !whyValue();
  syncSecondary(el.value);
}

function whyValue(){
  const w=document.querySelector('input[name=why]:checked');
  return w?w.value:null;
}

// A secondary identical to the primary is not a second matter, so the primary is
// removed from the secondary list rather than left selectable.
function syncSecondary(primary){
  const sec=document.getElementById('sec');
  const keep=sec.value===primary?'':sec.value;
  let html='<option value="">— none —</option>';
  TAX.intents.forEach(i=>{
    if(i.id===primary) return;
    html+='<option value="'+i.id+'"'+(i.id===keep?' selected':'')+'>'+i.id+'</option>';
  });
  sec.innerHTML=html;
}

async function save(skip){
  const sel=document.querySelector('input[name=intent]:checked');
  const body={review_id:item.review_id, skipped:!!skip,
    intent: skip?null:(sel&&sel.value),
    intent_secondary: skip?null:(document.getElementById('sec').value||null),
    refund_requested: skip?null:document.getElementById('refund').checked,
    unclassifiable_reason: skip?null:whyValue(),
    notes: skip?'':document.getElementById('notes').value};
  const res=await (await fetch('/save',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
  showReveal(res, body.intent);
  backSteps=0; prev=null;
  next();
}

function showReveal(res, mine){
  const r=document.getElementById('reveal');
  if(!res.models){r.style.display='none';return}
  const a=res.models['claude-sonnet-5'], b=res.models['claude-opus-5'];
  const agreedWithMe=(a===mine)||(b===mine);
  r.className=agreedWithMe?'':'miss';
  r.style.display='block';
  r.innerHTML='you chose <b>'+(mine||'skipped')+'</b> &nbsp;·&nbsp; '+
    'Sonnet 5 <b>'+a+'</b> &nbsp;·&nbsp; Opus 5 <b>'+b+'</b>'+
    (a===b? ' &nbsp;— the models agreed here.' :
            ' &nbsp;— <b>the models disagreed.</b>');
}
boot();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    """Serve the page and record judgements; model answers stay server-side."""

    worklist: list[dict[str, Any]] = []
    taxonomy_payload: dict[str, Any] = {}
    output: Path = JUDGEMENTS
    mode: str = "normal"
    taxonomy_version: int = 0
    # When false, model predictions are sent with the item and the judgement is no longer
    # independent. Every record stores which regime produced it so the two are never
    # silently pooled in analysis.
    blind: bool = True

    def log_message(self, *_args: Any) -> None:  # keep the terminal readable
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any]) -> None:
        self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/taxonomy":
            self._json(self.taxonomy_payload)
        elif self.path.startswith("/back"):
            steps = 1
            if "?" in self.path:
                query = self.path.split("?", 1)[1]
                for part in query.split("&"):
                    if part.startswith("steps="):
                        steps = max(1, int(part.split("=", 1)[1] or 1))
            judged = []
            if self.output.exists():
                judged = [
                    json.loads(line)
                    for line in self.output.open(encoding="utf-8")
                    if line.strip()
                ]
            if steps > len(judged):
                self._json({"item": None, "steps": len(judged)})
                return
            previous = judged[-steps]
            source = next(
                (i for i in self.worklist if i["review_id"] == previous["review_id"]), None
            )
            item = (
                {k: v for k, v in source.items() if not k.startswith("_")}
                if source
                else None
            )
            self._json({"item": item, "previous": previous, "steps": steps})
        elif self.path == "/next":
            if self.mode == "revisit":
                finished = {
                    json.loads(raw)["review_id"]
                    for raw in self.output.open(encoding="utf-8")
                    if raw.strip()
                    and int(json.loads(raw).get("taxonomy_version", 0))
                    >= self.taxonomy_version
                }
            else:
                finished = done_ids(self.output)
            pending = [i for i in self.worklist if i["review_id"] not in finished]
            item = None
            if pending:
                item = {k: v for k, v in pending[0].items() if not k.startswith("_")}
                if not self.blind:
                    item["models"] = {
                        m: pending[0]["_models"][m]["intent"] for m in MODELS
                    }
            # Count progress against THIS pass's worklist, not every judgement ever
            # made - a controls or recheck pass shares its output file with the main run.
            done = len(self.worklist) - len(pending)
            self._json({"item": item, "done": done, "total": len(self.worklist)})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if self.path != "/save":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")

        source = next(
            (i for i in self.worklist if i["review_id"] == body.get("review_id")), None
        )
        if source is None:
            self._json({"models": None})
            return

        primary = body.get("intent")
        secondary = body.get("intent_secondary")
        if secondary == primary:  # not a separate second matter; record as none
            secondary = None

        record = {
            "review_id": body["review_id"],
            "human_intent": primary,
            "human_intent_secondary": secondary,
            "human_refund_requested": body.get("refund_requested"),
            # Separates "praise has no intent by design" from "the taxonomy has a hole".
            "unclassifiable_reason": (
                body.get("unclassifiable_reason") if primary == "unclassifiable" else None
            ),
            "skipped": bool(body.get("skipped")),
            "notes": body.get("notes", ""),
            "item_kind": source["_kind"],
            "blind": self.blind,
            "taxonomy_version": self.taxonomy_version,
            "v3_candidate": primary in {c[0] for c in V3_CANDIDATES},
            "models": {m: source["_models"][m]["intent"] for m in MODELS},
        }
        existing = []
        if self.output.exists():
            existing = [
                json.loads(line)
                for line in self.output.open(encoding="utf-8")
                if line.strip()
            ]
        kept = [r for r in existing if r["review_id"] != record["review_id"]]
        revised = len(kept) != len(existing)
        kept.append(record)
        self.output.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
            encoding="utf-8",
        )

        # In recheck the reveal is suppressed: seeing the model answers again could cue
        # the earlier judgement, which is exactly what the blind retest must avoid.
        payload = {"revised": revised}
        if self.mode != "recheck":
            payload["models"] = record["models"]
        self._json(payload)


def main() -> None:
    """Build the worklist and serve it on localhost until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument(
        "--mode", choices=("normal", "controls", "recheck", "urdu", "revisit"), default="normal"
    )
    parser.add_argument("--n", type=int, default=50, help="items for controls/recheck")
    parser.add_argument(
        "--show-models",
        action="store_true",
        help="show model answers before judging (records blind=false on every item)",
    )
    args = parser.parse_args()

    taxonomy = load_taxonomy(TAXONOMY)
    Handler.mode = args.mode
    Handler.taxonomy_version = int(taxonomy.version)
    Handler.blind = not args.show_models
    if args.show_models:
        print("NOT BLIND — model answers are shown before you choose.")
        print("Judgements from this run are stored with blind=false and reported")
        print("separately; they cannot be pooled with the blind ones.\n")
    Handler.output = {
        "recheck": RECHECK,
        "urdu": URDU_JUDGEMENTS,
        "revisit": URDU_JUDGEMENTS,
    }.get(args.mode, JUDGEMENTS)
    Handler.worklist = build_worklist(mode=args.mode, extra=args.n)
    Handler.taxonomy_payload = {
        "intents": [
            {
                "id": i.id,
                "family": i.family,
                "definition": i.definition.strip(),
                "positive_examples": i.positive_examples,
                "negative_example": i.negative_example,
                "negative_rationale": i.negative_rationale.strip(),
            }
            for i in taxonomy.intents
        ]
    }

    kinds = Counter(i["_kind"] for i in Handler.worklist)
    if args.mode == "recheck":
        print("BLIND RE-CHECK — your earlier answers are not shown, and no model")
        print("answers are revealed. Judge each one fresh.")
    elif args.mode == "revisit":
        print("REVISIT — items judged before the taxonomy gained the intent that may")
        print("fit them. Each one leaves this list as soon as you re-judge it, and the")
        print("update lands in the same file the main pass reads.")
    elif args.mode == "urdu":
        print("URDU PASS — fresh length-matched sample, ~60 per language form.")
        print("Model answers ARE revealed after each save; they are not the measurement here.")
    elif args.mode == "controls":
        print("CONTROLS ONLY — reviews where both models already agreed.")
    else:
        print("controls are drawn only from reviews naming something concrete; "
              "all disagreements are kept")
    finished = len(done_ids(Handler.output))
    print(f"worklist: {len(Handler.worklist)} items "
          f"({kinds['disagreement']} disagreements, {kinds['control']} controls)")
    print(f"already judged: {finished}")
    print(f"\n  open  http://127.0.0.1:{args.port}\n\nCtrl-C to stop; progress is saved.")

    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
