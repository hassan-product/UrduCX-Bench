"""Render real-data safety checks and synthetic multilingual PII challenges."""

from __future__ import annotations

import argparse
import html
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.prep.clean import LANGUAGE_VALUES
from src.prep.scrub_pii import load_jsonl, normalize_for_matching, scrub_text

DEFAULT_INPUT = Path("data/interim/reviews_phase3_sample_scrubbed.jsonl")
DEFAULT_OUTPUT = Path("data/interim/pii_audit/index.html")
DEFAULT_TARGET_SIZE = 50
DEFAULT_SEED = 20260821

_CHALLENGE_CASES = {
    "english": {
        "phone": ("Call me at 03001234567 about ticket EN-2048.", "EN-2048"),
        "account": (
            "My account number 123456789012 has Rs 5000 missing.",
            "Rs 5000",
        ),
        "cnic": ("My CNIC is 42101-1234567-1; date is 15/01/2026.", "15/01/2026"),
        "iban": ("Use IBAN PK36SCBL0000001123456702 for case TXN-88421.", "TXN-88421"),
        "email": ("Email me at ali.khan@example.com about 2 GB data.", "2 GB"),
        "name": ("My name is Ali Khan. The disputed amount is Rs 1200.", "Rs 1200"),
    },
    "roman_urdu": {
        "phone": ("Mera phone ۰۳۰۰۱۲۳۴۵۶۷ hai, reference RU-2048 rehna chahiye.", "RU-2048"),
        "account": (
            "Mera account number ١٢٣٤٥٦٧٨٩٠١٢ hai, Rs 1200 wapis chahiye.",
            "Rs 1200",
        ),
        "cnic": ("Mera CNIC ۴۲۱۰۱-۱۲۳۴۵۶۷-۱ hai, date 15/01/2026 thi.", "15/01/2026"),
        "iban": ("Mera IBAN PK۳۶SCBL۰۰۰۰۰۰۱۱۲۳۴۵۶۷۰۲ hai, ref RU-88421 hai.", "RU-88421"),
        "email": ("Meri email sana.user@example.com hai, package 2 GB ka tha.", "2 GB"),
        "name": ("Mera naam Sana Ahmed hai, mere Rs 5000 kat gaye.", "Rs 5000"),
    },
    "urdu_script": {
        "phone": ("میرا فون ۰۳۰۰۱۲۳۴۵۶۷ ہے، حوالہ UR-2048 محفوظ رکھیں۔", "UR-2048"),
        "account": (
            "میرا اکاؤنٹ نمبر ١٢٣٤٥٦٧٨٩٠١٢ ہے، رقم ۵۰۰۰ روپے واپس کریں۔",
            "۵۰۰۰ روپے",
        ),
        "cnic": ("میرا شناختی کارڈ ۴۲۱۰۱-۱۲۳۴۵۶۷-۱ ہے، تاریخ ۱۵/۰۱/۲۰۲۶ ہے۔", "۱۵/۰۱/۲۰۲۶"),
        "iban": ("میرا IBAN PK۳۶SCBL۰۰۰۰۰۰۱۱۲۳۴۵۶۷۰۲ ہے، حوالہ UR-88421 ہے۔", "UR-88421"),
        "email": ("میری ای میل sana.user@example.com ہے، پیکج 2 GB کا تھا۔", "2 GB"),
        "name": ("میرا نام ثنا احمد ہے، میرے ۵۰۰۰ روپے کٹ گئے۔", "۵۰۰۰ روپے"),
    },
    "code_switched": {
        "phone": ("میرا callback number +923001234567 hai, ticket CS-2048 open hai.", "CS-2048"),
        "account": (
            "رقم account no 123456789012 mein bheji thi, ref CS-88421 hai.",
            "CS-88421",
        ),
        "cnic": ("میرا CNIC ۴۲۱۰۱-۱۲۳۴۵۶۷-۱ hai, verification date 15 January hai.", "15 January"),
        "iban": ("میرا IBAN PK36SCBL0000001123456702 hai, amount Rs 5000 hai.", "Rs 5000"),
        "email": ("میری email sana.user@example.com hai, data bundle 2 GB tha.", "2 GB"),
        "name": ("My name is Sana Ahmed. میرے Rs 1200 deduct ہوئے۔", "Rs 1200"),
    },
}

_EXPECTED_PLACEHOLDERS = {
    "phone": "<PHONE>",
    "account": "<ACCOUNT>",
    "cnic": "<CNIC>",
    "iban": "<IBAN>",
    "email": "<EMAIL>",
    "name": "<NAME>",
}

_PII_RISK_CUE_RE = re.compile(
    r"(?i)(?:@|\b(?:cnic|nic|iban|account|acct|phone|mobile|number|naam)\b|"
    r"شناختی|اکاؤنٹ|اکاونٹ|فون|موبائل|نمبر|نام|(?:\d[-\s]?){5,})"
)


def has_pii_risk_cue(record: dict[str, Any]) -> bool:
    """Flag unchanged records worth human review without treating them as PII."""
    text = normalize_for_matching(str(record.get("text_clean", "")))
    return bool(_PII_RISK_CUE_RE.search(text))


def build_challenge_records() -> list[dict[str, str]]:
    """Build synthetic positive cases without mixing them into source review data."""
    records = []
    for language in LANGUAGE_VALUES:
        for pii_type, (text, must_preserve) in _CHALLENGE_CASES[language].items():
            scrubbed, _ = scrub_text(text)
            records.append(
                {
                    "language": language,
                    "pii_type": pii_type,
                    "text_clean": text,
                    "text_scrubbed": scrubbed,
                    "expected_placeholder": _EXPECTED_PLACEHOLDERS[pii_type],
                    "must_preserve": must_preserve,
                }
            )
    return records


def sample_audit_records(
    records: list[dict[str, Any]],
    *,
    target_size: int = DEFAULT_TARGET_SIZE,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, Any]]:
    """Select a deterministic language-stratified audit, prioritizing changed records."""
    if target_size < len(LANGUAGE_VALUES):
        raise ValueError(f"target_size must be at least {len(LANGUAGE_VALUES)}")

    base, remainder = divmod(target_size, len(LANGUAGE_VALUES))
    quotas = {
        language: base + (index < remainder) for index, language in enumerate(LANGUAGE_VALUES)
    }
    generator = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for language in LANGUAGE_VALUES:
        candidates = [record for record in records if record.get("language") == language]
        quota = quotas[language]
        if len(candidates) < quota:
            raise ValueError(f"Need {quota} {language} records, found {len(candidates)}")
        changed = [
            record
            for record in candidates
            if record.get("text_clean") != record.get("text_scrubbed")
        ]
        high_risk = [
            record for record in candidates if record not in changed and has_pii_risk_cue(record)
        ]
        unchanged = [
            record for record in candidates if record not in changed and record not in high_risk
        ]
        generator.shuffle(changed)
        generator.shuffle(high_risk)
        generator.shuffle(unchanged)
        selected.extend((changed + high_risk + unchanged)[:quota])

    return selected


def _render_rows(
    records: list[dict[str, Any]],
    *,
    prefix: str,
    challenge: bool,
) -> str:
    """Render one provenance-specific group with independent persisted controls."""
    rows = []
    for index, record in enumerate(records, start=1):
        language = html.escape(str(record["language"]))
        original = html.escape(str(record.get("text_clean", "")))
        scrubbed = html.escape(str(record.get("text_scrubbed", "")))
        pii_type = html.escape(str(record.get("pii_type", "")))
        badge = f"<span>{language} | {pii_type}</span>" if challenge else f"<span>{language}</span>"
        privacy_label = "Expected PII removed" if challenge else "No visible residual PII"
        facts_label = "Control fact preserved" if challenge else "No useful facts destroyed"
        rows.append(
            f"""
            <article class="audit-item" data-language="{language}">
              <header><strong>Record {index}</strong>{badge}</header>
              <div class="comparison">
                <section><h3>Original local text</h3><p dir="auto">{original}</p></section>
                <section><h3>Scrubbed API text</h3><p dir="auto">{scrubbed}</p></section>
              </div>
              <footer>
                <label><input id="v2-{prefix}-privacy-{index}" type="checkbox">
                  {privacy_label}</label>
                <label><input id="v2-{prefix}-facts-{index}" type="checkbox"> {facts_label}</label>
              </footer>
            </article>"""
        )
    return "".join(rows)


def render_audit(
    records: list[dict[str, Any]],
    challenge_records: list[dict[str, Any]],
    *,
    seed: int,
) -> str:
    """Render distinct real-data and synthetic-challenge verification sections."""
    counts = Counter(str(record["language"]) for record in records)
    changed = sum(record.get("text_clean") != record.get("text_scrubbed") for record in records)
    distribution = " | ".join(f"{language}: {counts[language]}" for language in LANGUAGE_VALUES)
    total_records = len(records) + len(challenge_records)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PII scrubber audit</title>
  <style>
    :root {{ color-scheme: light; --ink: #17211b; --muted: #5c665f; --line: #c8d0ca;
      --paper: #f4f6f2; --panel: #ffffff; --accent: #176b4d; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink);
      font-family: Charter, Georgia, serif; }}
    .toolbar {{ position: sticky; top: 0; z-index: 2; padding: 16px 24px;
      border-bottom: 1px solid var(--line); background: rgba(244, 246, 242, .96); }}
    .toolbar h1 {{ margin: 0 0 6px; font-size: 24px; letter-spacing: 0; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px 20px; color: var(--muted);
      font: 14px ui-monospace, SFMono-Regular, Menlo, monospace; }}
    main {{ width: min(1400px, 100%); margin: 0 auto; padding: 20px 24px 60px; }}
    .audit-item {{ margin: 0 0 16px; border: 1px solid var(--line); border-radius: 6px;
      background: var(--panel); overflow: hidden; }}
    .audit-item > header, .audit-item > footer {{ display: flex; flex-wrap: wrap;
      justify-content: space-between; gap: 12px; padding: 10px 14px; background: #e8eee9; }}
    .audit-item > header span {{ color: var(--accent); font-weight: 700; }}
    .comparison {{ display: grid; grid-template-columns: 1fr 1fr; }}
    .comparison section {{ min-width: 0; padding: 14px; }}
    .comparison section + section {{ border-left: 1px solid var(--line); }}
    .section-heading {{ margin: 28px 0 12px; }}
    .section-heading h2 {{ margin: 0 0 6px; font-size: 22px; letter-spacing: 0; }}
    .section-heading p {{ color: var(--muted); }}
    h3 {{ margin: 0 0 8px; color: var(--muted); font: 700 12px ui-monospace,
      SFMono-Regular, Menlo, monospace; text-transform: uppercase; letter-spacing: 0; }}
    p {{ margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.55; }}
    label {{ display: inline-flex; align-items: center; gap: 7px; font-weight: 700; }}
    input {{ width: 18px; height: 18px; accent-color: var(--accent); }}
    @media (max-width: 760px) {{
      .comparison {{ grid-template-columns: 1fr; }}
      .comparison section + section {{ border-left: 0; border-top: 1px solid var(--line); }}
      main, .toolbar {{ padding-left: 14px; padding-right: 14px; }}
    }}
  </style>
</head>
<body>
  <div class="toolbar">
    <h1>PII scrubber audit</h1>
    <div class="meta"><span id="progress">0 / {total_records} complete</span>
      <span>real: {len(records)}</span><span>challenge: {len(challenge_records)}</span></div>
  </div>
  <main>
    <div class="section-heading"><h2>Synthetic multilingual challenge matrix</h2>
      <p>These challenge messages are not app-store reviews. They deliberately test phone,
      account, CNIC, IBAN, email, and explicit-name redaction in every language form.</p></div>
    {_render_rows(challenge_records, prefix="challenge", challenge=True)}
    <div class="section-heading"><h2>Real corpus safety audit</h2>
      <p>These {len(records)} real records test residual exposure and over-scrubbing. Natural
      reviews are not expected to contain every PII category. {distribution}; changed: {changed};
      seed: {seed}.</p></div>
    {_render_rows(records, prefix="real", challenge=False)}
  </main>
  <script>
    const boxes = [...document.querySelectorAll('input[type="checkbox"]')];
    const progress = document.querySelector('#progress');
    function update() {{
      boxes.forEach(box => box.checked = localStorage.getItem(box.id) === 'true');
      const complete = document.querySelectorAll('.audit-item').length -
        [...document.querySelectorAll('.audit-item')].filter(item =>
          [...item.querySelectorAll('input')].some(box => !box.checked)).length;
      progress.textContent = `${{complete}} / {total_records} complete`;
    }}
    boxes.forEach(box => box.addEventListener('change', () => {{
      localStorage.setItem(box.id, String(box.checked)); update();
    }}));
    update();
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    """Parse local PII audit options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-size", type=int, default=DEFAULT_TARGET_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> None:
    """Select the audit records and write the local inspection page."""
    args = parse_args()
    records = load_jsonl(args.input)
    selected = sample_audit_records(records, target_size=args.target_size, seed=args.seed)
    challenges = build_challenge_records()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_audit(selected, challenges, seed=args.seed), encoding="utf-8")
    counts = Counter(str(record["language"]) for record in selected)
    print(f"Wrote {len(selected)} audit records to {args.output}")
    for language in LANGUAGE_VALUES:
        print(f"  {language:16} {counts[language]}")
    print(f"Added {len(challenges)} synthetic multilingual PII challenge cases")


if __name__ == "__main__":
    main()
