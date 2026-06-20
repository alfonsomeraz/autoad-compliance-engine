"""Generation self-correct loop tests.

generate -> extract -> evaluate; on FAIL, feed the violations back and
regenerate (up to max_attempts). Exercised with stub generator + extractor so
no API calls are made; the loop logic and persistence are what we pin.
"""

from __future__ import annotations

from decimal import Decimal

from app.generation.agent import GeneratedCopyResult
from app.generation.service import generate_compliant_ad
from app.llm.extraction import ExtractionResult
from app.models.claims import AdClaims
from app.models.enums import Verdict
from app.models.tables import AdAsset, ComplianceRun

BAD = "BAD COPY"
GOOD = "GOOD COPY"

_bad_claims = AdClaims(lease_monthly_payment=Decimal("299.00"), trim_claimed="Touring")


def gen_fixed(text: str):
    def _g(source, channel, feedback):
        return GeneratedCopyResult(copy_text=text, model_name="gen-model")

    return _g


def gen_feedback_aware():
    """Returns BAD until given feedback, then GOOD — models self-correction."""

    def _g(source, channel, feedback):
        return GeneratedCopyResult(copy_text=GOOD if feedback else BAD, model_name="gen-model")

    return _g


def extractor_map(mapping: dict[str, AdClaims]):
    def _e(copy_text: str) -> ExtractionResult:
        return ExtractionResult(claims=mapping[copy_text], model_name="ext-model")

    return _e


def test_generates_compliant_ad_in_one_shot(db_session, civic, active_ruleset, compliant_claims):
    outcome = generate_compliant_ad(
        db_session,
        vehicle_id=civic.id,
        generator=gen_fixed(GOOD),
        extractor=extractor_map({GOOD: compliant_claims}),
    )
    assert outcome.verdict is Verdict.PASS
    assert outcome.attempts == 1
    assert outcome.copy_text == GOOD


def test_self_corrects_after_a_failed_attempt(db_session, civic, active_ruleset, compliant_claims):
    outcome = generate_compliant_ad(
        db_session,
        vehicle_id=civic.id,
        generator=gen_feedback_aware(),
        extractor=extractor_map({BAD: _bad_claims, GOOD: compliant_claims}),
        max_attempts=3,
    )
    assert outcome.verdict is Verdict.PASS
    assert outcome.attempts == 2
    assert outcome.copy_text == GOOD


def test_gives_up_after_max_attempts_and_persists_fail(db_session, civic, active_ruleset):
    outcome = generate_compliant_ad(
        db_session,
        vehicle_id=civic.id,
        generator=gen_fixed(BAD),
        extractor=extractor_map({BAD: _bad_claims}),
        max_attempts=3,
    )
    assert outcome.verdict is Verdict.FAIL
    assert outcome.attempts == 3
    run = db_session.get(ComplianceRun, outcome.run_id)
    assert run.status is Verdict.FAIL
    assert run.violations


def test_persisted_asset_is_marked_ai_generated(
    db_session, civic, active_ruleset, compliant_claims
):
    outcome = generate_compliant_ad(
        db_session,
        vehicle_id=civic.id,
        generator=gen_fixed(GOOD),
        extractor=extractor_map({GOOD: compliant_claims}),
    )
    run = db_session.get(ComplianceRun, outcome.run_id)
    asset = db_session.get(AdAsset, run.ad_asset_id)
    assert asset.generated_by == "gen-model"
    assert asset.copy_text == GOOD
