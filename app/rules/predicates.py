"""The deterministic predicate vocabulary.

Predicates are pure functions over an `EvalContext` (extracted `AdClaims` +
authoritative `SourceFacts`). The engine interprets a small, fixed vocabulary —
never arbitrary code:

    claim_present, claim_equals_source, claim_within_tolerance,
    disclaimer_contains, expiration_in_future, and all/any/not combinators.

Breadth comes from more *rules*, not more predicate types. Keep this small.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.models.claims import AdClaims, SourceFacts

_LESSEE_RESPONSIBILITY_KEYWORDS = ("lessee responsib", "responsible for excess")


@dataclass
class EvalContext:
    claims: AdClaims
    source: SourceFacts


# --- claim resolvers -------------------------------------------------------
# Map a semantic claim key to a value pulled from AdClaims. Composite keys
# (e.g. "down_payment_or_amount_due_at_signing") encode trigger-term logic in
# one place. A resolver returns the value, or None when the claim is absent.

def _first(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _lessee_disclaimer(claims: AdClaims) -> str | None:
    for disclaimer in claims.disclaimers:
        lowered = disclaimer.lower()
        if any(kw in lowered for kw in _LESSEE_RESPONSIBILITY_KEYWORDS):
            return disclaimer
    return None


CLAIM_RESOLVERS: dict[str, Callable[[AdClaims], Any]] = {
    "advertised_price": lambda c: c.advertised_price,
    "advertised_trim": lambda c: c.trim_claimed,
    "apr": lambda c: c.apr,
    "lease_monthly_payment": lambda c: c.lease_monthly_payment,
    "lease_term_months": lambda c: c.lease_term_months,
    "finance_monthly_payment": lambda c: c.finance_monthly_payment,
    "finance_term_months": lambda c: c.finance_term_months,
    "expiration_date": lambda c: c.expiration_date,
    "down_payment_or_amount_due_at_signing": lambda c: _first(
        c.down_payment, c.due_at_signing
    ),
    "total_of_payments_or_apr": lambda c: _first(c.total_of_payments, c.apr),
    # A specific advertised vehicle identified by stock number or VIN.
    "vehicle_identifier": lambda c: _first(c.stock_number_claimed, c.vin_claimed),
    "lessee_responsibility_disclaimer": _lessee_disclaimer,
}


def resolve_claim(key: str, claims: AdClaims) -> Any:
    if key not in CLAIM_RESOLVERS:
        raise KeyError(f"Unknown claim key: {key!r}")
    return CLAIM_RESOLVERS[key](claims)


# --- helpers ---------------------------------------------------------------


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, str)) and len(value) == 0:
        return False
    return True


# --- predicate implementations --------------------------------------------


def _claim_present(arg: str, ctx: EvalContext) -> bool:
    return _is_present(resolve_claim(arg, ctx.claims))


def _claim_equals_source(arg: dict, ctx: EvalContext) -> bool:
    claim_value = resolve_claim(arg["claim"], ctx.claims)
    source_value = ctx.source.resolve(arg["source"])
    if claim_value is None or source_value is None:
        return False

    claim_dec = _as_decimal(claim_value)
    source_dec = _as_decimal(source_value)
    if claim_dec is not None and source_dec is not None:
        tolerance = Decimal(str(arg.get("tolerance", 0)))
        return abs(claim_dec - source_dec) <= tolerance

    # Non-numeric (e.g. trim) — case-insensitive string equality.
    return str(claim_value).strip().lower() == str(source_value).strip().lower()


def _claim_within_tolerance(arg: dict, ctx: EvalContext) -> bool:
    claim_dec = _as_decimal(resolve_claim(arg["claim"], ctx.claims))
    source_dec = _as_decimal(ctx.source.resolve(arg["source"]))
    if claim_dec is None or source_dec is None:
        return False
    tolerance = Decimal(str(arg.get("tolerance", 0)))
    return abs(claim_dec - source_dec) <= tolerance


def _disclaimer_contains(arg: str, ctx: EvalContext) -> bool:
    needle = arg.lower()
    return any(needle in d.lower() for d in ctx.claims.disclaimers)


def _expiration_in_future(arg: str, ctx: EvalContext) -> bool:
    value = resolve_claim(arg, ctx.claims)
    if not isinstance(value, date):
        return False
    return value >= date.today()


_PREDICATES: dict[str, Callable[[Any, EvalContext], bool]] = {
    "claim_present": _claim_present,
    "claim_equals_source": _claim_equals_source,
    "claim_within_tolerance": _claim_within_tolerance,
    "disclaimer_contains": _disclaimer_contains,
    "expiration_in_future": _expiration_in_future,
}


def evaluate(node: dict, ctx: EvalContext) -> bool:
    """Evaluate a predicate tree node to a bool.

    A node is a single-key dict: a combinator (all/any/not) or a predicate name
    mapped to its argument.
    """
    if len(node) != 1:
        raise ValueError(f"Predicate node must have exactly one key: {node!r}")
    (key, arg), = node.items()

    if key == "all":
        return all(evaluate(child, ctx) for child in arg)
    if key == "any":
        return any(evaluate(child, ctx) for child in arg)
    if key == "not":
        return not evaluate(arg, ctx)

    if key not in _PREDICATES:
        raise ValueError(f"Unknown predicate: {key!r}")
    return _PREDICATES[key](arg, ctx)
