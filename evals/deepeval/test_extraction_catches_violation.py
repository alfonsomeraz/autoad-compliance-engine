"""Phase 0 DeepEval test — the seed of the eval hero.

Runs the LIVE extraction agent on a polished-looking lease ad that omits the
required disclosures, then proves two things:

1. Extraction recall on the trigger term: the agent must detect the monthly
   lease payment. Missing it is the dangerous case (it would suppress a real
   violation), so we weight this heavily — a deterministic DeepEval metric.
2. The deterministic engine then FAILs the ad on LEASE_DISCLOSURE_REQUIRED.

Requires a real ANTHROPIC_API_KEY. Lives outside tests/ so the fast,
deterministic suite never makes API calls; run explicitly or via the CI eval
gate:

    uv run pytest evals/deepeval -q --no-cov
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

import pytest
from deepeval import assert_test
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from app.config import get_settings
from app.llm.extraction import llm_extractor
from app.models.claims import SourceFacts
from app.models.enums import Verdict
from app.rules import engine
from app.rules.catalog import load_catalog

_key = get_settings().anthropic_api_key
requires_api_key = pytest.mark.skipif(
    not _key or "your-key-here" in _key,
    reason="ANTHROPIC_API_KEY not configured",
)

# A polished ad that advertises a monthly lease payment but discloses none of
# the Regulation M trigger terms.
NON_COMPLIANT_LEASE_AD = (
    "All-new Honda Civic Sport — lease it today for just $299/mo! "
    "Sleek design, legendary reliability. Visit Bayview Honda this weekend."
)


class TriggerTermRecallMetric(BaseMetric):
    """Deterministic: did extraction capture the monthly lease payment trigger
    term? actual_output is the extracted AdClaims as JSON."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        # Deterministic metric — run synchronously (no a_measure needed).
        self.async_mode = False

    def measure(self, test_case: LLMTestCase) -> float:
        claims = json.loads(test_case.actual_output)
        detected = claims.get("lease_monthly_payment") is not None
        self.score = 1.0 if detected else 0.0
        self.success = self.score >= self.threshold
        self.reason = (
            "Detected lease monthly payment trigger term."
            if detected
            else "MISSED the lease monthly payment trigger term."
        )
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        # Deterministic — just delegate to the sync implementation.
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self) -> str:
        return "Trigger-Term Recall (lease monthly payment)"


def _civic_source() -> SourceFacts:
    return SourceFacts(
        vehicle={"trim": "Sport"},
        offer={
            "effective_price": Decimal("26200.00"),
            "monthly_payment": Decimal("299.00"),
            "apr": Decimal("4.90"),
        },
    )


@requires_api_key
def test_extraction_catches_missing_lease_disclosure():
    extraction = llm_extractor(NON_COMPLIANT_LEASE_AD)
    claims = extraction.claims

    # 1) DeepEval: the agent must recall the trigger term.
    test_case = LLMTestCase(
        input=NON_COMPLIANT_LEASE_AD,
        actual_output=claims.model_dump_json(),
    )
    assert_test(test_case, [TriggerTermRecallMetric()])

    # 2) The deterministic engine must then block the ad.
    result = engine.evaluate(
        load_catalog(), claims, _civic_source(), jurisdiction="US"
    )
    assert result.verdict is Verdict.FAIL
    assert "LEASE_DISCLOSURE_REQUIRED" in {f.rule_key for f in result.findings}
