"""HTML ad renderer tests.

The renderer populates a template from authoritative source facts, so the
displayed price/trim/stock are faithful by construction. Disclaimers (marketing
copy) are escaped to prevent injection.
"""

from __future__ import annotations

from decimal import Decimal

from app.generation.html import render_ad_html
from app.models.claims import AdClaims, SourceFacts


def _source() -> SourceFacts:
    return SourceFacts(
        vehicle={
            "year": 2024,
            "make": "Honda",
            "model": "Civic",
            "trim": "Sport",
            "stock_number": "H24001",
        },
        offer={
            "effective_price": Decimal("26200"),
            "monthly_payment": Decimal("299"),
            "apr": Decimal("4.90"),
            "term_months": 36,
        },
    )


def test_render_is_an_html_document():
    html = render_ad_html(_source(), AdClaims())
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_render_shows_source_price_trim_and_stock():
    html = render_ad_html(_source(), AdClaims(disclaimers=["See dealer for details."]))
    assert "26,200" in html
    assert "Sport" in html
    assert "H24001" in html
    assert "See dealer for details." in html


def test_render_shows_monthly_payment_when_present():
    html = render_ad_html(_source(), AdClaims())
    assert "299" in html


def test_render_escapes_disclaimer_html():
    html = render_ad_html(_source(), AdClaims(disclaimers=["<script>alert('x')</script>"]))
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
