"""Keyword groups for finding reviews, deliberately not for labelling them.

Every pattern carries Urdu-script, Roman-Urdu and English forms. A Latin-only word list
misses financial-loss complaints in Urdu script roughly seventeen times for every one it
misses in English, so a monolingual pattern here would quietly hide the users the corpus
exists to represent.

These are offered as a search aid. Calling a review `otp_not_received` because it contains
the letters OTP is the shortcut the parent study exists to warn against.
"""

from __future__ import annotations

import re

TAGS: dict[str, tuple[str, str]] = {
    "money_lost": (
        "money deducted or missing",
        r"\b(deduct|deducted|debited|kat gaya|kat gaye|kaat|katay|cut ho|missing|gayab"
        r"|balance kam|paisay|paise|pese)\b|کٹ (گیا|گئے)|بیلنس کم|پیسے (کٹ|غائب)",
    ),
    "transfer": (
        "transfers and payments",
        r"\b(transfer|send money|bheja|bhejay|receive nahi|nahi pohanch|not credited"
        r"|ibft|raast)\b|ٹرانسفر|رقم بھیج|موصول نہیں",
    ),
    "otp": (
        "OTP and verification codes",
        r"\b(otp|one[\s-]?time|verification code|code nahi|pin code)\b|او ٹی پی|تصدیقی کوڈ",
    ),
    "login": (
        "sign-in and access",
        r"\b(login|log in|sign in|password|passcode|cannot access|access nahi)\b"
        r"|لاگ ان|پاسورڈ|رسائی نہیں",
    ),
    "blocked": (
        "blocked or frozen accounts",
        r"\b(block|blocked|freeze|frozen|suspend|band kar|bandh)\b|بلاک|بند کر|منجمد",
    ),
    "kyc": (
        "KYC and CNIC verification",
        r"\b(kyc|cnic|nadra|verif|document|upgrade)\b|کے وائی سی|شناختی کارڈ|تصدیق",
    ),
    "card": (
        "debit, credit and virtual cards",
        r"\b(debit|credit|visa|master ?card|atm card|virtual card|card)\b|کارڈ|ڈیبٹ",
    ),
    "fraud": (
        "fraud, scam and impersonation",
        r"\b(fraud|scam|thag|thug|cheat|dhoka|hack|hacked|unauthori[sz]ed)\b"
        r"|فراڈ|دھوکہ|ٹھگ|ہیک|جعلساز",
    ),
    "agent": (
        "agents, retailers and cash-out",
        r"\b(agent|retailer|shop ?keeper|dukan|cash ?out|withdraw|nikal)\b"
        r"|ایجنٹ|دکاندار|کیش آؤٹ|نکال",
    ),
    "support": (
        "unanswered support",
        r"\b(helpline|help ?line|customer (care|support|service)|complain|no (response|reply)"
        r"|jawab nahi|response nahi|koi response)\b|ہیلپ ?لائن|جواب نہیں|رسپانس نہیں",
    ),
    "network": (
        "signal, data and outages",
        r"\b(signal|network|coverage|internet|4g|5g|slow|down|outage|maintenance)\b"
        r"|سگنل|نیٹ ورک|انٹرنیٹ|سست|بند ہے",
    ),
    "bill": (
        "bill payments",
        r"\b(bill|bijli|electric|gas bill|sui gas|utility)\b|بل|بجلی|سوئی گیس",
    ),
    "loan": (
        "loans and instalments",
        r"\b(loan|qarz|qarza|udhaar|udhar|instal?ment|advance)\b|قرض|ادھار|قسط",
    ),
    "switching": (
        "mentions leaving for a rival",
        r"\b(switch|shift|uninstall|delete|better than|instead of|chhor|chor diya"
        r"|band kar diya)\b|چھوڑ|ان انسٹال|بہتر ہے",
    ),
}

COMPILED: dict[str, re.Pattern[str]] = {
    tag: re.compile(pattern, re.I | re.UNICODE) for tag, (_, pattern) in TAGS.items()
}


def matches(tag: str, text: str) -> bool:
    """Whether a review contains this keyword group."""
    pattern = COMPILED.get(tag)
    return bool(pattern and pattern.search(text or ""))


def describe() -> list[dict[str, str]]:
    """Tag ids with their human descriptions, for the interface."""
    return [{"id": tag, "label": label} for tag, (label, _) in TAGS.items()]
