"""Catalog-loading + end-to-end rule-fixture tests.

Proves the YAML catalog loads into Rule objects and that representative ads
produce the expected verdicts through the real engine — including the demo
money shot (missing lease disclosures + trim mismatch => FAIL)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.claims import AdClaims, SourceFacts
from app.models.enums import Verdict
from app.rules import engine
from app.rules.catalog import load_catalog

CATALOG = load_catalog()


def _civic_source() -> SourceFacts:
    """Authoritative facts for the seeded 2024 Civic Sport lease."""
    return SourceFacts(
        vehicle={"trim": "Sport", "year": 2024, "make": "Honda", "model": "Civic"},
        offer={
            "effective_price": Decimal("26200.00"),
            "monthly_payment": Decimal("299.00"),
            "apr": Decimal("4.90"),
            "term_months": 36,
        },
    )


def test_catalog_loads_expected_rules():
    keys = {r.rule_key for r in CATALOG}
    assert {
        "LEASE_DISCLOSURE_REQUIRED",
        "ADVERTISED_PRICE_MATCHES_SOURCE",
        "ADVERTISED_TRIM_MATCHES_SOURCE",
        "ADVERTISED_APR_MATCHES_SOURCE",
        "OFFER_NOT_EXPIRED",
    } <= keys


def test_every_rule_has_a_citation():
    # A rule without a source citation is not auditable.
    assert all(r.source_citation for r in CATALOG)


def test_fully_compliant_lease_ad_passes():
    claims = AdClaims(
        advertised_price=Decimal("26200.00"),
        lease_monthly_payment=Decimal("299.00"),
        lease_term_months=36,
        due_at_signing=Decimal("2999.00"),
        apr=Decimal("4.90"),
        trim_claimed="Sport",
        expiration_date=date.today() + timedelta(days=20),
        disclaimers=[
            "Lessee responsible for excess wear and mileage. $2,999 due at signing.",
        ],
    )
    result = engine.evaluate(CATALOG, claims, _civic_source(), jurisdiction="US-CA")
    assert result.verdict is Verdict.PASS


def test_demo_money_shot_lease_missing_disclosures_and_wrong_trim_fails():
    # Looks polished, but: no lease disclosures and advertises the wrong trim.
    claims = AdClaims(
        lease_monthly_payment=Decimal("299.00"),
        trim_claimed="Touring",  # inventory says Sport
    )
    result = engine.evaluate(CATALOG, claims, _civic_source(), jurisdiction="US-CA")
    assert result.verdict is Verdict.FAIL
    fired = {f.rule_key for f in result.findings}
    assert "LEASE_DISCLOSURE_REQUIRED" in fired
    assert "ADVERTISED_TRIM_MATCHES_SOURCE" in fired
