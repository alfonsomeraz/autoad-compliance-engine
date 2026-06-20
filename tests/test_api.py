"""POST /validate endpoint tests.

Uses FastAPI dependency overrides to inject the rolled-back test session and a
stub extractor, so the HTTP contract is exercised without a DB of record or any
API calls.
"""

from __future__ import annotations

from decimal import Decimal

from app.api.validate import get_extractor
from app.llm.extraction import ExtractionResult
from app.main import app
from app.models.claims import AdClaims


def stub(claims: AdClaims):
    def _extract(ad_copy: str) -> ExtractionResult:
        return ExtractionResult(claims=claims, model_name="stub-model")

    return _extract


def test_validate_returns_fail_with_violations(client, civic, active_ruleset):
    bad = AdClaims(lease_monthly_payment=Decimal("299.00"), trim_claimed="Touring")
    app.dependency_overrides[get_extractor] = lambda: stub(bad)

    resp = client.post(
        "/validate",
        json={"vehicle_id": civic.id, "copy_text": "Civic Touring $299/mo!"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "FAIL"
    rule_keys = {v["rule_key"] for v in body["violations"]}
    assert "ADVERTISED_TRIM_MATCHES_SOURCE" in rule_keys
    assert "LEASE_DISCLOSURE_REQUIRED" in rule_keys
    assert body["run_id"] > 0


def test_validate_clean_ad_passes(client, civic, active_ruleset, compliant_claims):
    app.dependency_overrides[get_extractor] = lambda: stub(compliant_claims)

    resp = client.post(
        "/validate",
        json={"vehicle_id": civic.id, "copy_text": "Civic Sport for $26,200"},
    )

    assert resp.status_code == 200
    assert resp.json()["verdict"] == "PASS"


def test_validate_unknown_vehicle_returns_404(client):
    app.dependency_overrides[get_extractor] = lambda: stub(AdClaims())
    resp = client.post("/validate", json={"vehicle_id": 999999, "copy_text": "anything"})
    assert resp.status_code == 404
