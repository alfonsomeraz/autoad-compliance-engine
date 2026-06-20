"""Copy-generation agent (Pydantic AI).

Generates ad copy from authoritative vehicle/offer facts. Like extraction, the
agent is exposed behind a `Generator` callable so the self-correct loop can be
tested with a stub (no API calls). The agent writes copy using ONLY the
provided facts and is told to include the disclosures the rules require; the
deterministic validator is still the final authority.
"""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from typing import Protocol

from pydantic import BaseModel, Field

from app.config import get_settings
from app.models.claims import SourceFacts
from app.models.enums import Channel

_INSTRUCTIONS = """\
You write compliant automotive advertising copy for a dealership. You are given
the authoritative vehicle and offer facts as JSON, the channel, and (sometimes)
feedback listing compliance violations from a previous attempt.

Hard rules:
- Use ONLY the provided facts. Never invent or alter a price, trim, APR, term,
  payment, or expiration. If a fact is absent, do not state it.
- If you advertise a monthly LEASE payment, include the lease disclosures: the
  amount due at signing, the lease term, the APR or total of payments, and
  lessee-responsibility language.
- If you advertise a monthly FINANCE payment, include APR, the finance term, and
  the down payment / amount financed.
- If you state an APR, note it is for well-qualified buyers.
- Include the vehicle's stock number, a "See dealer for details" line, and the
  offer expiration date.
- Disclose that the advertised price excludes government fees and taxes.

If feedback is provided, FIX every listed violation in this revision. Put all
fine print in the `disclaimers` list. Keep the headline and body punchy.
"""


class GeneratedAd(BaseModel):
    """Structured generation output. Assembled into a single copy_text blob that
    the validator then extracts and judges."""

    headline: str
    body: str
    disclaimers: list[str] = Field(default_factory=list)

    def to_copy_text(self) -> str:
        parts = [self.headline, self.body, *self.disclaimers]
        return "\n".join(p for p in parts if p)


class GeneratedCopyResult(BaseModel):
    copy_text: str
    model_name: str


class Generator(Protocol):
    """Callable the self-correct loop depends on."""

    def __call__(
        self, source: SourceFacts, channel: Channel, feedback: str | None
    ) -> GeneratedCopyResult: ...


def _facts_json(source: SourceFacts) -> str:
    def _default(o: object):
        if isinstance(o, Decimal):
            return str(o)
        return str(o)

    return json.dumps(source.model_dump(mode="python"), default=_default, indent=2)


@lru_cache
def get_generation_agent():
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    settings = get_settings()
    if not settings.anthropic_api_key or "your-key-here" in settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured; set it in .env to use the generation agent."
        )
    model = AnthropicModel(
        settings.llm_model_generation,
        provider=AnthropicProvider(api_key=settings.anthropic_api_key),
    )
    return Agent(model, output_type=GeneratedAd, instructions=_INSTRUCTIONS)


def llm_generator(
    source: SourceFacts, channel: Channel, feedback: str | None = None
) -> GeneratedCopyResult:
    """Production generator: run the live Pydantic AI generation agent."""
    agent = get_generation_agent()
    prompt = f"Channel: {channel.value}\n\nVehicle + offer facts:\n{_facts_json(source)}"
    if feedback:
        prompt += f"\n\nThe previous attempt FAILED compliance. Fix these violations:\n{feedback}"
    result = agent.run_sync(prompt)
    return GeneratedCopyResult(
        copy_text=result.output.to_copy_text(),
        model_name=get_settings().llm_model_generation,
    )
