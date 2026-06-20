"""Predicate-library tests. The predicates are pure functions over
(AdClaims, SourceFacts); these tests pin every predicate and combinator."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.claims import AdClaims, SourceFacts
from app.rules import predicates
from app.rules.predicates import EvalContext


def ctx(claims: AdClaims, **source) -> EvalContext:
    return EvalContext(claims=claims, source=SourceFacts(**source))


# --- claim_present ---------------------------------------------------------


def test_claim_present_true_when_field_set():
    c = ctx(AdClaims(advertised_price=Decimal("26200")))
    assert predicates.evaluate({"claim_present": "advertised_price"}, c) is True


def test_claim_present_false_when_field_absent():
    c = ctx(AdClaims())
    assert predicates.evaluate({"claim_present": "advertised_price"}, c) is False


def test_claim_present_false_for_empty_disclaimer_list():
    c = ctx(AdClaims(disclaimers=[]))
    assert predicates.evaluate({"claim_present": "lessee_responsibility_disclaimer"}, c) is False


def test_composite_claim_due_at_signing_or_down_payment():
    c = ctx(AdClaims(due_at_signing=Decimal("2999")))
    assert (
        predicates.evaluate({"claim_present": "down_payment_or_amount_due_at_signing"}, c) is True
    )


def test_finance_monthly_payment_present():
    c = ctx(AdClaims(finance_monthly_payment=Decimal("589")))
    assert predicates.evaluate({"claim_present": "finance_monthly_payment"}, c) is True


def test_vehicle_identifier_present_via_stock_number():
    c = ctx(AdClaims(stock_number_claimed="H24001"))
    assert predicates.evaluate({"claim_present": "vehicle_identifier"}, c) is True


def test_vehicle_identifier_present_via_vin():
    c = ctx(AdClaims(vin_claimed="1HGCM82633A000001"))
    assert predicates.evaluate({"claim_present": "vehicle_identifier"}, c) is True


def test_vehicle_identifier_absent():
    c = ctx(AdClaims(advertised_price=Decimal("26200")))
    assert predicates.evaluate({"claim_present": "vehicle_identifier"}, c) is False


def test_lessee_responsibility_disclaimer_detected_by_keyword():
    c = ctx(AdClaims(disclaimers=["Lessee responsible for excess wear and mileage charges."]))
    assert predicates.evaluate({"claim_present": "lessee_responsibility_disclaimer"}, c) is True


# --- claim_equals_source ---------------------------------------------------


def test_claim_equals_source_numeric_match():
    c = ctx(
        AdClaims(advertised_price=Decimal("26200")),
        offer={"effective_price": Decimal("26200")},
    )
    node = {
        "claim_equals_source": {
            "claim": "advertised_price",
            "source": "offer.effective_price",
            "tolerance": 0,
        }
    }
    assert predicates.evaluate(node, c) is True


def test_claim_equals_source_numeric_mismatch():
    c = ctx(
        AdClaims(advertised_price=Decimal("24999")),
        offer={"effective_price": Decimal("26200")},
    )
    node = {
        "claim_equals_source": {
            "claim": "advertised_price",
            "source": "offer.effective_price",
            "tolerance": 0,
        }
    }
    assert predicates.evaluate(node, c) is False


def test_claim_equals_source_string_trim_match_case_insensitive():
    c = ctx(AdClaims(trim_claimed="sport"), vehicle={"trim": "Sport"})
    node = {"claim_equals_source": {"claim": "advertised_trim", "source": "vehicle.trim"}}
    assert predicates.evaluate(node, c) is True


def test_claim_equals_source_false_when_source_missing():
    c = ctx(AdClaims(advertised_price=Decimal("26200")))
    node = {
        "claim_equals_source": {
            "claim": "advertised_price",
            "source": "offer.effective_price",
        }
    }
    assert predicates.evaluate(node, c) is False


# --- claim_within_tolerance ------------------------------------------------


def test_claim_within_tolerance_passes_inside_band():
    c = ctx(AdClaims(apr=Decimal("4.91")), offer={"apr": Decimal("4.90")})
    node = {
        "claim_within_tolerance": {
            "claim": "apr",
            "source": "offer.apr",
            "tolerance": 0.05,
        }
    }
    assert predicates.evaluate(node, c) is True


def test_claim_within_tolerance_fails_outside_band():
    c = ctx(AdClaims(apr=Decimal("5.90")), offer={"apr": Decimal("4.90")})
    node = {
        "claim_within_tolerance": {
            "claim": "apr",
            "source": "offer.apr",
            "tolerance": 0.05,
        }
    }
    assert predicates.evaluate(node, c) is False


# --- disclaimer_contains ---------------------------------------------------


def test_disclaimer_contains_matches_substring_case_insensitive():
    c = ctx(AdClaims(disclaimers=["Offer expires 6/30. APR financing available."]))
    assert predicates.evaluate({"disclaimer_contains": "apr financing"}, c) is True


def test_disclaimer_contains_false_when_absent():
    c = ctx(AdClaims(disclaimers=["Offer expires 6/30."]))
    assert predicates.evaluate({"disclaimer_contains": "apr financing"}, c) is False


# --- expiration_in_future --------------------------------------------------


def test_expiration_in_future_true_for_future_date():
    c = ctx(AdClaims(expiration_date=date.today() + timedelta(days=10)))
    assert predicates.evaluate({"expiration_in_future": "expiration_date"}, c) is True


def test_expiration_in_future_false_for_past_date():
    c = ctx(AdClaims(expiration_date=date.today() - timedelta(days=1)))
    assert predicates.evaluate({"expiration_in_future": "expiration_date"}, c) is False


# --- combinators -----------------------------------------------------------


def test_all_combinator_requires_every_child():
    c = ctx(AdClaims(advertised_price=Decimal("100"), apr=Decimal("4.9")))
    node = {"all": [{"claim_present": "advertised_price"}, {"claim_present": "apr"}]}
    assert predicates.evaluate(node, c) is True
    node_fail = {
        "all": [
            {"claim_present": "advertised_price"},
            {"claim_present": "advertised_trim"},
        ]
    }
    assert predicates.evaluate(node_fail, c) is False


def test_any_combinator_requires_one_child():
    c = ctx(AdClaims(apr=Decimal("4.9")))
    node = {"any": [{"claim_present": "advertised_price"}, {"claim_present": "apr"}]}
    assert predicates.evaluate(node, c) is True


def test_not_combinator_inverts():
    c = ctx(AdClaims())
    assert predicates.evaluate({"not": {"claim_present": "apr"}}, c) is True
