"""Multimodal validation tests — the vision money shot.

A vision-extracted image whose DISPLAYED price doesn't match inventory must be
blocked by the same deterministic engine. Stub vision extractor, no API calls.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.llm.extraction import ExtractionResult
from app.models.claims import AdClaims
from app.models.enums import AssetFormat, Verdict
from app.models.tables import AdAsset
from app.validation.orchestrator import validate_ad_image


def vstub(claims: AdClaims):
    def _v(image: bytes, media_type: str) -> ExtractionResult:
        return ExtractionResult(claims=claims, model_name="vision-stub")

    return _v


def test_faithful_image_passes_and_persists_image_asset(
    db_session, civic, active_ruleset, compliant_claims
):
    run = validate_ad_image(
        db_session,
        vehicle_id=civic.id,
        image_bytes=b"\x89PNG-fake",
        media_type="image/png",
        vision_extractor=vstub(compliant_claims),
    )
    assert run.status is Verdict.PASS
    asset = db_session.get(AdAsset, run.ad_asset_id)
    assert asset.format is AssetFormat.IMAGE
    assert asset.image_s3_key  # a traceable reference was recorded
    assert run.model_versions["vision_extraction"] == "vision-stub"


def test_displayed_price_mismatch_is_blocked(db_session, civic, active_ruleset):
    # The image "shows" $19,999 but inventory says $26,200.
    displayed = AdClaims(advertised_price=Decimal("19999"), trim_claimed="Sport")
    run = validate_ad_image(
        db_session,
        vehicle_id=civic.id,
        image_bytes=b"\x89PNG-fake",
        media_type="image/png",
        vision_extractor=vstub(displayed),
    )
    assert run.status is Verdict.FAIL
    assert "ADVERTISED_PRICE_MATCHES_SOURCE" in {v.rule_key for v in run.violations}


def test_unknown_vehicle_raises(db_session, active_ruleset):
    with pytest.raises(LookupError):
        validate_ad_image(
            db_session,
            vehicle_id=999999,
            image_bytes=b"x",
            media_type="image/png",
            vision_extractor=vstub(AdClaims()),
        )
