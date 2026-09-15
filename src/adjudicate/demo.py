"""Generate a synthetic dataset so the tool runs with no data of your own.

Real evaluation data is customer text and does not travel. Without something to open, the
only way to show the tool working is a recording of someone else's data, which is worse
than a working copy of invented data.

The label set is the project's actual taxonomy, copied into the demo directory so it is
self-contained. Only the items are fabricated: each is built from an intent's own
positive examples with amounts, durations and filler varied, then given the messiness real
reviews have - trailing question marks, "bhai" openers, dropped vowels. They are not
convincing as complaints and are not meant to be. What has to behave identically is the
interface, the passes, and every statistic, including the parts that only appear once a
cell gets thin.

Three properties are built into the fake predictions deliberately, because a demo where
everything agrees teaches the wrong lesson:

  models disagree on roughly a fifth of items, so the controls pass and the joint-error
  figure have something to measure;
  every model is wrong together on a slice of the items they agree on, which is the
  finding that inter-model agreement can never surface on its own;
  and one language form carries a real deficit, so the subgroup test has something to
  find - while the sample stays small enough that the power line still says it cannot be
  certain.
"""

from __future__ import annotations

import json
import random
import re
import shutil
from pathlib import Path

from src.adjudicate.labels import Label, load_labels

TAXONOMY = Path("config/taxonomy.yaml")
SEED = 20260901

URDU = re.compile(r"[؀-ۿ]")
# Roman Urdu has no standard orthography, so detection is a word list rather than a rule.
# It is deliberately generous: a mixed sentence belongs in roman_urdu, not english.
ROMAN_MARKERS = re.compile(
    r"\b(nahi|nhi|nai|hai|hy|hain|tha|thi|kar|kr|karo|gaya|gya|gaye|mera|meri|mujh|mujhe"
    r"|apna|apni|kya|kyun|koi|kuch|paisay|paise|pese|bohat|bht|bhi|se|pe|par|jo|ke|ki|ka"
    r"|dobara|phir|abhi|lekin|magar|raha|rha|rahe|diya|dea|liya)\b",
    re.I,
)

# Real reviews rarely arrive clean. Openers and tails are kept in the same script as the
# item, because a Latin "please help" bolted onto an Urdu complaint turns every
# urdu_script item into a code-switched one and empties the stratum being demonstrated.
FILLER = {
    "urdu_script": (("", "", "یار ", "السلام علیکم، "), ("", "", "؟؟؟", " براہ کرم مدد کریں")),
    "roman_urdu": (("", "", "bhai ", "AOA "), ("", "", " please help", " ????")),
    "code_switched": (("", "", "bhai ", "یار "), ("", "", " kindly resolve", "؟؟؟")),
    "english": (("", "", "Dear team, ", "Hi, "), ("", "", " please help", "!!!")),
}
LANGUAGES = ("urdu_script", "roman_urdu", "code_switched", "english")

# The taxonomy's own examples are mostly Roman Urdu and English, which leaves the
# Urdu-script and code-switched strata nearly empty - and a demo of a per-language
# breakdown with four items in a cell demonstrates the wrong thing. These seeds fill
# them. Invented, like everything else here.
EXTRA_SEEDS: tuple[tuple[str, str], ...] = (
    (
        "unauthorized_vas_deduction",
        "ہر ہفتے 50 روپے کٹ جاتے ہیں کسی سروس کے نام پر جو میں نے کبھی لی ہی نہیں",
    ),
    (
        "balance_disappeared_unexplained",
        "میرا بیلنس خود بخود کم ہو گیا، کوئی ٹرانزیکشن نظر نہیں آ رہی",
    ),
    ("login_failure", "درست پاسورڈ ڈالنے کے باوجود ایپ میں لاگ اِن نہیں ہو رہا"),
    ("otp_not_received", "بیس منٹ سے او ٹی پی نہیں آیا، تین بار کوشش کر چکا ہوں"),
    ("account_blocked_frozen", "میرا اکاؤنٹ بغیر کسی وجہ کے بند کر دیا گیا ہے"),
    ("transfer_failed_money_deducted", "پیسے بھیجے لیکن وصول کنندہ کو نہیں ملے، میرا بیلنس کٹ گیا"),
    ("data_speed_complaint", "فور جی ہونے کے باوجود انٹرنیٹ بہت سست چل رہا ہے"),
    ("card_activation_failed", "ڈیبٹ کارڈ منگوایا تھا، ایک مہینہ ہو گیا ابھی تک نہیں ملا"),
    ("support_unresponsive", "ہیلپ لائن پر کوئی جواب نہیں دیتا، شکایت درج کیے تین ہفتے ہو گئے"),
    (
        "unauthorized_vas_deduction",
        "ہر ہفتے Rs 50 کٹ جاتے ہیں some VAS service کے نام پر jo maine subscribe nahi kiya",
    ),
    ("login_failure", "correct password ڈالنے کے باوجود login نہیں ہو رہا"),
    ("otp_not_received", "OTP نہیں آ رہا, 20 minutes سے wait کر رہا ہوں"),
    (
        "transfer_failed_money_deducted",
        "میں نے Rs 5000 transfer کیے, balance کٹ گیا but recipient کو نہیں ملے",
    ),
    (
        "support_unresponsive",
        "helpline پر کوئی response نہیں دیتا, 3 weeks سے complaint pending ہے",
    ),
    ("account_blocked_frozen", "میرا account suddenly block ہو گیا without any reason"),
    ("kyc_verification_stuck", "CNIC verification ایک ہفتے سے pending ہے, koi update نہیں مل رہا"),
    ("data_speed_complaint", "4G ہونے کے باوجود internet بہت slow ہے"),
    ("cash_out_agent_problem", "ایجنٹ کے پاس cash out کروایا, balance کٹ گیا لیکن cash نہیں دیا"),
)

# One form is handicapped so the subgroup breakdown has a real effect to detect.
WEAK_FORM = "roman_urdu"


def detect_language(text: str) -> str:
    """Classify a string by the script it is written in."""
    has_urdu = bool(URDU.search(text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_urdu and has_latin:
        return "code_switched"
    if has_urdu:
        return "urdu_script"
    return "roman_urdu" if ROMAN_MARKERS.search(text) else "english"


def vary(text: str, language: str, rng: random.Random) -> str:
    """Reword one example so a hundred items are not a hundred copies.

    Only amounts are resampled - a number attached to a unit of time keeps its scale,
    since "contact you in 1500 hours" reads as broken rather than varied.
    """
    out = re.sub(
        r"(Rs\.?\s*|PKR\s*)(\d[\d,]*)",
        lambda m: m.group(1) + str(rng.choice((30, 50, 199, 500, 1500, 5000))),
        text,
    )
    out = re.sub(
        r"\b(\d{1,2}) (day|days|week|weeks|month|months|din|hafte|hour|hours)\b",
        lambda m: f"{rng.randint(2, 9)} {m.group(2)}",
        out,
    )
    if language in ("roman_urdu", "code_switched") and rng.random() < 0.3:
        out = out.replace("nahi", "nhi").replace("hai", "hy")
    openers, tails = FILLER[language]
    return (rng.choice(openers) + out + rng.choice(tails)).strip()


def build_items(labels: tuple[Label, ...], count: int, rng: random.Random) -> list[dict]:
    """Fabricate items from the label set's own examples, with model predictions."""
    known = {label.id for label in labels}
    seeds = [
        (label.id, example)
        for label in labels
        for example in label.positive_examples
        if example.strip()
    ]
    # Only seeds whose intent exists in this label set, so a trimmed taxonomy still works.
    seeds += [(i, text) for i, text in EXTRA_SEEDS if i in known]
    ids = [label.id for label in labels]
    rows = []

    for n in range(count):
        truth, example = seeds[n % len(seeds)]
        # Classify the source, then match the filler to it, so the stratum survives.
        language = detect_language(example)
        text = vary(example, language, rng)

        # A model that is simply weaker on one form, not on the task as a whole.
        skill = 0.58 if language == WEAK_FORM else 0.76
        first = truth if rng.random() < skill else rng.choice(ids)

        # Agreement is correlated, not independent: models share blind spots, which is
        # exactly why agreeing with each other is not evidence of being right.
        if rng.random() < 0.82:
            second = first
        else:
            second = truth if rng.random() < skill else rng.choice(ids)
        third = first if rng.random() < 0.72 else rng.choice(ids)

        rows.append(
            {
                "id": f"demo_{n:04d}",
                "text": text,
                "meta": {
                    "language": language,
                    "product": rng.choice(("wallet_a", "wallet_b", "telco_a")),
                    "rating": rng.choice((1, 1, 1, 2, 2, 3)),
                },
                "predictions": {
                    "model-alpha": first,
                    "model-beta": second,
                    "model-gamma": third,
                },
            }
        )
    return rows


def build(directory: Path, count: int = 220) -> tuple[Path, Path, Path]:
    """Write a complete demo dataset; returns items, labels and output paths."""
    directory.mkdir(parents=True, exist_ok=True)
    labels_path = directory / "demo_labels.yaml"
    shutil.copyfile(TAXONOMY, labels_path)

    rng = random.Random(SEED)
    rows = build_items(load_labels(labels_path).labels, count, rng)
    rng.shuffle(rows)

    items_path = directory / "demo_items.jsonl"
    items_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    return items_path, labels_path, directory / "demo_judgements.jsonl"
