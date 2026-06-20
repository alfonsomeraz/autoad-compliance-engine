"""The multimodal money shot — LIVE vision over a rendered ad image.

Render an ad to a PNG, have the live vision agent read the displayed values,
and run them through the SAME deterministic engine:
- a faithful image (price from source) must NOT trip the price rule;
- a tampered image (displayed price != inventory) must FAIL on
  ADVERTISED_PRICE_MATCHES_SOURCE.

Requires ANTHROPIC_API_KEY. Lives outside tests/ (live API).
"""

from __future__ import annotations

import os
from decimal import Decimal

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

import pytest

from app.config import get_settings
from app.models.claims import AdClaims, SourceFacts
from app.models.enums import Verdict
from app.rules import engine
from app.rules.catalog import load_catalog
from app.vision.extraction import llm_vision_extractor
from app.vision.render_image import render_ad_image

_key = get_settings().anthropic_api_key
requires_api_key = pytest.mark.skipif(
    not _key or "your-key-here" in _key, reason="ANTHROPIC_API_KEY not configured"
)

CATALOG = load_catalog()


def _civic_source() -> SourceFacts:
    return SourceFacts(
        vehicle={
            "year": 2024,
            "make": "Honda",
            "model": "Civic",
            "trim": "Sport",
            "stock_number": "H24001",
        },
        offer={
            "effective_price": Decimal("26200"),
            "monthly_payment": Decimal("299"),
            "apr": Decimal("4.90"),
            "term_months": 36,
        },
    )


_DISCLAIMERS = [
    "Lessee is responsible for excess wear and mileage.",
    "Advertised price excludes government fees and taxes.",
    "See dealer for details. Financing for well-qualified buyers.",
]


@requires_api_key
def test_vision_reads_faithful_price():
    source = _civic_source()
    image = render_ad_image(source, AdClaims(disclaimers=_DISCLAIMERS))
    claims = llm_vision_extractor(image, "image/png").claims
    # The vision model should read the source price; the price rule must not fire.
    result = engine.evaluate(CATALOG, claims, source, jurisdiction="US-CA")
    fired = {f.rule_key for f in result.findings}
    print(f"\nFaithful image -> read price {claims.advertised_price}; fired={fired}")
    assert "ADVERTISED_PRICE_MATCHES_SOURCE" not in fired


@requires_api_key
def test_vision_catches_tampered_price():
    source = _civic_source()
    image = render_ad_image(source, AdClaims(disclaimers=_DISCLAIMERS), display_price="$19,999")
    claims = llm_vision_extractor(image, "image/png").claims
    result = engine.evaluate(CATALOG, claims, source, jurisdiction="US-CA")
    print(
        f"\nTampered image -> read price {claims.advertised_price}; verdict {result.verdict.value}"
    )
    assert result.verdict is Verdict.FAIL
    assert "ADVERTISED_PRICE_MATCHES_SOURCE" in {f.rule_key for f in result.findings}
