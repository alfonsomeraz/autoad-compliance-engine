"""The eval hero — the CI-gated suite over the golden dataset.

Three surfaces, all using the LIVE pipeline:
1. Extraction recall on trigger terms — the dangerous miss (a missed monthly
   payment suppresses a real violation), so we gate it hard.
2. End-to-end blocker recall — of ads that truly contain a blocker, how many
   does the pipeline FAIL. This is the headline metric; target >= 0.95.
3. Generation faithfulness — generated copy must not hallucinate facts; every
   extracted number/trim/APR must trace to source.

Requires ANTHROPIC_API_KEY. Lives outside tests/ so the fast suite never makes
API calls. Thresholds and sizes are env-overridable for cheap local smoke runs:

    GOLDEN_EVAL_LIMIT=4 GEN_EVAL_LIMIT=1 \\
    BLOCKER_RECALL_MIN=0 TRIGGER_RECALL_MIN=0 \\
    uv run pytest evals/deepeval/test_golden_evals.py -s --no-cov
"""

from __future__ import annotations

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

import pytest

from app.config import get_settings
from app.generation.agent import llm_generator
from app.llm.extraction import llm_extractor
from app.models.claims import AdClaims, SourceFacts
from app.models.enums import Channel, Verdict
from app.rules import engine
from app.rules.catalog import load_catalog
from evals.datasets.loader import load_golden

_key = get_settings().anthropic_api_key
requires_api_key = pytest.mark.skipif(
    not _key or "your-key-here" in _key, reason="ANTHROPIC_API_KEY not configured"
)

CATALOG = load_catalog()
GOLDEN = load_golden()
TRIGGER_FIELDS = ("lease_monthly_payment", "finance_monthly_payment", "apr")

BLOCKER_RECALL_MIN = float(os.getenv("BLOCKER_RECALL_MIN", "0.95"))
TRIGGER_RECALL_MIN = float(os.getenv("TRIGGER_RECALL_MIN", "0.95"))


def _limit(env: str, default: int) -> int:
    value = int(os.getenv(env, "0"))
    return value if value > 0 else default


@pytest.fixture(scope="module")
def pipeline():
    """Run extraction + the engine over the golden ads once (live)."""
    ads = GOLDEN[: _limit("GOLDEN_EVAL_LIMIT", len(GOLDEN))]
    rows = []
    for ad in ads:
        claims = llm_extractor(ad.ad_copy).claims
        source = SourceFacts.model_validate(ad.source_facts)
        result = engine.evaluate(CATALOG, claims, source, jurisdiction=ad.jurisdiction)
        rows.append((ad, claims, result))
    return rows


@requires_api_key
def test_trigger_term_recall(pipeline):
    total = hits = 0
    misses = []
    for ad, claims, _ in pipeline:
        true = AdClaims.model_validate(ad.true_claims)
        for field in TRIGGER_FIELDS:
            if getattr(true, field) is not None:
                total += 1
                if getattr(claims, field) is not None:
                    hits += 1
                else:
                    misses.append(f"{ad.id}:{field}")
    recall = hits / total if total else 1.0
    print(f"\nTrigger-term recall: {recall:.3f} ({hits}/{total}); misses={misses}")
    assert recall >= TRIGGER_RECALL_MIN, f"trigger-term recall {recall:.3f}"


@requires_api_key
def test_end_to_end_blocker_recall(pipeline):
    total = caught = 0
    missed = []
    for ad, _, result in pipeline:
        if ad.expected_blocker_rule_keys:
            total += 1
            if result.verdict is Verdict.FAIL:
                caught += 1
            else:
                missed.append(f"{ad.id}->{result.verdict.value}")
    recall = caught / total if total else 1.0
    print(f"\nBlocker recall: {recall:.3f} ({caught}/{total}); missed={missed}")
    assert recall >= BLOCKER_RECALL_MIN, f"blocker recall {recall:.3f}"


@requires_api_key
def test_verdict_confusion_matrix(pipeline):
    # Reported for the demo; we assert only that no truly-blocking ad passes.
    labels = ("PASS", "FAIL", "REQUIRES_REVIEW")
    matrix = {exp: {got: 0 for got in labels} for exp in labels}
    false_pass = []
    for ad, _, result in pipeline:
        matrix[ad.expected_verdict][result.verdict.value] += 1
        if ad.expected_blocker_rule_keys and result.verdict is Verdict.PASS:
            false_pass.append(ad.id)
    print("\nConfusion matrix (expected -> predicted):")
    for exp in labels:
        print(f"  {exp:>16}: {matrix[exp]}")
    assert not false_pass, f"blocking ads marked PASS: {false_pass}"


@requires_api_key
def test_generation_faithfulness():
    """Generated copy must not invent facts: extracted price/trim/APR either
    trace to source or are absent."""
    compliant = [ad for ad in GOLDEN if ad.scenario == "compliant"]
    sample = compliant[: _limit("GEN_EVAL_LIMIT", 3)]
    hallucinations = []
    for ad in sample:
        source = SourceFacts.model_validate(ad.source_facts)
        copy = llm_generator(source, Channel.DISPLAY, None).copy_text
        claims = llm_extractor(copy).claims

        eff = source.resolve("offer.effective_price")
        trim = source.resolve("vehicle.trim")
        apr = source.resolve("offer.apr")
        if claims.advertised_price is not None and str(claims.advertised_price) != str(eff):
            hallucinations.append(f"{ad.id}: price {claims.advertised_price} != {eff}")
        if claims.trim_claimed is not None and claims.trim_claimed.lower() != str(trim).lower():
            hallucinations.append(f"{ad.id}: trim {claims.trim_claimed} != {trim}")
        if apr is not None and claims.apr is not None and str(claims.apr) != str(apr):
            hallucinations.append(f"{ad.id}: apr {claims.apr} != {apr}")
    print(f"\nGeneration faithfulness over {len(sample)} ads; hallucinations={hallucinations}")
    assert not hallucinations
