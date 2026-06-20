"""POST /validate-image — validate an ad IMAGE against source via vision.

Accepts a multipart image upload + vehicle_id. The vision agent extracts the
displayed claims; the deterministic engine cross-checks them against inventory.
The vision extractor is injected so tests stub it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.validate import ValidateResponse, ViolationOut
from app.db import get_db
from app.validation.orchestrator import validate_ad_image
from app.vision.extraction import VisionExtractor, llm_vision_extractor

router = APIRouter()


def get_vision_extractor() -> VisionExtractor:
    """Default (production) vision extractor. Overridden in tests."""
    return llm_vision_extractor


@router.post("/validate-image", response_model=ValidateResponse, tags=["validation"])
def validate_image(
    vehicle_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    vision_extractor: VisionExtractor = Depends(get_vision_extractor),
) -> ValidateResponse:
    data = image.file.read()
    try:
        run = validate_ad_image(
            db,
            vehicle_id=vehicle_id,
            image_bytes=data,
            media_type=image.content_type or "image/png",
            vision_extractor=vision_extractor,
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
