"""Generate compliant ad copy with auto-validate-and-self-correct.

Generate copy -> extract its claims -> evaluate against the rule engine. If the
verdict is not PASS, summarize the violations as feedback and regenerate, up to
max_attempts. The final attempt is persisted as an AI-generated ad_asset plus
its immutable compliance_run — the system never returns copy it didn't validate.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.generation.agent import Generator, llm_generator
from app.llm.extraction import Extractor, llm_extractor
from app.models.enums import AssetFormat, Channel, Verdict
from app.models.tables import AdAsset, ComplianceRun, Offer, Vehicle
from app.rules import engine
from app.rules.schema import EvaluationResult
from app.validation.orchestrator import (
    build_source_facts,
    resolve_ruleset,
    violations_from,
)


class GenerationOutcome(BaseModel):
    copy_text: str
    verdict: Verdict
    attempts: int
    run_id: int


def _feedback(result: EvaluationResult) -> str:
    return "\n".join(f"- {f.rule_key} ({f.severity.value}): {f.message}" for f in result.findings)


def generate_compliant_ad(
    db: Session,
    *,
    vehicle_id: int,
    channel: Channel = Channel.DISPLAY,
    generator: Generator = llm_generator,
    extractor: Extractor = llm_extractor,
    max_attempts: int = 3,
) -> GenerationOutcome:
    """Generate copy, self-correcting against the validator up to max_attempts.
    Persists the final attempt as an AI-generated asset + compliance run."""
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise LookupError(f"Vehicle {vehicle_id} not found")

    offer = db.scalars(
        select(Offer).where(Offer.vehicle_id == vehicle_id).order_by(Offer.id)
    ).first()
    jurisdiction = vehicle.dealership.jurisdiction
    source = build_source_facts(vehicle, offer)
    ruleset = resolve_ruleset(db)

    feedback: str | None = None
    attempts = 0
    generated = None
    extraction = None
    result = None
    while attempts < max_attempts:
        attempts += 1
        generated = generator(source, channel, feedback)
        extraction = extractor(generated.copy_text)
        result = engine.evaluate(
            ruleset.specs, extraction.claims, source, jurisdiction=jurisdiction
        )
        if result.verdict is Verdict.PASS:
            break
        feedback = _feedback(result)

    asset = AdAsset(
        vehicle_id=vehicle_id,
        channel=channel,
        format=AssetFormat.TEXT,
        generated_by=generated.model_name,
        copy_text=generated.copy_text,
        generation_metadata={"attempts": attempts},
    )
    db.add(asset)
    db.flush()

    run = ComplianceRun(
        ad_asset_id=asset.id,
        ruleset_version_id=ruleset.ruleset_version_id,
        status=result.verdict,
        extracted_claims=extraction.claims.model_dump(mode="json"),
        model_versions={
            "generation": generated.model_name,
            "extraction": extraction.model_name,
        },
        completed_at=datetime.now(timezone.utc),
    )
    run.violations = violations_from(result.findings, ruleset.rule_id_by_key)
    db.add(run)
    db.commit()
    db.refresh(run)

    return GenerationOutcome(
        copy_text=generated.copy_text,
        verdict=result.verdict,
        attempts=attempts,
        run_id=run.id,
    )
