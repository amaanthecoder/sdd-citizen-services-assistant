"""Language detection for bilingual (AR/EN) handling.

We deliberately avoid heavy dependencies (e.g. langdetect). Arabic vs. English
is easily separable by Unicode block. For mixed input we return "mixed" so
the responder can code-switch back rather than forcing one language.
"""
from __future__ import annotations


_ARABIC_RANGES = [
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
]


def _is_arabic(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _ARABIC_RANGES)


def detect_language(text: str) -> str:
    """Return 'ar', 'en', or 'mixed'."""
    if not text:
        return "en"
    ar = 0
    en = 0
    for ch in text:
        cp = ord(ch)
        if _is_arabic(cp):
            ar += 1
        elif ch.isalpha():
            en += 1
    total = ar + en
    if total == 0:
        return "en"
    ar_ratio = ar / total
    if ar_ratio > 0.75:
        return "ar"
    if ar_ratio < 0.15:
        return "en"
    return "mixed"
