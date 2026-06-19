"""POST /validate — the Phase 0 vertical slice endpoint.

Ad copy + vehicle_id -> verdict + violations. The extractor is provided via a
dependency so it can be overridden in tests (stub) and swapped in production.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.extraction import Extractor, llm_extractor
from app.models.enums import Channel, Severity, Verdict
from app.validation.orchestrator import validate_ad

router = APIRouter()


def get_extractor() -> Extractor:
    """Default (production) extractor. Overridden in tests."""
    return llm_extractor


class ValidateRequest(BaseModel):
    vehicle_id: int
    copy_text: str = Field(min_length=1)
    channel: Channel = Channel.DISPLAY


class ViolationOut(BaseModel):
    rule_key: str
    severity: Severity
    message: str
    evidence: dict = Field(default_factory=dict)


class ValidateResponse(BaseModel):
    run_id: int
    verdict: Verdict
    violations: list[ViolationOut]
    extracted_claims: dict


@router.post("/validate", response_model=ValidateResponse)
def validate(
    req: ValidateRequest,
    db: Session = Depends(get_db),
    extractor: Extractor = Depends(get_extractor),
) -> ValidateResponse:
    try:
        run = validate_ad(
            db,
            vehicle_id=req.vehicle_id,
            copy_text=req.copy_text,
            channel=req.channel,
            extractor=extractor,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ValidateResponse(
        run_id=run.id,
        verdict=run.status,
        violations=[
            ViolationOut(
                rule_key=v.rule_key,
                severity=v.severity,
                message=v.message,
                evidence=v.evidence or {},
            )
            for v in run.violations
        ],
        extracted_claims=run.extracted_claims or {},
    )
