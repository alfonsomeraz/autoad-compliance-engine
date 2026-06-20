"""Rasterize an ad to a PNG so the vision validator has a real image to read.

Pillow-based (no headless-browser infra). The factual fields default to the
authoritative source facts — faithful by construction — but each is
overridable, which is exactly how we synthesize a *tampered* creative (e.g. a
displayed price that doesn't match inventory) for the multimodal money shot.
"""

from __future__ import annotations

import io
from decimal import Decimal

from PIL import Image, ImageDraw, ImageFont

from app.models.claims import AdClaims, SourceFacts

_W, _H = 900, 600
_BG = (11, 31, 58)
_FG = (255, 255, 255)
_ACCENT = (255, 211, 77)
_MUTED = (174, 191, 222)


def _money(value: object) -> str:
    return f"${Decimal(str(value)):,.0f}" if value is not None else ""


_FONT_CANDIDATES = (
    "DejaVuSans-Bold.ttf",  # common on Linux / CI
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    "Arial.ttf",
)


def _font(size: int):
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    # Pillow >=10.1 renders a legible, scalable default at the requested size.
    return ImageFont.load_default(size=size)


def render_ad_image(
    source: SourceFacts,
    claims: AdClaims,
    *,
    display_price: str | None = None,
) -> bytes:
    """Render a PNG ad. By default the price is the authoritative source price;
    pass display_price to override it (to simulate a non-compliant creative)."""
    veh = source.vehicle
    off = source.offer

    headline = " ".join(str(veh.get(k, "")) for k in ("year", "make", "model") if veh.get(k))
    price = display_price if display_price is not None else _money(off.get("effective_price"))

    img = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)
    draw.text((48, 40), headline, font=_font(44), fill=_FG)
    draw.text((48, 100), str(veh.get("trim", "")), font=_font(28), fill=_MUTED)
    draw.text((48, 170), price, font=_font(72), fill=_ACCENT)

    y = 270
    if off.get("monthly_payment") is not None:
        line = f"{_money(off.get('monthly_payment'))}/mo"
        if off.get("term_months"):
            line += f" for {off['term_months']} months"
        draw.text((48, y), line, font=_font(30), fill=_FG)
        y += 44
    if off.get("apr") is not None:
        draw.text((48, y), f"{off['apr']}% APR", font=_font(28), fill=_FG)
        y += 44
    if veh.get("stock_number"):
        draw.text((48, y), f"Stock #{veh['stock_number']}", font=_font(22), fill=_MUTED)
        y += 40

    fine = _font(15)
    fy = _H - 24 * (len(claims.disclaimers) + 1)
    for line in claims.disclaimers:
        draw.text((48, fy), line, font=fine, fill=_MUTED)
        fy += 22

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
