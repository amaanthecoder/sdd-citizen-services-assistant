"""Guardrails: prompt-injection detection and same-turn authorization gate.

These are runtime checks — the LLM's system prompt also documents them, but
the checks here are enforced regardless of what the LLM decides. If the LLM
ever tries to bypass them, the guard wins.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Prompt injection detection
# ---------------------------------------------------------------------------
# Pattern set is intentionally conservative: false positives are cheap (we
# just flag and sanitize), false negatives are what we're trying to avoid.
_INJECTION_PATTERNS = [
    r"ignore (all |previous |your |the )?(instructions|rules|prompt)",
    r"disregard (all |previous |your |the )?(instructions|rules|prompt)",
    r"you are now (a |an )?",
    r"forget (everything|all|previous)",
    r"new instructions?:",
    r"system\s*[:>]",
    r"</?system>",
    r"assistant\s*[:>]",
    r"###\s*(system|instruction)",
    # Actions an injected doc might try to trigger:
    r"\bapprove (a |the |any )?(refund|payment|transfer)",
    r"\btransfer (all |the )?(funds|money|balance)",
    r"\b(pay|refund)\s+(the\s+)?(full|entire)",
    r"jailbreak",
    r"developer mode",
    # Arabic variants
    r"تجاهل التعليمات",
    r"أنت الآن",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


@dataclass
class InjectionScan:
    detected: bool
    matches: list[str]

    @property
    def summary(self) -> str:
        return "; ".join(self.matches[:3]) if self.matches else ""


def scan_for_injection(text: str) -> InjectionScan:
    """Scan citizen-supplied text for common prompt-injection markers.

    Uses `finditer` (not `findall`) so we get the full matched span rather
    than only the sub-groups — several patterns wrap alternations in `(...)?`
    so `findall` would return empty tuples for legitimate hits.
    """
    if not text:
        return InjectionScan(False, [])
    matches = [m.group(0).strip() for m in _INJECTION_RE.finditer(text)]
    matches = [m for m in matches if m]
    return InjectionScan(bool(matches), matches)


def wrap_untrusted(text: str) -> str:
    """Wrap untrusted content in visible delimiters so the LLM knows not to
    treat any instructions inside as authoritative."""
    return (
        "<untrusted_citizen_input>\n"
        + text.replace("</untrusted_citizen_input>", "&lt;/untrusted_citizen_input&gt;")
        + "\n</untrusted_citizen_input>"
    )


# ---------------------------------------------------------------------------
# Same-turn authorization gate for pay_fine
# ---------------------------------------------------------------------------
# The rule: the current turn's user message MUST contain an explicit
# confirmation that references either the specific fine_id or an unambiguous
# affirmative alongside the amount. Vague requests like "just pay it" are
# rejected — the agent must ask a confirmation question, receive a YES, and
# only THEN call pay_fine.

_AFFIRMATIVE_EN = re.compile(
    r"\b(yes|yep|yeah|confirm(ed)?|go ahead|proceed|pay it|authorize[d]?|approve[d]?)\b",
    re.IGNORECASE,
)
_AFFIRMATIVE_AR = re.compile(r"(نعم|أكد|موافق|ادفع|أدفع|تفضل)")


@dataclass
class AuthzResult:
    allowed: bool
    reason: str


def authorize_pay_fine(
    latest_user_message: str,
    fine_id: str,
    amount_aed: float,
) -> AuthzResult:
    """Return AuthzResult(allowed=True) only if the latest user turn contains
    an explicit confirmation for THIS specific fine.

    Accepts either:
      - The fine_id appearing in the message, OR
      - An affirmative token (yes/confirm/نعم/…) AND the amount digits present.

    A bare "just pay my fine" without an affirmative or fine_id fails.
    """
    if not latest_user_message:
        return AuthzResult(False, "no user message on this turn")

    msg = latest_user_message.strip()
    mentions_fine = fine_id and fine_id.lower() in msg.lower()
    affirmative = bool(_AFFIRMATIVE_EN.search(msg) or _AFFIRMATIVE_AR.search(msg))
    mentions_amount = str(int(amount_aed)) in msg or f"{amount_aed:.2f}" in msg

    if mentions_fine and affirmative:
        return AuthzResult(True, "citizen confirmed by fine_id + affirmative")
    if affirmative and mentions_amount:
        return AuthzResult(True, "citizen confirmed by affirmative + amount")

    return AuthzResult(
        False,
        "no same-turn confirmation of this specific fine_id / amount",
    )
