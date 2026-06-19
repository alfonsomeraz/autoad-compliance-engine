"""Catalog-loading + end-to-end rule-fixture tests.

Proves the YAML catalog loads into Rule objects and that representative ads
produce the expected verdicts through the real engine — including the demo
money shot (missing lease disclosures + trim mismatch => FAIL)."""

from __future__ import annotations

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
        "FINANCE_DISCLOSURE_REQUIRED",
        "CA_SPECIFIC_VEHICLE_IDENTIFIER_REQUIRED",
        "CA_ADVERTISED_PRICE_INCLUDES_FEES_DISCLAIMER",
    } <= keys
    assert len(CATALOG) >= 12


def test_every_rule_has_a_citation():
    # A rule without a source citation is not auditable.
    assert all(r.source_citation for r in CATALOG)


def test_fully_compliant_lease_ad_passes(compliant_claims):
    result = engine.evaluate(
        CATALOG, compliant_claims, _civic_source(), jurisdiction="US-CA"
    )
    assert result.verdict is Verdict.PASS


def test_finance_ad_missing_disclosures_fails():
    # Advertises a finance monthly payment but no APR / term / down payment.
    claims = AdClaims(finance_monthly_payment=Decimal("589.00"))
    source = SourceFacts(
        vehicle={"trim": "EX-L"}, offer={"effective_price": Decimal("32750.00")}
    )
    result = engine.evaluate(CATALOG, claims, source, jurisdiction="US")
    assert result.verdict is Verdict.FAIL
    assert "FINANCE_DISCLOSURE_REQUIRED" in {f.rule_key for f in result.findings}


def test_ca_priced_ad_requires_vehicle_identifier():
    # Price matches source and trim is right, but no stock number / VIN given.
    claims = AdClaims(advertised_price=Decimal("26200.00"), trim_claimed="Sport")
    result = engine.evaluate(CATALOG, claims, _civic_source(), jurisdiction="US-CA")
    assert "CA_SPECIFIC_VEHICLE_IDENTIFIER_REQUIRED" in {
        f.rule_key for f in result.findings
    }


def test_ca_rule_does_not_fire_under_federal_jurisdiction():
    claims = AdClaims(advertised_price=Decimal("26200.00"), trim_claimed="Sport")
    result = engine.evaluate(CATALOG, claims, _civic_source(), jurisdiction="US")
    assert "CA_SPECIFIC_VEHICLE_IDENTIFIER_REQUIRED" not in {
        f.rule_key for f in result.findings
    }


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
