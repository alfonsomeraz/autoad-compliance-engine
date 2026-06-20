"""Validation orchestration: extract -> evaluate -> verdict -> persist.

The orchestrator is the seam where fuzzy extraction meets deterministic
judgment. It fetches authoritative facts, runs the (injectable) extractor,
hands claims + facts to the rule engine, and writes the immutable
`compliance_run` + `violation` audit records. It never decides a verdict
itself — that is the engine's job.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.extraction import Extractor, llm_extractor
from app.models.claims import AdClaims, SourceFacts
from app.models.enums import AssetFormat, Channel
from app.models.tables import AdAsset, ComplianceRun, Offer, Vehicle, Violation
from app.observability import get_logger
from app.rules import engine, sync
from app.rules.catalog import load_catalog
from app.rules.schema import Finding, RuleSpec
from app.vision.extraction import VisionExtractor, llm_vision_extractor

_log = get_logger(__name__)


class ResolvedRuleset(NamedTuple):
    specs: list[RuleSpec]
    rule_id_by_key: dict[str, int]
    ruleset_version_id: int | None


def resolve_ruleset(db: Session, catalog: list[RuleSpec] | None = None) -> ResolvedRuleset:
    """Resolve the rules to evaluate against. An explicit catalog (tests) wins;
    otherwise pin to the active ruleset_version; otherwise fall back to YAML."""
    if catalog is not None:
        return ResolvedRuleset(catalog, {}, None)
    active = sync.get_active_ruleset(db)
    if active is not None:
        return ResolvedRuleset(
            specs=[sync.rulespec_from_row(r) for r in active.rules],
            rule_id_by_key={r.rule_key: r.id for r in active.rules},
            ruleset_version_id=active.id,
        )
    return ResolvedRuleset(load_catalog(), {}, None)


def violations_from(findings: list[Finding], rule_id_by_key: dict[str, int]) -> list[Violation]:
    """Build Violation rows from engine findings, linking to rule rows."""
    return [
        Violation(
            rule_id=rule_id_by_key.get(f.rule_key),
            rule_key=f.rule_key,
            severity=f.severity,
            message=f.message,
            evidence=f.evidence,
        )
        for f in findings
    ]


def build_source_facts(vehicle: Vehicle, offer: Offer | None) -> SourceFacts:
    """Flatten the authoritative vehicle + offer into the structure the rule
    predicates resolve dotted paths against (e.g. offer.effective_price)."""
    veh = {
        "trim": vehicle.trim,
        "year": vehicle.year,
        "make": vehicle.make,
        "model": vehicle.model,
        "msrp": vehicle.msrp,
        "dealer_price": vehicle.dealer_price,
        "condition": str(vehicle.condition),
        "stock_number": vehicle.stock_number,
        "vin": vehicle.vin,
    }
    off: dict = {"effective_price": vehicle.dealer_price}
    if offer is not None:
        off.update(
            {
                "type": str(offer.type),
                "apr": offer.apr,
                "term_months": offer.term_months,
                "monthly_payment": offer.monthly_payment,
                "down_payment": offer.down_payment,
                "due_at_signing": offer.due_at_signing,
                "expiration_date": offer.expiration_date,
            }
        )
    return SourceFacts(vehicle=veh, offer=off)


def validate_ad(
    db: Session,
    *,
    vehicle_id: int,
    copy_text: str,
    channel: Channel = Channel.DISPLAY,
    extractor: Extractor = llm_extractor,
    catalog: list[RuleSpec] | None = None,
) -> ComplianceRun:
    """Validate ad copy against the rule catalog for a given vehicle.

    Persists an ad_asset, runs extraction + the rule engine, and writes the
    compliance_run + any violations. Returns the persisted run.
    """
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise LookupError(f"Vehicle {vehicle_id} not found")

    offer = db.scalars(
        select(Offer).where(Offer.vehicle_id == vehicle_id).order_by(Offer.id)
    ).first()
    jurisdiction = vehicle.dealership.jurisdiction

    asset = AdAsset(
        vehicle_id=vehicle_id,
        channel=channel,
        format=AssetFormat.TEXT,
        generated_by="human",
        copy_text=copy_text,
    )
    db.add(asset)
    db.flush()

    extraction = extractor(copy_text)
    return _evaluate_and_record(
        db,
        asset=asset,
        vehicle=vehicle,
        offer=offer,
        jurisdiction=jurisdiction,
        claims=extraction.claims,
        model_versions={"extraction": extraction.model_name},
        catalog=catalog,
    )


def validate_ad_image(
    db: Session,
    *,
    vehicle_id: int,
    image_bytes: bytes,
    media_type: str = "image/png",
    channel: Channel = Channel.DISPLAY,
    vision_extractor: VisionExtractor = llm_vision_extractor,
    catalog: list[RuleSpec] | None = None,
) -> ComplianceRun:
    """Validate an ad IMAGE: vision-extract the displayed claims and cross-check
    them against source via the same rule engine. Persists an image ad_asset +
    compliance_run. This is how a price/trim mismatch in creative gets caught."""
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise LookupError(f"Vehicle {vehicle_id} not found")

    offer = db.scalars(
        select(Offer).where(Offer.vehicle_id == vehicle_id).order_by(Offer.id)
    ).first()
    jurisdiction = vehicle.dealership.jurisdiction

    # No object store yet (Phase 4); record a content-addressed reference.
    image_ref = f"sha256:{hashlib.sha256(image_bytes).hexdigest()[:16]}"
    asset = AdAsset(
        vehicle_id=vehicle_id,
        channel=channel,
        format=AssetFormat.IMAGE,
        generated_by="human",
        image_s3_key=image_ref,
    )
    db.add(asset)
    db.flush()

    extraction = vision_extractor(image_bytes, media_type)
    return _evaluate_and_record(
        db,
        asset=asset,
        vehicle=vehicle,
        offer=offer,
        jurisdiction=jurisdiction,
        claims=extraction.claims,
        model_versions={"vision_extraction": extraction.model_name},
        catalog=catalog,
    )


def _evaluate_and_record(
    db: Session,
    *,
    asset: AdAsset,
    vehicle: Vehicle,
    offer: Offer | None,
    jurisdiction: str,
    claims: AdClaims,
    model_versions: dict,
    catalog: list[RuleSpec] | None,
) -> ComplianceRun:
    """Evaluate claims against the resolved ruleset and persist the immutable
    compliance_run + violations. Shared by the text and image paths."""
    ruleset = resolve_ruleset(db, catalog)
    source = build_source_facts(vehicle, offer)
    result = engine.evaluate(ruleset.specs, claims, source, jurisdiction=jurisdiction)

    run = ComplianceRun(
        ad_asset_id=asset.id,
        ruleset_version_id=ruleset.ruleset_version_id,
        status=result.verdict,
        extracted_claims=claims.model_dump(mode="json"),
        model_versions=model_versions,
        completed_at=datetime.now(timezone.utc),
    )
    run.violations = violations_from(result.findings, ruleset.rule_id_by_key)
    db.add(run)
    db.commit()
    db.refresh(run)

    _log.info(
        "compliance_run.recorded",
        run_id=run.id,
        verdict=run.status.value,
        violations=len(run.violations),
        ruleset_version_id=ruleset.ruleset_version_id,
        asset_format=asset.format.value,
        vehicle_id=asset.vehicle_id,
    )
    return run
