"""POST /generate — generate compliant ad copy with auto-validate/self-correct.

vehicle_id (+ channel) -> generated copy that has already passed the validator,
or the best attempt with its verdict + violations if it could not reach PASS.
The generator and extractor are injected so tests stub them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.validate import get_extractor
from app.db import get_db
from app.generation.agent import Generator, llm_generator
from app.generation.service import generate_compliant_ad
from app.llm.extraction import Extractor
from app.models.enums import Channel, Verdict

router = APIRouter()


def get_generator() -> Generator:
    """Default (production) generator. Overridden in tests."""
    return llm_generator


class GenerateRequest(BaseModel):
    vehicle_id: int
    channel: Channel = Channel.DISPLAY
    max_attempts: int = Field(default=3, ge=1, le=5)


class GenerateResponse(BaseModel):
    run_id: int
    verdict: Verdict
    attempts: int
    copy_text: str


@router.post("/generate", response_model=GenerateResponse, tags=["generation"])
def generate(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    generator: Generator = Depends(get_generator),
    extractor: Extractor = Depends(get_extractor),
) -> GenerateResponse:
    try:
        outcome = generate_compliant_ad(
            db,
            vehicle_id=req.vehicle_id,
            channel=req.channel,
            generator=generator,
            extractor=extractor,
            max_attempts=req.max_attempts,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GenerateResponse(
        run_id=outcome.run_id,
        verdict=outcome.verdict,
        attempts=outcome.attempts,
        copy_text=outcome.copy_text,
    )
