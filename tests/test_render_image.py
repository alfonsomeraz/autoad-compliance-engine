"""Ad-image rasterizer tests (deterministic — no browser, no API)."""

from __future__ import annotations

import io
from decimal import Decimal

from PIL import Image

from app.models.claims import AdClaims, SourceFacts
from app.vision.render_image import render_ad_image

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _source() -> SourceFacts:
    return SourceFacts(
        vehicle={
            "year": 2024,
            "make": "Honda",
            "model": "Civic",
            "trim": "Sport",
            "stock_number": "H24001",
        },
        offer={"effective_price": Decimal("26200"), "monthly_payment": Decimal("299")},
    )


def test_render_returns_a_valid_png():
    data = render_ad_image(_source(), AdClaims(disclaimers=["See dealer for details."]))
    assert data.startswith(_PNG_SIGNATURE)
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"
    assert img.size[0] > 100 and img.size[1] > 100


def test_price_override_produces_a_different_image():
    src = _source()
    faithful = render_ad_image(src, AdClaims())
    tampered = render_ad_image(src, AdClaims(), display_price="$19,999")
    # A different displayed price must change the pixels.
    assert faithful != tampered
