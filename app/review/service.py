"""Review-queue operations over compliance runs.

Query the queue, fetch a run's full audit detail, and record a reviewer's
decision. Decisions are appended to review_decision; the run's deterministic
verdict is never mutated (overrides are logged, not silent).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ReviewDecisionType, Verdict
from app.models.tables import ComplianceRun, ReviewDecision


def list_runs(db: Session, status: Verdict | None = None, limit: int = 50) -> list[ComplianceRun]:
    """List runs, most recent first, optionally filtered by verdict status.
    Pass status=REQUIRES_REVIEW for the review queue."""
    stmt = select(ComplianceRun).order_by(ComplianceRun.started_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(ComplianceRun.status == status)
    return list(db.scalars(stmt))


def get_run(db: Session, run_id: int) -> ComplianceRun:
    run = db.get(ComplianceRun, run_id)
    if run is None:
        raise LookupError(f"Compliance run {run_id} not found")
    return run


def record_decision(
    db: Session,
    run_id: int,
    *,
    reviewer: str,
    decision: ReviewDecisionType,
    notes: str | None = None,
) -> ReviewDecision:
    """Log a reviewer's decision for a run. Raises LookupError if the run is
    unknown. Does not change the run's deterministic verdict."""
    run = db.get(ComplianceRun, run_id)
    if run is None:
        raise LookupError(f"Compliance run {run_id} not found")
    record = ReviewDecision(
        compliance_run_id=run_id,
        reviewer=reviewer,
        decision=decision,
        notes=notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
