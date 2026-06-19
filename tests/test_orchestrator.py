"""Validation-orchestrator tests.

Exercise the full extract -> evaluate -> verdict -> persist wiring with a stub
extractor (no API calls), against the real DB inside a rolled-back transaction.
The deterministic path and the audit-record writes are what we pin here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.llm.extraction import ExtractionResult
from app.models.claims import AdClaims
from app.models.enums import Verdict
from app.models.tables import ComplianceRun
from app.validation.orchestrator import validate_ad


def stub(claims: AdClaims):
    def _extract(ad_copy: str) -> ExtractionResult:
        return ExtractionResult(claims=claims, model_name="stub-model")

    return _extract


def test_clean_lease_ad_passes_and_writes_audit_record(
    db_session, civic, active_ruleset, compliant_claims
):
    run = validate_ad(
        db_session,
        vehicle_id=civic.id,
        copy_text="Lease the Civic Sport for $299/mo ...",
        extractor=stub(compliant_claims),
    )

    assert run.status is Verdict.PASS
    assert run.violations == []
    # The audit record is persisted with the claims + model that produced them.
    persisted = db_session.get(ComplianceRun, run.id)
    assert persisted is not None
    assert persisted.extracted_claims["trim_claimed"] == "Sport"
    assert persisted.model_versions["extraction"] == "stub-model"
    assert persisted.completed_at is not None


def test_lease_missing_disclosures_and_wrong_trim_fails_with_violations(
    db_session, civic, active_ruleset
):
    claims = AdClaims(
        lease_monthly_payment=Decimal("299.00"),
        trim_claimed="Touring",  # inventory says Sport
    )
    run = validate_ad(
        db_session,
        vehicle_id=civic.id,
        copy_text="Drive home the Civic Touring for just $299/mo!",
        extractor=stub(claims),
    )

    assert run.status is Verdict.FAIL
    fired = {v.rule_key for v in run.violations}
    assert "LEASE_DISCLOSURE_REQUIRED" in fired
    assert "ADVERTISED_TRIM_MATCHES_SOURCE" in fired


def test_low_confidence_extraction_routes_to_review(
    db_session, civic, active_ruleset, compliant_claims
):
    # Otherwise-clean ad, but the extraction is shaky => never a confident PASS.
    claims = compliant_claims.model_copy(update={"extraction_confidence": 0.2})
    run = validate_ad(
        db_session,
        vehicle_id=civic.id,
        copy_text="Civic — great price!",
        extractor=stub(claims),
    )
    assert run.status is Verdict.REQUIRES_REVIEW


def test_run_pins_to_active_ruleset_and_links_violations(
    db_session, civic, active_ruleset
):
    bad = AdClaims(lease_monthly_payment=Decimal("299.00"), trim_claimed="Touring")
    run = validate_ad(
        db_session,
        vehicle_id=civic.id,
        copy_text="Civic Touring $299/mo!",
        extractor=stub(bad),
    )
    assert run.status is Verdict.FAIL
    assert run.ruleset_version_id == active_ruleset.id
    # Each violation links to the rule row it came from.
    assert run.violations
    assert all(v.rule_id is not None for v in run.violations)


def test_unknown_vehicle_raises(db_session):
    with pytest.raises(LookupError):
        validate_ad(
            db_session,
            vehicle_id=999999,
            copy_text="anything",
            extractor=stub(AdClaims()),
        )
