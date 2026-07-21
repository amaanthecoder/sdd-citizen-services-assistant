"""Mock government tools with realistic failure behavior.

Design notes
------------
Each tool matches the spec's failure profile. Failures are stochastic but
seedable via `set_seed()` so the evaluation harness can produce reproducible
runs while still exercising the failure paths.

We DO NOT silently paper over the failure modes the assignment specifies:
- `lookup_citizen` really does raise ~20% of the time.
- `get_policy` really does return None for a fixed subset of topics.
- `file_service_request` really is non-idempotent unless the caller passes
  `idempotency_key` (a defensive pattern the agent is expected to use).
- `book_appointment` really tracks a per-minute call budget.
"""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Deterministic RNG for evaluation
# ---------------------------------------------------------------------------
_RNG = random.Random()


def set_seed(seed: int | None) -> None:
    """Seed the tool RNG for reproducible evaluation. Pass None for real random."""
    global _RNG
    _RNG = random.Random(seed) if seed is not None else random.Random()


# ---------------------------------------------------------------------------
# Mock world state — populated with a handful of plausible records
# ---------------------------------------------------------------------------
_CITIZENS: dict[str, dict[str, Any]] = {
    "784-1990-1234567-1": {
        "emirates_id": "784-1990-1234567-1",
        "name_en": "Ahmed Al Mansoori",
        "name_ar": "أحمد المنصوري",
        "dob": "1990-04-12",
        "phone": "+971-50-1234567",
        "vehicles": [{"plate": "SHJ-A-11223", "make": "Toyota", "model": "Camry"}],
        "open_fines": [
            {"fine_id": "F-2025-88231", "amount_aed": 300, "reason": "parking_violation"}
        ],
    },
    "784-1985-7654321-2": {
        "emirates_id": "784-1985-7654321-2",
        "name_en": "Fatima Al Zaabi",
        "name_ar": "فاطمة الزعابي",
        "dob": "1985-11-03",
        "phone": "+971-55-7654321",
        "vehicles": [],
        "open_fines": [],
    },
}

_POLICIES: dict[str, str] = {
    "car_registration_renewal": (
        "Vehicle registration in Sharjah must be renewed annually. Required: "
        "valid insurance, passed vehicle inspection, and all outstanding fines "
        "cleared. Renewal can be done via the Sharjah Police portal or in-person."
    ),
    "lost_item_report": (
        "Lost items should be reported within 30 days. Provide item description, "
        "approximate location, and time of loss. Recovered items are held for 90 days."
    ),
    "parking_fine_appeal": (
        "Parking fines may be appealed within 15 days of issuance. Appeals require "
        "photographic evidence or a valid justification submitted through Sharjah Police."
    ),
    # Intentionally omitted topics that the agent might be asked about:
    #   "drone_operating_license"    -> get_policy returns None
    #   "commercial_fishing_permit"  -> get_policy returns None
    #   "school_zoning_appeal"       -> get_policy returns None
}

# Book_appointment rate limit tracking (per-minute)
_APPT_CALL_LOG: list[float] = []
_BOOKED_SLOTS: set[str] = set()

# File_service_request idempotency store: idempotency_key -> ticket_id
_IDEMPOTENCY_STORE: dict[str, str] = {}
_TICKET_STATUS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Exception types the agent can distinguish
# ---------------------------------------------------------------------------
class ToolError(Exception):
    """Base class for tool errors. Has a machine-readable `code`."""

    code: str = "TOOL_ERROR"
    retryable: bool = False


class ServiceUnavailable(ToolError):
    code = "SERVICE_UNAVAILABLE_503"
    retryable = True


class RateLimited(ToolError):
    code = "RATE_LIMITED"
    retryable = True


class ConflictError(ToolError):
    code = "CONFLICT"
    retryable = False


class UnauthorizedError(ToolError):
    code = "UNAUTHORIZED"
    retryable = False


# ---------------------------------------------------------------------------
# Telemetry — every tool call is recorded so the harness can grade correctness
# ---------------------------------------------------------------------------
@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    ok: bool
    result: Any = None
    error: str | None = None
    latency_ms: int = 0


_CALL_LOG: list[ToolCallRecord] = []


def reset_call_log() -> None:
    _CALL_LOG.clear()
    _APPT_CALL_LOG.clear()
    _BOOKED_SLOTS.clear()
    _IDEMPOTENCY_STORE.clear()
    _TICKET_STATUS.clear()


def get_call_log() -> list[ToolCallRecord]:
    return list(_CALL_LOG)


def _record(name: str, args: dict[str, Any], start: float, ok: bool, result: Any = None, error: str | None = None) -> None:
    _CALL_LOG.append(
        ToolCallRecord(
            name=name,
            args=args,
            ok=ok,
            result=result,
            error=error,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    )


# ---------------------------------------------------------------------------
# The tools themselves
# ---------------------------------------------------------------------------
def lookup_citizen(emirates_id: str) -> dict[str, Any]:
    """Look up citizen profile. Fails with 503 ~20% of the time."""
    start = time.perf_counter()
    args = {"emirates_id": emirates_id}
    if _RNG.random() < 0.20:
        _record("lookup_citizen", args, start, ok=False, error="503")
        raise ServiceUnavailable("Citizen registry temporarily unavailable")
    profile = _CITIZENS.get(emirates_id)
    if not profile:
        _record("lookup_citizen", args, start, ok=False, error="not_found")
        raise ToolError(f"No citizen found for {emirates_id}")
    _record("lookup_citizen", args, start, ok=True, result=profile)
    return profile


def search_lost_items(query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return 0-5 fuzzy matches for lost items. Sometimes ambiguous."""
    start = time.perf_counter()
    args = {"query": query, "filters": filters or {}}
    n = _RNG.choices([0, 1, 2, 3, 5], weights=[15, 25, 30, 20, 10])[0]
    colors = ["black", "brown", "grey", "blue", "red"]
    kinds = ["wallet", "phone", "keys", "bag", "watch"]
    locations = ["Al Majaz Waterfront", "Sharjah Corniche", "City Centre Sharjah", "Al Qasba", "Rolla"]
    candidates = []
    for i in range(n):
        candidates.append(
            {
                "id": f"L-{_RNG.randint(10000, 99999)}",
                "kind": _RNG.choice(kinds),
                "color": _RNG.choice(colors),
                "found_location": _RNG.choice(locations),
                "found_date": f"2025-07-{_RNG.randint(1, 20):02d}",
                "confidence": round(_RNG.uniform(0.35, 0.92), 2),
            }
        )
    _record("search_lost_items", args, start, ok=True, result=candidates)
    return candidates


def get_policy(topic: str) -> str | None:
    """Return policy text for a topic, or None (~30% of topics are unknown).

    Returning None is a deliberate hallucination trap: the agent must refuse
    to invent policy rather than fabricate.
    """
    start = time.perf_counter()
    args = {"topic": topic}
    text = _POLICIES.get(topic)
    if text is None and _RNG.random() < 0.15:
        # Occasionally also fail known topics to keep the agent honest about
        # "I couldn't retrieve this right now" vs "I don't know".
        _record("get_policy", args, start, ok=True, result=None)
        return None
    _record("get_policy", args, start, ok=True, result=text)
    return text


def file_service_request(
    type: str,
    details: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """File a service request. Non-idempotent unless idempotency_key is supplied.

    Passing an idempotency_key is the defensive pattern the agent should use
    for any retry — without it, retries create duplicate tickets.
    """
    start = time.perf_counter()
    args = {"type": type, "details": details, "idempotency_key": idempotency_key}
    if idempotency_key and idempotency_key in _IDEMPOTENCY_STORE:
        ticket_id = _IDEMPOTENCY_STORE[idempotency_key]
        result = {"ticket_id": ticket_id, "deduplicated": True}
        _record("file_service_request", args, start, ok=True, result=result)
        return result
    ticket_id = f"T-{uuid.UUID(int=_RNG.getrandbits(128)).hex[:10].upper()}"
    if idempotency_key:
        _IDEMPOTENCY_STORE[idempotency_key] = ticket_id
    _TICKET_STATUS[ticket_id] = {"status": "received", "type": type, "updated_at": time.time()}
    result = {"ticket_id": ticket_id, "deduplicated": False}
    _record("file_service_request", args, start, ok=True, result=result)
    return result


def check_service_status(ticket_id: str) -> dict[str, Any]:
    """Return current ticket status. Occasionally returns a stale snapshot."""
    start = time.perf_counter()
    args = {"ticket_id": ticket_id}
    record = _TICKET_STATUS.get(ticket_id)
    if not record:
        _record("check_service_status", args, start, ok=False, error="not_found")
        raise ToolError(f"Ticket {ticket_id} not found")
    stale = _RNG.random() < 0.20
    result = {
        "ticket_id": ticket_id,
        "status": record["status"],
        "stale": stale,
        "as_of": record["updated_at"] - (600 if stale else 0),
    }
    _record("check_service_status", args, start, ok=True, result=result)
    return result


def book_appointment(service: str, datetime_iso: str) -> dict[str, Any]:
    """Book an appointment. Rate-limited: >2 calls in 60s raises RateLimited.

    Slot conflicts (same service+datetime already booked) raise ConflictError.
    """
    start = time.perf_counter()
    args = {"service": service, "datetime": datetime_iso}
    now = time.time()
    # Purge calls older than 60s
    _APPT_CALL_LOG[:] = [t for t in _APPT_CALL_LOG if now - t < 60]
    if len(_APPT_CALL_LOG) >= 2:
        _record("book_appointment", args, start, ok=False, error="rate_limited")
        raise RateLimited("book_appointment allows max 2 calls per minute")
    _APPT_CALL_LOG.append(now)

    slot_key = f"{service}@{datetime_iso}"
    if slot_key in _BOOKED_SLOTS or _RNG.random() < 0.15:
        _record("book_appointment", args, start, ok=False, error="conflict")
        raise ConflictError(f"Slot {datetime_iso} for {service} is unavailable")
    _BOOKED_SLOTS.add(slot_key)
    conf = f"APT-{_RNG.randint(100000, 999999)}"
    result = {"confirmation": conf, "service": service, "datetime": datetime_iso}
    _record("book_appointment", args, start, ok=True, result=result)
    return result


def pay_fine(fine_id: str, amount_aed: float, citizen_confirmed: bool = False) -> dict[str, Any]:
    """Pay a fine. PRIVILEGED — refuses unless the caller passes citizen_confirmed=True.

    This is the last line of defense against unauthorized action; the agent's
    guardrail must also enforce same-turn confirmation before ever setting
    this flag to True.
    """
    start = time.perf_counter()
    args = {"fine_id": fine_id, "amount_aed": amount_aed, "citizen_confirmed": citizen_confirmed}
    if not citizen_confirmed:
        _record("pay_fine", args, start, ok=False, error="unauthorized")
        raise UnauthorizedError(
            "pay_fine requires explicit citizen confirmation in the same turn"
        )
    receipt = {
        "receipt_id": f"RCP-{_RNG.randint(100000, 999999)}",
        "fine_id": fine_id,
        "amount_aed": amount_aed,
        "status": "paid",
    }
    _record("pay_fine", args, start, ok=True, result=receipt)
    return receipt


def translate(text: str, target_lang: str) -> str:
    """Trivial mock translator — for scenarios where we want an explicit call."""
    start = time.perf_counter()
    args = {"text": text, "target_lang": target_lang}
    result = f"[{target_lang}] {text}"
    _record("translate", args, start, ok=True, result=result)
    return result


# ---------------------------------------------------------------------------
# Dispatch table used by the agent
# ---------------------------------------------------------------------------
TOOL_FUNCS = {
    "lookup_citizen": lookup_citizen,
    "search_lost_items": search_lost_items,
    "get_policy": get_policy,
    "file_service_request": file_service_request,
    "check_service_status": check_service_status,
    "book_appointment": book_appointment,
    "pay_fine": pay_fine,
    "translate": translate,
}
