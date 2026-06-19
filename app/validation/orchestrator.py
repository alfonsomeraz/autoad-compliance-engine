"""Validation orchestration: extract -> evaluate -> verdict -> persist.

The orchestrator is the seam where fuzzy extraction meets deterministic
judgment. It fetches authoritative facts, runs the (injectable) extractor,
hands claims + facts to the rule engine, and writes the immutable
`compliance_run` + `violation` audit records. It never decides a verdict
itself — that is the engine's job.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.extraction import Extractor, llm_extractor
from app.models.claims import SourceFacts
from app.models.enums import AssetFormat, Channel
from app.models.tables import AdAsset, ComplianceRun, Offer, Vehicle, Violation
from app.rules import engine, sync
from app.rules.catalog import load_catalog
from app.rules.schema import RuleSpec


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

    # Resolve the ruleset: an explicit catalog (tests) wins; otherwise pin to
    # the active ruleset_version in the DB; otherwise fall back to YAML.
    rule_id_by_key: dict[str, int] = {}
    ruleset_version_id: int | None = None
    if catalog is not None:
        specs = catalog
    else:
        active = sync.get_active_ruleset(db)
        if active is not None:
            specs = [sync.rulespec_from_row(r) for r in active.rules]
            rule_id_by_key = {r.rule_key: r.id for r in active.rules}
            ruleset_version_id = active.id
        else:
            specs = load_catalog()

    extraction = extractor(copy_text)
    source = build_source_facts(vehicle, offer)
    result = engine.evaluate(
        specs, extraction.claims, source, jurisdiction=jurisdiction
    )

    run = ComplianceRun(
        ad_asset_id=asset.id,
        ruleset_version_id=ruleset_version_id,
        status=result.verdict,
        extracted_claims=extraction.claims.model_dump(mode="json"),
        model_versions={"extraction": extraction.model_name},
        completed_at=datetime.now(timezone.utc),
    )
    run.violations = [
        Violation(
            rule_id=rule_id_by_key.get(f.rule_key),
            rule_key=f.rule_key,
            severity=f.severity,
            message=f.message,
            evidence=f.evidence,
        )
        for f in result.findings
    ]
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
