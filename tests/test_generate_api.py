"""POST /generate endpoint tests (stub generator + extractor, no API calls)."""

from __future__ import annotations

from app.api.generate import get_generator
from app.api.validate import get_extractor
from app.generation.agent import GeneratedCopyResult
from app.llm.extraction import ExtractionResult
from app.main import app
from app.models.claims import AdClaims

GOOD = "GOOD COPY"


def gen_fixed(text: str):
    def _g(source, channel, feedback):
        return GeneratedCopyResult(copy_text=text, model_name="gen-model")

    return _g


def extractor_map(mapping: dict[str, AdClaims]):
    def _e(copy_text: str) -> ExtractionResult:
        return ExtractionResult(claims=mapping.get(copy_text, AdClaims()), model_name="ext-model")

    return _e


def test_generate_returns_compliant_copy(client, civic, active_ruleset, compliant_claims):
    app.dependency_overrides[get_generator] = lambda: gen_fixed(GOOD)
    app.dependency_overrides[get_extractor] = lambda: extractor_map({GOOD: compliant_claims})

    resp = client.post("/generate", json={"vehicle_id": civic.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "PASS"
    assert body["copy_text"] == GOOD
    assert body["attempts"] == 1
    assert body["run_id"] > 0


def test_generate_unknown_vehicle_returns_404(client):
    app.dependency_overrides[get_generator] = lambda: gen_fixed(GOOD)
    app.dependency_overrides[get_extractor] = lambda: extractor_map({})
    resp = client.post("/generate", json={"vehicle_id": 999999})
    assert resp.status_code == 404
