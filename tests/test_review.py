"""Review-queue service tests.

The queue surfaces runs needing a human decision; decisions (approve/reject/
override) are logged to review_decision and never mutate the immutable
deterministic verdict on the run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.llm.extraction import ExtractionResult
from app.models.claims import AdClaims
from app.models.enums import ReviewDecisionType, Verdict
from app.review import service
from app.validation.orchestrator import validate_ad


def stub(claims: AdClaims):
    def _extract(ad_copy: str) -> ExtractionResult:
        return ExtractionResult(claims=claims, model_name="stub-model")

    return _extract


def _make_run(db, civic, claims):
    return validate_ad(
        db, vehicle_id=civic.id, copy_text="ad", extractor=stub(claims)
    )


def test_queue_lists_only_requires_review(
    db_session, civic, active_ruleset, compliant_claims
):
    review_run = _make_run(
        db_session, civic, compliant_claims.model_copy(update={"extraction_confidence": 0.2})
    )
    _make_run(db_session, civic, compliant_claims)  # a clean PASS run

    queued = service.list_runs(db_session, status=Verdict.REQUIRES_REVIEW)
    ids = {r.id for r in queued}
    assert review_run.id in ids
    assert all(r.status is Verdict.REQUIRES_REVIEW for r in queued)


def test_get_run_detail_exposes_violations(db_session, civic, active_ruleset):
    bad = AdClaims(lease_monthly_payment=Decimal("299.00"), trim_claimed="Touring")
    run = _make_run(db_session, civic, bad)
    detail = service.get_run(db_session, run.id)
    assert detail.id == run.id
    assert any(v.rule_key == "ADVERTISED_TRIM_MATCHES_SOURCE" for v in detail.violations)


def test_record_decision_logs_and_preserves_verdict(
    db_session, civic, active_ruleset, compliant_claims
):
    run = _make_run(
        db_session, civic, compliant_claims.model_copy(update={"extraction_confidence": 0.2})
    )
    assert run.status is Verdict.REQUIRES_REVIEW

    decision = service.record_decision(
        db_session,
        run.id,
        reviewer="jane@dealer.com",
        decision=ReviewDecisionType.APPROVE,
        notes="Looks fine on manual check.",
    )
    assert decision.id is not None
    # The deterministic verdict is immutable; the human action is logged alongside.
    refreshed = service.get_run(db_session, run.id)
    assert refreshed.status is Verdict.REQUIRES_REVIEW
    assert len(refreshed.review_decisions) == 1
    assert refreshed.review_decisions[0].decision is ReviewDecisionType.APPROVE


def test_override_is_logged(db_session, civic, active_ruleset):
    bad = AdClaims(lease_monthly_payment=Decimal("299.00"), trim_claimed="Touring")
    run = _make_run(db_session, civic, bad)
    service.record_decision(
        db_session, run.id, reviewer="mgr@dealer.com",
        decision=ReviewDecisionType.OVERRIDE, notes="Approved by legal.",
    )
    refreshed = service.get_run(db_session, run.id)
    assert refreshed.review_decisions[0].decision is ReviewDecisionType.OVERRIDE


def test_decision_on_unknown_run_raises(db_session):
    with pytest.raises(LookupError):
        service.record_decision(
            db_session, 999999, reviewer="x", decision=ReviewDecisionType.APPROVE
        )
