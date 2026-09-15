"""Hunt the full corpus for intents the stratified sample starved.

The Phase 3 diagnostic left 3 intents with zero support and 9 more under ten. This
searches all 54,519 cleaned reviews for candidates, labels them, and reports the yield
per intent - the number that decides whether each starved intent is *rare in the sample*
or *absent from app-store reviews altogether*. Merging or dropping an intent is a
taxonomy decision; this only supplies the evidence.

Every pattern carries Urdu-script, Roman-Urdu and English forms. The diagnostic found
an English-only regex missed financial-loss complaints in Urdu script 17 times for every
1 in English, so a Latin-only hunt would answer its own question wrong.

Candidates are PII-scrubbed before any leaves the machine.
"""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv
from src.label.auto_label import (
    build_response_schema,
    build_system_prompt,
    cache_key,
    call_model,
    load_cached_label,
    write_cached_label,
)
from src.label.taxonomy import load_taxonomy
from src.prep.scrub_pii import scrub_records

CORPUS = Path("data/interim/reviews_cleaned.jsonl")
ALREADY_LABELLED = Path("spike/phase3_diag/sample_500.jsonl")
CACHE_DIR = Path("spike/phase3_diag/hunt_cache")
OUTPUT = Path("spike/phase3_diag/hunt_results.jsonl")
TAXONOMY = Path("config/taxonomy.yaml")

MODEL = "claude-sonnet-5"
PER_INTENT = 50
MIN_WORDS = 5
WORKERS = 8

# Each intent maps to signal groups. A review scores one point per group it matches;
# candidates are ranked by score, so a review hitting every group ranks above one
# hitting a single group. Single-group intents fall back to plain keyword presence.
PATTERNS: dict[str, list[str]] = {
    "otp_not_received": [
        r"\botp\b|one[\s-]?time|verification code|او ٹی پی|تصدیقی کوڈ|کوڈ",
        r"nahi a+ya|nahi mila|nahi arha|not receiv|never receiv|didn'?t (get|receive)"
        r"|نہیں آیا|نہیں آ ?رہا|نہیں ملا",
    ],
    "transfer_to_wrong_recipient": [
        r"wrong (number|account|person|recipient)|gal(a|u)t (number|numbar|account|banda)"
        r"|غلط نمبر|غلط اکاؤنٹ|غلط بندے|غلط شخص",
        r"\bsent\b|transfer|bhej|چلے گئے|بھیج",
    ],
    "fake_payment_screenshot": [
        r"\bfake\b|jaali|jali|forged|doctored|جعلی|فیک|نقلی",
        r"screen ?shot|receipt|رسید|سکرین ?شاٹ|اسکرین ?شاٹ",
    ],
    "scam_impersonation_report": [
        r"imperson|pretend|posing as|khud ko .{0,25}(officer|staff|company|employee)"
        r"|company ka (banda|aadmi|admi)|نمائندہ بن|افسر بن|عملہ بن",
        r"scam|fraud|thag|thug|دھوکہ|فراڈ|ٹھگ|جعلساز",
    ],
    "cash_out_agent_problem": [
        r"\bagent\b|retailer|dukan|shop ?keeper|ایجنٹ|دکاندار|دکان",
        r"cash ?out|withdraw|nikal|نکال|کیش ?آؤٹ|رقم نکل",
    ],
    "loan_repayment_dispute": [
        r"\bloan\b|qarz|qarza|udhaar|udhar|advance salary|قرض|ادھار",
        r"repay|instal?ment|rollover|auto.?deduct|extra charge|واپس|قسط|چارجز|سود",
    ],
    "harassment_or_abuse_via_platform": [
        r"gaali|gali (de|di)|abus|threat|harass|badtami?z|بدتمیز|گالی|دھمکی|تنگ کر|بےعزت",
    ],
    "sim_or_number_issue": [
        r"\bsim\b|port (kar|karwa|ho)|number (change|port)|سم|پورٹ|نمبر تبدیل",
    ],
    "account_compromised": [
        r"hack|unauthori[sz]ed|kisi aur ne|someone (else )?(used|logged|access|took)"
        r"|ہیک|کسی اور نے|بغیر اجازت",
    ],
    "bill_payment_not_reflected": [
        r"\bbill\b|bijli|electric|gas bill|بل|بجلی|سوئی گیس",
        r"not (show|reflect|updat|receiv|credit)|unpaid|abhi b?hi|نہیں دکھا|ادا نہیں|جمع نہیں",
    ],
    "information_request": [
        r"\?|kya h(ai|y)|kaise|kitna|kitne|how (do|can) i|what is|کیسے|کتنا|کیا ہے",
    ],
    "refund_request": [
        r"refund|wapis|wapas|return my money|واپس|رقم واپس",
    ],
}

_print_lock = threading.Lock()


def score(text: str, groups: list[re.Pattern[str]]) -> int:
    """Count how many distinct signal groups this review matches."""
    return sum(1 for group in groups if group.search(text))


def find_candidates(rows: list[dict[str, Any]], exclude: set[str]) -> dict[str, list[dict]]:
    """Rank the corpus against each starved intent's patterns."""
    compiled = {
        intent: [re.compile(p, re.I | re.UNICODE) for p in patterns]
        for intent, patterns in PATTERNS.items()
    }
    picks: dict[str, list[dict]] = {}
    for intent, groups in compiled.items():
        scored = []
        for row in rows:
            if row["review_id"] in exclude:
                continue
            text = row.get("text_clean") or ""
            if len(text.split()) < MIN_WORDS:
                continue
            hits = score(text, groups)
            if hits:
                scored.append((hits, row))
        scored.sort(key=lambda pair: -pair[0])
        picks[intent] = [row for _, row in scored[:PER_INTENT]]
    return picks


def main() -> None:
    """Search, scrub, label, and report the yield for every starved intent."""
    load_dotenv(Path(".env"))
    import os

    rows = [json.loads(line) for line in CORPUS.open(encoding="utf-8")]
    exclude = {
        json.loads(line)["review_id"] for line in ALREADY_LABELLED.open(encoding="utf-8")
    }
    print(f"corpus {len(rows):,} | already labelled {len(exclude)}")

    picks = find_candidates(rows, exclude)
    flat: list[dict[str, Any]] = []
    for intent, candidates in picks.items():
        print(f"  {intent:36s} {len(candidates):3d} candidates")
        for row in candidates:
            flat.append({**row, "hunted_for": intent})

    # PII gate: nothing leaves the machine unscrubbed.
    scrubbed, counts = scrub_records(flat)
    print(f"\nscrubbed {len(scrubbed)} candidates; redactions: {dict(counts)}")

    taxonomy = load_taxonomy(TAXONOMY)
    prompt = build_system_prompt(taxonomy)
    schema = build_response_schema(taxonomy)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def work(record: dict[str, Any]) -> dict[str, Any]:
        text = str(record.get("text_scrubbed") or record.get("text_clean") or "")
        key = cache_key(text, model=MODEL, taxonomy_version=taxonomy.version)
        cached = load_cached_label(CACHE_DIR, key)
        if cached is not None:
            return {**record, "label": cached, "status": "cached"}
        try:
            label, _, _ = call_model(
                client.messages.create,
                model=MODEL,
                system_prompt=prompt,
                review_text=text,
                response_schema=schema,
            )
        except Exception as error:  # reported, never scored as an answer (Issue 13)
            return {**record, "status": "failed", "error": str(error)[:200]}
        write_cached_label(CACHE_DIR, key, label)
        return {**record, "label": label, "status": "ok"}

    # Warm the prompt cache before fanning out.
    results = [work(scrubbed[0])]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results.extend(pool.map(work, scrubbed[1:]))

    with OUTPUT.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n{'intent hunted':36s} {'cand':>5s} {'hits':>5s} {'yield':>7s}  top confusions")
    print("-" * 100)
    verdicts = []
    for intent in PATTERNS:
        group = [r for r in results if r["hunted_for"] == intent and "label" in r]
        hits = sum(1 for r in group if r["label"]["intent"] == intent)
        others = Counter(
            r["label"]["intent"] for r in group if r["label"]["intent"] != intent
        )
        top = ", ".join(f"{k} {v}" for k, v in others.most_common(3))
        rate = hits / len(group) * 100 if group else 0.0
        print(f"{intent:36s} {len(group):5d} {hits:5d} {rate:6.1f}%  {top[:52]}")
        verdicts.append((intent, hits, rate))

    print("\nVERDICT (evidence only - the taxonomy call is the maintainer's)")
    for intent, hits, _rate in sorted(verdicts, key=lambda v: v[1]):
        # Yield is retrieval precision over the TOP-ranked candidates, not a corpus
        # rate: these 50 were the highest-scoring matches, not a random draw. It says
        # how cheaply a targeted top-up could reach the >=30 threshold, nothing more.
        if hits == 0:
            note = "ABSENT — 0 in the 50 best-matching reviews out of 54,519"
        elif hits < 5:
            note = "VESTIGIAL — real, but the best candidates are nearly dry"
        else:
            need = max(0, 30 - hits)
            note = (
                f"VIABLE — {hits}/{PER_INTENT} precision at the top of the ranking; "
                f"~{round(need / (hits / PER_INTENT)) if hits else 0} more candidates reach 30"
            )
        print(f"  {intent:36s} {hits:3d} found  {note}")

    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nlabelled {len(results) - failed} of {len(results)} ({failed} failed) -> {OUTPUT}")


if __name__ == "__main__":
    main()
