"""FastAPI application entry point.

Thin HTTP layer; all logic lives in the validation/rules/llm packages. Run with:

    uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.generate import router as generate_router
from app.api.review import router as review_router
from app.api.validate import router as validate_router
from app.api.validate_image import router as validate_image_router
from app.api.vehicles import router as vehicles_router
from app.observability import configure_logging

configure_logging()

_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

app = FastAPI(
    title="AutoAd Compliance AI Engine",
    version="0.1.0",
    description="Generate and validate automotive ads; block non-compliant outputs.",
)


@app.middleware("http")
async def bind_request_id(request: Request, call_next):
    """Bind a correlation id so every log line in a request shares it."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=uuid.uuid4().hex[:12])
    return await call_next(request)


app.include_router(validate_router, tags=["validation"])
app.include_router(validate_image_router)
app.include_router(generate_router)
app.include_router(review_router)
app.include_router(vehicles_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


# The thin web UI (served last so it doesn't shadow API routes).
app.mount("/ui", StaticFiles(directory=_STATIC_DIR, html=True), name="ui")
