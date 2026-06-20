"""Structured audit-logging tests.

Every compliance run must emit a structured event carrying its run ID and
verdict — the audit traceability the spec requires.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.llm.extraction import ExtractionResult
from app.models.claims import AdClaims
from app.validation.orchestrator import validate_ad


def stub(claims: AdClaims):
    def _extract(ad_copy: str) -> ExtractionResult:
        return ExtractionResult(claims=claims, model_name="stub-model")

    return _extract


def test_validate_emits_compliance_run_recorded_event(
    db_session, civic, active_ruleset, compliant_claims
):
    with structlog.testing.capture_logs() as logs:
        run = validate_ad(
            db_session,
            vehicle_id=civic.id,
            copy_text="ad",
            extractor=stub(compliant_claims),
        )
    events = [e for e in logs if e.get("event") == "compliance_run.recorded"]
    assert events, "expected a compliance_run.recorded audit event"
    event = events[0]
    assert event["run_id"] == run.id
    assert event["verdict"] == "PASS"
    assert "ruleset_version_id" in event


def test_failed_validation_logs_violation_count(db_session, civic, active_ruleset):
    bad = AdClaims(lease_monthly_payment=Decimal("299.00"), trim_claimed="Touring")
    with structlog.testing.capture_logs() as logs:
        validate_ad(db_session, vehicle_id=civic.id, copy_text="ad", extractor=stub(bad))
    event = next(e for e in logs if e.get("event") == "compliance_run.recorded")
    assert event["verdict"] == "FAIL"
    assert event["violations"] >= 1
