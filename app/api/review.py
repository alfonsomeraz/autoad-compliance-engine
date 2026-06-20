"""Review-queue, audit-detail, and catalog endpoints.

GET  /reviews                 list runs (default: the REQUIRES_REVIEW queue)
GET  /runs/{run_id}           full audit detail for one run
POST /runs/{run_id}/decisions log a reviewer decision (approve/reject/override)
GET  /ruleset/active          the active ruleset and its rules (catalog view)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.enums import ReviewDecisionType, Severity, Verdict
from app.review import service
from app.rules import sync

router = APIRouter()


class RunSummary(BaseModel):
    run_id: int
    ad_asset_id: int
    status: Verdict
    violation_count: int
    ruleset_version_id: int | None
    started_at: datetime


class ViolationOut(BaseModel):
    rule_key: str
    severity: Severity
    message: str
    evidence: dict = Field(default_factory=dict)


class DecisionOut(BaseModel):
    id: int
    reviewer: str
    decision: ReviewDecisionType
    notes: str | None
    decided_at: datetime


class RunDetail(BaseModel):
    run_id: int
    status: Verdict
    ruleset_version_id: int | None
    extracted_claims: dict
    violations: list[ViolationOut]
    review_decisions: list[DecisionOut]


class DecisionIn(BaseModel):
    reviewer: str = Field(min_length=1)
    decision: ReviewDecisionType
    notes: str | None = None


class RuleOut(BaseModel):
    rule_key: str
    version: int
    jurisdiction: str
    severity: Severity
    description: str
    source_citation: str


class ActiveRulesetOut(BaseModel):
    ruleset_version_id: int
    label: str
    rules: list[RuleOut]


@router.get("/reviews", response_model=list[RunSummary], tags=["review"])
def list_reviews(
    status_filter: Verdict = Query(
        default=Verdict.REQUIRES_REVIEW, alias="status"
    ),
    db: Session = Depends(get_db),
) -> list[RunSummary]:
    runs = service.list_runs(db, status=status_filter)
    return [
        RunSummary(
            run_id=r.id,
            ad_asset_id=r.ad_asset_id,
            status=r.status,
            violation_count=len(r.violations),
            ruleset_version_id=r.ruleset_version_id,
            started_at=r.started_at,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunDetail, tags=["review"])
def get_run(run_id: int, db: Session = Depends(get_db)) -> RunDetail:
    try:
        run = service.get_run(db, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunDetail(
        run_id=run.id,
        status=run.status,
        ruleset_version_id=run.ruleset_version_id,
        extracted_claims=run.extracted_claims or {},
        violations=[
            ViolationOut(
                rule_key=v.rule_key,
                severity=v.severity,
                message=v.message,
                evidence=v.evidence or {},
            )
            for v in run.violations
        ],
        review_decisions=[
            DecisionOut(
                id=d.id,
                reviewer=d.reviewer,
                decision=d.decision,
                notes=d.notes,
                decided_at=d.decided_at,
            )
            for d in run.review_decisions
        ],
    )


@router.post(
    "/runs/{run_id}/decisions",
    response_model=DecisionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["review"],
)
def post_decision(
    run_id: int, body: DecisionIn, db: Session = Depends(get_db)
) -> DecisionOut:
    try:
        record = service.record_decision(
            db,
            run_id,
            reviewer=body.reviewer,
            decision=body.decision,
            notes=body.notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DecisionOut(
        id=record.id,
        reviewer=record.reviewer,
        decision=record.decision,
        notes=record.notes,
        decided_at=record.decided_at,
    )


@router.get("/ruleset/active", response_model=ActiveRulesetOut, tags=["review"])
def get_active_ruleset(db: Session = Depends(get_db)) -> ActiveRulesetOut:
    ruleset = sync.get_active_ruleset(db)
    if ruleset is None:
        raise HTTPException(status_code=404, detail="No active ruleset")
    return ActiveRulesetOut(
        ruleset_version_id=ruleset.id,
        label=ruleset.label,
        rules=[
            RuleOut(
                rule_key=r.rule_key,
                version=r.version,
                jurisdiction=r.jurisdiction,
                severity=r.severity,
                description=r.description,
                source_citation=r.source_citation,
            )
            for r in ruleset.rules
        ],
    )
