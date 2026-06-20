"""SQLAlchemy ORM models — the source of truth for factual checks + audit.

Milestone 0 subset of the §8 data model: oem, dealership, vehicle, offer,
ad_asset, compliance_run, violation. Rules are still authored in code/YAML at
this stage; `rule`, `ruleset_version`, and `review_decision` arrive in
Milestone 1 as a follow-up Alembic migration.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    AssetFormat,
    Channel,
    OfferType,
    ReviewDecisionType,
    Severity,
    VehicleCondition,
    Verdict,
)


class OEM(Base):
    __tablename__ = "oem"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    brand_guidelines_ref: Mapped[str | None] = mapped_column(Text, default=None)

    dealerships: Mapped[list[Dealership]] = relationship(back_populates="oem")


class Dealership(Base):
    __tablename__ = "dealership"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    dba_name: Mapped[str | None] = mapped_column(String(160), default=None)
    oem_id: Mapped[int | None] = mapped_column(ForeignKey("oem.id"), default=None)
    # Jurisdiction drives which rules apply (e.g. "US", "US-CA").
    jurisdiction: Mapped[str] = mapped_column(String(16), default="US")

    oem: Mapped[OEM | None] = relationship(back_populates="dealerships")
    vehicles: Mapped[list[Vehicle]] = relationship(back_populates="dealership")


class Vehicle(Base):
    __tablename__ = "vehicle"

    id: Mapped[int] = mapped_column(primary_key=True)
    dealership_id: Mapped[int] = mapped_column(ForeignKey("dealership.id"))
    vin: Mapped[str] = mapped_column(String(17), unique=True)
    year: Mapped[int]
    make: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    trim: Mapped[str] = mapped_column(String(80))
    msrp: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    dealer_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    mileage: Mapped[int] = mapped_column(default=0)
    condition: Mapped[VehicleCondition] = mapped_column(default=VehicleCondition.NEW)
    stock_number: Mapped[str] = mapped_column(String(40))
    body_style: Mapped[str | None] = mapped_column(String(40), default=None)

    dealership: Mapped[Dealership] = relationship(back_populates="vehicles")
    offers: Mapped[list[Offer]] = relationship(back_populates="vehicle")
    ad_assets: Mapped[list[AdAsset]] = relationship(back_populates="vehicle")


class Offer(Base):
    __tablename__ = "offer"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id"))
    type: Mapped[OfferType]
    apr: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)
    term_months: Mapped[int | None] = mapped_column(default=None)
    monthly_payment: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    down_payment: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    due_at_signing: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    residual: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    expiration_date: Mapped[date | None] = mapped_column(default=None)
    jurisdiction: Mapped[str] = mapped_column(String(16), default="US")

    vehicle: Mapped[Vehicle] = relationship(back_populates="offers")


class AdAsset(Base):
    __tablename__ = "ad_asset"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id"))
    channel: Mapped[Channel] = mapped_column(default=Channel.DISPLAY)
    format: Mapped[AssetFormat] = mapped_column(default=AssetFormat.TEXT)
    generated_by: Mapped[str] = mapped_column(String(40), default="human")
    copy_text: Mapped[str | None] = mapped_column(Text, default=None)
    image_s3_key: Mapped[str | None] = mapped_column(String(256), default=None)
    generation_metadata: Mapped[dict | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vehicle: Mapped[Vehicle] = relationship(back_populates="ad_assets")
    compliance_runs: Mapped[list[ComplianceRun]] = relationship(back_populates="ad_asset")


class ComplianceRun(Base):
    __tablename__ = "compliance_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    ad_asset_id: Mapped[int] = mapped_column(ForeignKey("ad_asset.id"))
    # The immutable ruleset this run was evaluated against (pins the audit).
    ruleset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("ruleset_version.id"), default=None
    )
    status: Mapped[Verdict]
    extracted_claims: Mapped[dict | None] = mapped_column(JSONB, default=None)
    model_versions: Mapped[dict | None] = mapped_column(JSONB, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    ad_asset: Mapped[AdAsset] = relationship(back_populates="compliance_runs")
    ruleset_version: Mapped[RulesetVersion | None] = relationship()
    violations: Mapped[list[Violation]] = relationship(
        back_populates="compliance_run", cascade="all, delete-orphan"
    )
    review_decisions: Mapped[list[ReviewDecision]] = relationship(
        back_populates="compliance_run", cascade="all, delete-orphan"
    )


class Violation(Base):
    __tablename__ = "violation"

    id: Mapped[int] = mapped_column(primary_key=True)
    compliance_run_id: Mapped[int] = mapped_column(ForeignKey("compliance_run.id"))
    # rule_id ties to the DB rule row; rule_key is kept for readable audit.
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rule.id"), default=None)
    rule_key: Mapped[str] = mapped_column(String(80))
    severity: Mapped[Severity]
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSONB, default=None)

    compliance_run: Mapped[ComplianceRun] = relationship(back_populates="violations")


# A ruleset version is an immutable snapshot of which rule rows it contains.
ruleset_version_rule = Table(
    "ruleset_version_rule",
    Base.metadata,
    Column(
        "ruleset_version_id",
        ForeignKey("ruleset_version.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("rule_id", ForeignKey("rule.id"), primary_key=True),
)


class Rule(Base):
    """A compliance rule as a versioned DB row. The predicate trees live in
    JSONB so the catalog grows without redeploys; (rule_key, version) is unique
    so prior versions stay diffable and auditable."""

    __tablename__ = "rule"
    __table_args__ = (UniqueConstraint("rule_key", "version", name="uq_rule_key_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(default=1)
    jurisdiction: Mapped[str] = mapped_column(String(16), default="US")
    severity: Mapped[Severity]
    description: Mapped[str] = mapped_column(Text, default="")
    applies_when: Mapped[dict] = mapped_column(JSONB, default=dict)
    requirement: Mapped[dict] = mapped_column(JSONB, default=dict)
    remediation: Mapped[str] = mapped_column(Text, default="")
    source_citation: Mapped[str] = mapped_column(Text, default="")
    effective_from: Mapped[date | None] = mapped_column(Date, default=None)
    effective_to: Mapped[date | None] = mapped_column(Date, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RulesetVersion(Base):
    """An immutable, labeled snapshot of the rules in force. A compliance_run
    pins to one so the exact ruleset behind a verdict is always reproducible."""

    __tablename__ = "ruleset_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(80), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rules: Mapped[list[Rule]] = relationship(secondary=ruleset_version_rule)


class ReviewDecision(Base):
    """A reviewer's decision on a run that requires review. Overrides are logged
    here, never silent — this is the human-in-the-loop audit trail."""

    __tablename__ = "review_decision"

    id: Mapped[int] = mapped_column(primary_key=True)
    compliance_run_id: Mapped[int] = mapped_column(ForeignKey("compliance_run.id"))
    reviewer: Mapped[str] = mapped_column(String(120))
    decision: Mapped[ReviewDecisionType]
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    compliance_run: Mapped[ComplianceRun] = relationship(back_populates="review_decisions")
