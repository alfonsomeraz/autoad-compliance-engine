"""Claims-extraction agent (Pydantic AI).

The agent turns unstructured ad copy into a typed `AdClaims` object — and that
is *all* it does for compliance. It never decides a verdict; the deterministic
rule engine does. The agent is exposed behind the `Extractor` callable so the
orchestrator can be tested with a stub (no API calls) while production uses the
live LLM.

Pydantic AI 1.x API (verified against docs):
    agent = Agent('anthropic:claude-sonnet-4-6', output_type=AdClaims, instructions=...)
    result = agent.run_sync(ad_copy); result.output -> AdClaims
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from pydantic import BaseModel
from pydantic_ai import Agent

from app.config import get_settings
from app.models.claims import AdClaims

_INSTRUCTIONS = """\
You are a claims-extraction component in an automotive-advertising compliance
system. Extract ONLY the claims that the ad copy literally makes into the
structured AdClaims schema. You do NOT judge compliance and you do NOT decide a
verdict — you only report what the ad says.

Rules for extraction:
- Extract a field only if the ad actually states it. Do not infer, guess, or
  fill in plausible values. Leave a field null when the ad is silent on it.
- advertised_price: the headline price the ad shows for the vehicle (not a
  monthly payment). Set price_type to reflect how price is presented.
- lease_monthly_payment, finance_monthly_payment, and a cash price are different
  claims — populate lease_monthly_payment only for a monthly LEASE payment, and
  finance_monthly_payment only for a monthly FINANCE/loan payment.
- Capture every fine-print / disclaimer sentence verbatim in `disclaimers`.
- apr, lease_term_months, finance_term_months, due_at_signing, down_payment,
  expiration_date, trim_claimed: populate from the ad's literal text when present.
- stock_number_claimed / vin_claimed: the stock number or VIN if the ad names a
  specific vehicle.
- Set extraction_confidence between 0 and 1 (1 = certain). Lower it when the ad
  is ambiguous, low quality, or hard to parse. Use confidence_notes to explain
  anything uncertain. A shaky extraction must not look confident.
"""


class ExtractionResult(BaseModel):
    """Extracted claims plus the model that produced them (for the audit trail)."""

    claims: AdClaims
    model_name: str


class Extractor(Protocol):
    """Callable contract the orchestrator depends on."""

    def __call__(self, ad_copy: str) -> ExtractionResult: ...


@lru_cache
def get_extraction_agent() -> Agent[None, AdClaims]:
    """Lazily build the extraction agent so importing this module never requires
    an API key (DB/rule-only flows run without one).

    The configured key from Settings is wired explicitly into the provider so
    behavior doesn't depend on the ambient environment."""
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    settings = get_settings()
    if not settings.anthropic_api_key or "your-key-here" in settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured; set it in .env to use the "
            "extraction agent."
        )
    model = AnthropicModel(
        settings.llm_model_extraction,
        provider=AnthropicProvider(api_key=settings.anthropic_api_key),
    )
    return Agent(model, output_type=AdClaims, instructions=_INSTRUCTIONS)


def llm_extractor(ad_copy: str) -> ExtractionResult:
    """Production extractor: run the live Pydantic AI agent."""
    agent = get_extraction_agent()
    result = agent.run_sync(ad_copy)
    return ExtractionResult(
        claims=result.output, model_name=get_settings().llm_model_extraction
    )
