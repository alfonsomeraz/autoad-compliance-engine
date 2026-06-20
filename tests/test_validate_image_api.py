"""POST /validate-image endpoint tests (stub vision extractor, no API calls)."""

from __future__ import annotations

from decimal import Decimal

from app.api.validate_image import get_vision_extractor
from app.llm.extraction import ExtractionResult
from app.main import app
from app.models.claims import AdClaims


def vstub(claims: AdClaims):
    def _v(image: bytes, media_type: str) -> ExtractionResult:
        return ExtractionResult(claims=claims, model_name="vision-stub")

    return _v


def _post(client, civic):
    return client.post(
        "/validate-image",
        data={"vehicle_id": civic.id},
        files={"image": ("ad.png", b"\x89PNG-fake", "image/png")},
    )


def test_validate_image_blocks_displayed_price_mismatch(client, civic, active_ruleset):
    displayed = AdClaims(advertised_price=Decimal("19999"), trim_claimed="Sport")
    app.dependency_overrides[get_vision_extractor] = lambda: vstub(displayed)
    resp = _post(client, civic)
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "FAIL"
    assert "ADVERTISED_PRICE_MATCHES_SOURCE" in {v["rule_key"] for v in body["violations"]}


def test_validate_image_faithful_passes(client, civic, active_ruleset, compliant_claims):
    app.dependency_overrides[get_vision_extractor] = lambda: vstub(compliant_claims)
    resp = _post(client, civic)
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "PASS"
