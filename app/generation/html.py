"""Render an ad as an HTML template populated from authoritative source data.

Because the displayed price/trim/stock come straight from `SourceFacts`, the
rendered ad is faithful to inventory *by construction* — there is no model in
this path to hallucinate a number. Marketing disclaimers are HTML-escaped. The
HTML can be rasterized to an image (see scripts/render_image.py) and fed to the
vision validator as a belt-and-suspenders cross-check.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from app.models.claims import AdClaims, SourceFacts

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; background: #0b1f3a; }}
  .ad {{ width: 800px; color: #fff; padding: 48px; }}
  .headline {{ font-size: 40px; font-weight: 800; margin: 0 0 8px; }}
  .trim {{ font-size: 22px; color: #8fb4ff; margin: 0 0 24px; }}
  .price {{ font-size: 56px; font-weight: 800; color: #ffd34d; }}
  .terms {{ font-size: 22px; margin: 12px 0; }}
  .stock {{ font-size: 16px; color: #c9d6ef; margin-top: 8px; }}
  .fine-print {{ font-size: 12px; color: #aebfde; margin-top: 28px; line-height: 1.5; }}
</style>
</head>
<body>
  <div class="ad">
    <p class="headline">{headline}</p>
    <p class="trim">{trim_line}</p>
    <p class="price">{price}</p>
    <p class="terms">{terms}</p>
    <p class="stock">{stock}</p>
    <div class="fine-print">{fine_print}</div>
  </div>
</body>
</html>
"""


def _money(value: object) -> str:
    if value is None:
        return ""
    return f"${Decimal(str(value)):,.0f}"


def render_ad_html(source: SourceFacts, claims: AdClaims) -> str:
    """Render an HTML ad. Factual fields come from `source` (authoritative);
    disclaimers come from `claims` and are escaped."""
    veh = source.vehicle
    off = source.offer

    headline_bits = [veh.get("year"), veh.get("make"), veh.get("model")]
    headline = escape(" ".join(str(b) for b in headline_bits if b))
    trim_line = escape(str(veh.get("trim", "")))
    price = escape(_money(off.get("effective_price")))

    terms_parts: list[str] = []
    if off.get("monthly_payment") is not None:
        line = f"{_money(off.get('monthly_payment'))}/mo"
        if off.get("term_months"):
            line += f" for {escape(str(off['term_months']))} months"
        terms_parts.append(line)
    if off.get("apr") is not None:
        terms_parts.append(f"{escape(str(off['apr']))}% APR")
    terms = escape(" · ".join(terms_parts))

    stock = escape(f"Stock #{veh['stock_number']}") if veh.get("stock_number") else ""
    fine_print = "<br>".join(escape(d) for d in claims.disclaimers)

    return _TEMPLATE.format(
        headline=headline,
        trim_line=trim_line,
        price=price,
        terms=terms,
        stock=stock,
        fine_print=fine_print,
    )
