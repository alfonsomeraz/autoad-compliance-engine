"""Review-queue + audit + catalog HTTP endpoints."""

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


def _validate(client, civic, claims):
    app.dependency_overrides[get_extractor] = lambda: stub(claims)
    return client.post("/validate", json={"vehicle_id": civic.id, "copy_text": "ad"}).json()


def test_review_queue_lists_requires_review(client, civic, active_ruleset, compliant_claims):
    _validate(client, civic, compliant_claims.model_copy(update={"extraction_confidence": 0.2}))
    resp = client.get("/reviews")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1
    assert all(r["status"] == "REQUIRES_REVIEW" for r in runs)


def test_run_detail_endpoint_returns_violations(client, civic, active_ruleset):
    bad = AdClaims(lease_monthly_payment=Decimal("299.00"), trim_claimed="Touring")
    run = _validate(client, civic, bad)
    resp = client.get(f"/runs/{run['run_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FAIL"
    assert any(v["rule_key"] == "ADVERTISED_TRIM_MATCHES_SOURCE" for v in body["violations"])


def test_post_decision_logs_and_appears_in_detail(client, civic, active_ruleset, compliant_claims):
    run = _validate(
        client, civic, compliant_claims.model_copy(update={"extraction_confidence": 0.2})
    )
    resp = client.post(
        f"/runs/{run['run_id']}/decisions",
        json={"reviewer": "jane@dealer.com", "decision": "approve", "notes": "ok"},
    )
    assert resp.status_code == 201
    detail = client.get(f"/runs/{run['run_id']}").json()
    assert len(detail["review_decisions"]) == 1
    assert detail["review_decisions"][0]["decision"] == "approve"


def test_active_ruleset_endpoint_lists_rules(client, civic, active_ruleset):
    resp = client.get("/ruleset/active")
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "test-active-ruleset"
    assert len(body["rules"]) >= 12


def test_run_detail_unknown_returns_404(client):
    assert client.get("/runs/999999").status_code == 404
