"""FastAPI application entry point.

Thin HTTP layer; all logic lives in the validation/rules/llm packages. Run with:

    uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.generate import router as generate_router
from app.api.review import router as review_router
from app.api.validate import router as validate_router
from app.api.validate_image import router as validate_image_router

app = FastAPI(
    title="AutoAd Compliance AI Engine",
    version="0.1.0",
    description="Generate and validate automotive ads; block non-compliant outputs.",
)

app.include_router(validate_router, tags=["validation"])
app.include_router(validate_image_router)
app.include_router(generate_router)
app.include_router(review_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
