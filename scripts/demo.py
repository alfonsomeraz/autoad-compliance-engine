"""End-to-end demo — the whole pitch in under two minutes.

Runs the live pipeline against the seeded inventory:
  1. VALIDATE a deceptive ad        -> blocked (FAIL) with the exact rules
  2. GENERATE a compliant ad        -> auto-validated to PASS (self-correct)
  3. VALIDATE a tampered ad IMAGE    -> blocked on a displayed-price mismatch

Prereqs: docker compose up -d && uv run alembic upgrade head &&
         uv run python -m scripts.seed, plus ANTHROPIC_API_KEY in .env.

    uv run python -m scripts.demo
"""

from __future__ import annotations

from app.db import SessionLocal
from app.generation.agent import llm_generator
from app.generation.service import generate_compliant_ad
from app.llm.extraction import llm_extractor
from app.models.claims import AdClaims
from app.models.tables import Vehicle
from app.validation.orchestrator import (
    build_source_facts,
    validate_ad,
    validate_ad_image,
)
from app.vision.extraction import llm_vision_extractor
from app.vision.render_image import render_ad_image

RULE = "=" * 70


def _heading(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def main() -> None:
    with SessionLocal() as db:
        civic = db.query(Vehicle).filter(Vehicle.model == "Civic").first()
        if civic is None:
            raise SystemExit("No inventory — run: uv run python -m scripts.seed")
        print(
            f"Vehicle #{civic.id}: {civic.year} {civic.make} {civic.model} "
            f"{civic.trim} — dealer price ${civic.dealer_price:,.0f}, stock {civic.stock_number}"
        )

        _heading("1. VALIDATE a deceptive ad (wrong trim, $249/mo, no disclosures)")
        bad_copy = "Drive home the Honda Civic Touring for just $249/mo! Hurry in."
        print(f"Ad: {bad_copy!r}")
        run = validate_ad(db, vehicle_id=civic.id, copy_text=bad_copy)
        print(f"\n-> VERDICT: {run.status.value}")
        for v in run.violations:
            print(f"   [{v.severity.value}] {v.rule_key}")

        _heading("2. GENERATE a compliant ad (auto-validate + self-correct)")
        outcome = generate_compliant_ad(
            db,
            vehicle_id=civic.id,
            generator=llm_generator,
            extractor=llm_extractor,
        )
        print(f"-> VERDICT: {outcome.verdict.value} after {outcome.attempts} attempt(s)\n")
        print(outcome.copy_text)

        _heading("3. VALIDATE a tampered ad IMAGE ($19,999 displayed != inventory)")
        source = build_source_facts(civic, civic.offers[0] if civic.offers else None)
        image = render_ad_image(
            source,
            AdClaims(disclaimers=["See dealer for details."]),
            display_price="$19,999",
        )
        img_run = validate_ad_image(
            db,
            vehicle_id=civic.id,
            image_bytes=image,
            media_type="image/png",
            vision_extractor=llm_vision_extractor,
        )
        print(f"-> VERDICT: {img_run.status.value}")
        for v in img_run.violations:
            print(f"   [{v.severity.value}] {v.rule_key}")

        print(
            f"\n{RULE}\nThe LLM extracted claims; the deterministic engine decided every verdict.\n{RULE}"
        )


if __name__ == "__main__":
    main()
