"""Sync the YAML rule catalog into versioned DB rows + ruleset snapshots.

YAML remains the authoring source; this module makes those rules durable,
versioned `rule` rows and pins them into an immutable `ruleset_version`. A
compliance_run references the active ruleset_version so the exact rules behind
any verdict are always reproducible.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.tables import Rule, RulesetVersion
from app.rules.catalog import load_catalog
from app.rules.schema import RuleSpec


def rulespec_from_row(row: Rule) -> RuleSpec:
    """Convert a persisted rule row into the engine's RuleSpec."""
    return RuleSpec(
        rule_key=row.rule_key,
        version=row.version,
        jurisdiction=row.jurisdiction,
        severity=row.severity,
        description=row.description,
        applies_when=row.applies_when,
        requirement=row.requirement,
        remediation=row.remediation,
        source_citation=row.source_citation,
    )


def sync_rules(db: Session, specs: list[RuleSpec]) -> list[Rule]:
    """Upsert each spec into the rule table, keyed by (rule_key, version).
    Existing rows are updated in place; new ones inserted. Returns the rows."""
    rows: list[Rule] = []
    for spec in specs:
        row = db.scalar(
            select(Rule).where(Rule.rule_key == spec.rule_key, Rule.version == spec.version)
        )
        if row is None:
            row = Rule(rule_key=spec.rule_key, version=spec.version)
            db.add(row)
        row.jurisdiction = spec.jurisdiction
        row.severity = spec.severity
        row.description = spec.description
        row.applies_when = spec.applies_when
        row.requirement = spec.requirement
        row.remediation = spec.remediation
        row.source_citation = spec.source_citation
        rows.append(row)
    db.flush()
    return rows


def create_ruleset_version(db: Session, label: str, rules: list[Rule]) -> RulesetVersion:
    """Snapshot the given rules into a new active ruleset_version, deactivating
    any previously active one (only one active at a time)."""
    db.execute(update(RulesetVersion).values(is_active=False))
    version = RulesetVersion(label=label, is_active=True, rules=list(rules))
    db.add(version)
    db.flush()
    return version


def get_active_ruleset(db: Session) -> RulesetVersion | None:
    return db.scalar(
        select(RulesetVersion)
        .where(RulesetVersion.is_active.is_(True))
        .order_by(RulesetVersion.id.desc())
    )


def sync_and_activate(
    db: Session, specs: list[RuleSpec] | None = None, label: str | None = None
) -> RulesetVersion:
    """Sync the catalog (YAML by default) and activate a ruleset snapshot."""
    specs = specs if specs is not None else load_catalog()
    rows = sync_rules(db, specs)
    label = label or f"catalog-{datetime.now(timezone.utc):%Y%m%d%H%M%S%f}"
    return create_ruleset_version(db, label, rows)
