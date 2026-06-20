"""Vision claims-extraction agent (Pydantic AI, multimodal).

Extracts the *displayed* values from a rendered ad image into the SAME
`AdClaims` schema the text path uses, so the deterministic rule engine can
cross-check them against source. This catches "the picture says $299/mo but the
offer is $399/mo." Exposed behind a `VisionExtractor` callable so the multimodal
orchestrator can be tested with a stub (no API calls).

Pydantic AI vision input (verified against docs):
    agent.run_sync([prompt, BinaryContent(data=img_bytes, media_type="image/png")])
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.llm.extraction import ExtractionResult
from app.models.claims import AdClaims

_INSTRUCTIONS = """\
You are a claims-extraction component in an automotive-advertising compliance
system. You are given an IMAGE of an ad. Extract ONLY the values visibly
DISPLAYED in the image into the AdClaims schema. Report what the image shows —
you do NOT judge compliance and you do NOT decide a verdict.

- Read the headline price, any monthly lease/finance payment, APR, term, due at
  signing, down payment, trim, stock number/VIN, and expiration date as shown.
- Transcribe every fine-print / disclaimer line you can read into `disclaimers`.
- Populate a field only if it is actually visible. Do not infer hidden values.
- Set extraction_confidence (0-1); lower it if text is small, stylized, or hard
  to read, and note why in confidence_notes. A shaky read must not look certain.
"""


class VisionExtractor(Protocol):
    def __call__(self, image: bytes, media_type: str) -> ExtractionResult: ...


@lru_cache
def get_vision_agent():
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    settings = get_settings()
    if not settings.anthropic_api_key or "your-key-here" in settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured; set it in .env to use the "
            "vision extraction agent."
        )
    # Sonnet is multimodal; reuse the extraction model.
    model = AnthropicModel(
        settings.llm_model_extraction,
        provider=AnthropicProvider(api_key=settings.anthropic_api_key),
    )
    return Agent(model, output_type=AdClaims, instructions=_INSTRUCTIONS)


def llm_vision_extractor(image: bytes, media_type: str) -> ExtractionResult:
    """Production vision extractor: run the live multimodal agent on an image."""
    from pydantic_ai import BinaryContent

    agent = get_vision_agent()
    result = agent.run_sync(
        [
            "Extract the displayed ad claims from this image.",
            BinaryContent(data=image, media_type=media_type),
        ]
    )
    return ExtractionResult(
        claims=result.output, model_name=f"{get_settings().llm_model_extraction}-vision"
    )
