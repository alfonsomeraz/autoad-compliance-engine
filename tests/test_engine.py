"""Rule-engine tests: verdict logic + findings, over (AdClaims, SourceFacts).

The engine is the deterministic heart — no LLM, no flakiness. These tests pin
the PASS / FAIL / REQUIRES_REVIEW logic and that findings carry evidence.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.claims import AdClaims, SourceFacts
from app.models.enums import Severity, Verdict
from app.rules import engine
from app.rules.schema import RuleSpec

PRICE_RULE = RuleSpec(
    rule_key="ADVERTISED_PRICE_MATCHES_SOURCE",
    severity=Severity.BLOCKER,
    applies_when={"claim_present": "advertised_price"},
    requirement={
        "claim_equals_source": {
            "claim": "advertised_price",
            "source": "offer.effective_price",
            "tolerance": 0,
        }
    },
)

EXPIRY_RULE = RuleSpec(
    rule_key="OFFER_NOT_EXPIRED",
    severity=Severity.WARNING,
    applies_when={"claim_present": "expiration_date"},
    requirement={"expiration_in_future": "expiration_date"},
)


def source(price="26200"):
    return SourceFacts(offer={"effective_price": Decimal(price)})


def test_clean_ad_passes():
    claims = AdClaims(advertised_price=Decimal("26200"))
    result = engine.evaluate([PRICE_RULE], claims, source())
    assert result.verdict is Verdict.PASS
    assert result.findings == []


def test_blocker_violation_fails():
    claims = AdClaims(advertised_price=Decimal("19999"))
    result = engine.evaluate([PRICE_RULE], claims, source())
    assert result.verdict is Verdict.FAIL
    assert len(result.findings) == 1
    assert result.findings[0].rule_key == "ADVERTISED_PRICE_MATCHES_SOURCE"
    assert result.findings[0].severity is Severity.BLOCKER


def test_warning_only_requires_review():
    claims = AdClaims(expiration_date=date.today() - timedelta(days=1))
    result = engine.evaluate([EXPIRY_RULE], claims, source())
    assert result.verdict is Verdict.REQUIRES_REVIEW
    assert result.findings[0].severity is Severity.WARNING


def test_rule_does_not_fire_when_applies_when_false():
    # No advertised_price claim => price rule never applies => clean PASS.
    claims = AdClaims(trim_claimed="Sport")
    result = engine.evaluate([PRICE_RULE], claims, source())
    assert result.verdict is Verdict.PASS
    assert result.findings == []


def test_low_confidence_extraction_forces_review_even_when_clean():
    claims = AdClaims(advertised_price=Decimal("26200"), extraction_confidence=0.2)
    result = engine.evaluate([PRICE_RULE], claims, source())
    assert result.verdict is Verdict.REQUIRES_REVIEW
    assert result.low_confidence is True


def test_blocker_dominates_low_confidence():
    claims = AdClaims(advertised_price=Decimal("1"), extraction_confidence=0.1)
    result = engine.evaluate([PRICE_RULE], claims, source())
    assert result.verdict is Verdict.FAIL


def test_finding_carries_evidence():
    claims = AdClaims(advertised_price=Decimal("19999"))
    result = engine.evaluate([PRICE_RULE], claims, source())
    evidence = result.findings[0].evidence
    # Evidence ties the claim to the source fact for the audit trail.
    assert "claim" in evidence or "advertised_price" in str(evidence)


def test_jurisdiction_filter_skips_inapplicable_rules():
    ca_rule = RuleSpec(
        rule_key="CA_ONLY_RULE",
        jurisdiction="US-CA",
        severity=Severity.BLOCKER,
        applies_when={"claim_present": "advertised_price"},
        requirement={"claim_present": "trim_claimed"},  # would fail if it fired
    )
    claims = AdClaims(advertised_price=Decimal("26200"))
    # Target jurisdiction US (federal only) => the CA rule must not fire.
    result = engine.evaluate([ca_rule], claims, source(), jurisdiction="US")
    assert result.verdict is Verdict.PASS


def test_federal_rule_applies_in_substate_jurisdiction():
    claims = AdClaims(advertised_price=Decimal("19999"))
    result = engine.evaluate([PRICE_RULE], claims, source(), jurisdiction="US-CA")
    assert result.verdict is Verdict.FAIL
