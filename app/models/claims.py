"""The extraction contract (`AdClaims`) and the source-of-truth facts.

`AdClaims` is what the LLM extraction agent must populate from unstructured ad
content — and *all* it produces for compliance. The deterministic rule engine
compares it against `SourceFacts` (built from authoritative vehicle + offer
rows) to reach a verdict. The LLM never decides the verdict.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PriceType

# Below this extraction confidence we never emit a confident PASS — a shaky
# extraction routes to REQUIRES_REVIEW instead.
LOW_CONFIDENCE_THRESHOLD = 0.6


class AdClaims(BaseModel):
    """Structured claims extracted from an ad. Every field is optional because
    an ad may or may not assert it; absence is itself meaningful to the rules."""

    advertised_price: Decimal | None = None
    price_type: PriceType = PriceType.UNKNOWN
    apr: Decimal | None = None
    lease_monthly_payment: Decimal | None = None
    lease_term_months: int | None = None
    due_at_signing: Decimal | None = None
    down_payment: Decimal | None = None
    total_of_payments: Decimal | None = None
    expiration_date: date | None = None
    trim_claimed: str | None = None
    disclaimers: list[str] = Field(default_factory=list)

    # Extraction self-assessment. confidence_notes is free text for the audit
    # trail; extraction_confidence (0-1) drives the deterministic low-confidence
    # REQUIRES_REVIEW trigger.
    confidence_notes: str | None = None
    extraction_confidence: float = 1.0

    @property
    def is_low_confidence(self) -> bool:
        return self.extraction_confidence < LOW_CONFIDENCE_THRESHOLD


class SourceFacts(BaseModel):
    """Authoritative facts an ad is allowed to claim, flattened from the
    vehicle + the offer being advertised. Rule predicates resolve dotted paths
    like `offer.effective_price` against this structure."""

    vehicle: dict = Field(default_factory=dict)
    offer: dict = Field(default_factory=dict)

    def resolve(self, path: str):
        """Resolve a dotted path (e.g. 'offer.effective_price') to a value, or
        None if any segment is missing."""
        node: object = self.model_dump()
        for segment in path.split("."):
            if not isinstance(node, dict) or segment not in node:
                return None
            node = node[segment]
        return node
