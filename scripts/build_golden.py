"""Generate the golden dataset of labeled ads.

We construct ads from ground-truth claims (so the true claims are known by
construction), render matching ad copy, and derive each label (expected verdict
+ blocker rule keys) by running the deterministic rule engine on the true
claims. Extraction quality is then the thing under test: does the LLM recover
these claims from the rendered copy, and does the pipeline reach the same
verdict?

    uv run python -m scripts.build_golden    # writes evals/datasets/golden.json
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from app.models.claims import AdClaims, SourceFacts
from app.models.enums import Severity
from app.rules import engine
from app.rules.catalog import load_catalog
from evals.datasets.loader import GOLDEN_PATH, GoldenAd

CATALOG = load_catalog()
FUTURE = date.today() + timedelta(days=30)
PAST = date.today() - timedelta(days=5)

# (vehicle, offer) base inventory. offer.type drives which disclosures apply.
BASES: list[tuple[dict, dict]] = [
    (
        {
            "year": 2024,
            "make": "Honda",
            "model": "Civic",
            "trim": "Sport",
            "msrp": Decimal("27500"),
            "dealer_price": Decimal("26200"),
            "stock_number": "H24001",
            "vin": "1HGCM82633A000001",
            "condition": "new",
        },
        {
            "type": "lease",
            "monthly_payment": Decimal("299"),
            "term_months": 36,
            "due_at_signing": Decimal("2999"),
            "apr": Decimal("4.90"),
        },
    ),
    (
        {
            "year": 2024,
            "make": "Honda",
            "model": "Accord",
            "trim": "EX-L",
            "msrp": Decimal("34100"),
            "dealer_price": Decimal("32750"),
            "stock_number": "H24002",
            "vin": "1HGCM82633A000002",
            "condition": "new",
        },
        {
            "type": "lease",
            "monthly_payment": Decimal("389"),
            "term_months": 39,
            "due_at_signing": Decimal("3499"),
            "apr": Decimal("5.10"),
        },
    ),
    (
        {
            "year": 2025,
            "make": "Honda",
            "model": "CR-V",
            "trim": "EX",
            "msrp": Decimal("33200"),
            "dealer_price": Decimal("31900"),
            "stock_number": "H25003",
            "vin": "1HGCM82633A000003",
            "condition": "new",
        },
        {
            "type": "lease",
            "monthly_payment": Decimal("345"),
            "term_months": 36,
            "due_at_signing": Decimal("3199"),
            "apr": Decimal("4.50"),
        },
    ),
    (
        {
            "year": 2024,
            "make": "Honda",
            "model": "Pilot",
            "trim": "Touring",
            "msrp": Decimal("48900"),
            "dealer_price": Decimal("46500"),
            "stock_number": "H24004",
            "vin": "1HGCM82633A000004",
            "condition": "new",
        },
        {
            "type": "finance",
            "monthly_payment": Decimal("689"),
            "term_months": 60,
            "down_payment": Decimal("4000"),
            "apr": Decimal("3.90"),
        },
    ),
    (
        {
            "year": 2025,
            "make": "Honda",
            "model": "HR-V",
            "trim": "LX",
            "msrp": Decimal("26500"),
            "dealer_price": Decimal("25100"),
            "stock_number": "H25005",
            "vin": "1HGCM82633A000005",
            "condition": "new",
        },
        {
            "type": "finance",
            "monthly_payment": Decimal("459"),
            "term_months": 60,
            "down_payment": Decimal("2500"),
            "apr": Decimal("4.20"),
        },
    ),
    (
        {
            "year": 2023,
            "make": "Honda",
            "model": "Passport",
            "trim": "EX-L",
            "msrp": Decimal("43000"),
            "dealer_price": Decimal("39950"),
            "stock_number": "H23006",
            "vin": "1HGCM82633A000006",
            "condition": "certified",
        },
        {"type": "cash"},
    ),
    (
        {
            "year": 2022,
            "make": "Honda",
            "model": "Odyssey",
            "trim": "EX",
            "msrp": Decimal("38500"),
            "dealer_price": Decimal("33900"),
            "stock_number": "H22007",
            "vin": "1HGCM82633A000007",
            "condition": "used",
        },
        {"type": "rebate", "down_payment": Decimal("2500")},
    ),
]


def _source(vehicle: dict, offer: dict) -> SourceFacts:
    off = {"effective_price": vehicle["dealer_price"], **offer}
    return SourceFacts(vehicle=dict(vehicle), offer=off)


def _compliant(vehicle: dict, offer: dict) -> AdClaims:
    disclaimers = [
        "Advertised price excludes government fees and taxes.",
        "See dealer for details.",
    ]
    c = AdClaims(
        advertised_price=vehicle["dealer_price"],
        trim_claimed=vehicle["trim"],
        stock_number_claimed=vehicle["stock_number"],
        expiration_date=FUTURE,
        disclaimers=disclaimers,
    )
    if offer["type"] == "lease":
        c.lease_monthly_payment = offer["monthly_payment"]
        c.lease_term_months = offer["term_months"]
        c.due_at_signing = offer["due_at_signing"]
        c.apr = offer["apr"]
        c.disclaimers += [
            "Lessee is responsible for excess wear and mileage.",
            "Financing available for well-qualified buyers.",
        ]
    elif offer["type"] == "finance":
        c.finance_monthly_payment = offer["monthly_payment"]
        c.finance_term_months = offer["term_months"]
        c.down_payment = offer["down_payment"]
        c.apr = offer["apr"]
        c.disclaimers += ["Financing available for well-qualified buyers."]
    return c


def _render(claims: AdClaims, vehicle: dict) -> str:
    trim = claims.trim_claimed or vehicle["trim"]
    lines = [f"{vehicle['year']} {vehicle['make']} {vehicle['model']} {trim}!"]
    if claims.advertised_price is not None:
        lines.append(f"Yours for ${claims.advertised_price:,.0f}.")
    if claims.lease_monthly_payment is not None:
        s = f"Lease for ${claims.lease_monthly_payment:,.0f}/mo"
        if claims.lease_term_months:
            s += f" for {claims.lease_term_months} months"
        if claims.due_at_signing is not None:
            s += f", ${claims.due_at_signing:,.0f} due at signing"
        lines.append(s + ".")
    if claims.finance_monthly_payment is not None:
        s = f"Finance for ${claims.finance_monthly_payment:,.0f}/mo"
        if claims.finance_term_months:
            s += f" for {claims.finance_term_months} months"
        if claims.down_payment is not None:
            s += f" with ${claims.down_payment:,.0f} down"
        lines.append(s + ".")
    if claims.apr is not None:
        lines.append(f"{claims.apr}% APR.")
    if claims.stock_number_claimed:
        lines.append(f"Stock #{claims.stock_number_claimed}.")
    if claims.expiration_date:
        lines.append(f"Offer expires {claims.expiration_date:%B %d, %Y}.")
    lines.extend(claims.disclaimers)
    return "\n".join(lines)


def _without_lessee(disclaimers: list[str]) -> list[str]:
    return [d for d in disclaimers if "lessee" not in d.lower()]


def _without_see_dealer(disclaimers: list[str]) -> list[str]:
    return [d for d in disclaimers if "see dealer" not in d.lower()]


def _scenarios(vehicle: dict, offer: dict) -> list[tuple[str, AdClaims]]:
    """Return (scenario_name, claims) variants applicable to this offer type."""
    out: list[tuple[str, AdClaims]] = [("compliant", _compliant(vehicle, offer))]

    wrong_trim = _compliant(vehicle, offer)
    wrong_trim.trim_claimed = "Touring" if vehicle["trim"] != "Touring" else "Sport"
    out.append(("wrong_trim", wrong_trim))

    wrong_price = _compliant(vehicle, offer)
    wrong_price.advertised_price = vehicle["dealer_price"] - Decimal("2000")
    out.append(("wrong_price", wrong_price))

    expired = _compliant(vehicle, offer)
    expired.expiration_date = PAST
    out.append(("expired_offer", expired))

    missing_stock = _compliant(vehicle, offer)
    missing_stock.stock_number_claimed = None
    out.append(("missing_ca_stock_number", missing_stock))

    if offer["type"] in ("lease", "finance"):
        wrong_apr = _compliant(vehicle, offer)
        wrong_apr.apr = (wrong_apr.apr or Decimal("0")) + Decimal("2.00")
        out.append(("wrong_apr", wrong_apr))

        missing_oem = _compliant(vehicle, offer)
        missing_oem.disclaimers = _without_see_dealer(missing_oem.disclaimers)
        out.append(("missing_oem_disclaimer", missing_oem))

    if offer["type"] == "lease":
        miss = _compliant(vehicle, offer)
        miss.due_at_signing = None
        miss.lease_term_months = None
        miss.disclaimers = _without_lessee(miss.disclaimers)
        out.append(("missing_lease_disclosure", miss))

    if offer["type"] == "finance":
        miss = _compliant(vehicle, offer)
        miss.apr = None
        miss.finance_term_months = None
        miss.down_payment = None
        out.append(("missing_finance_disclosure", miss))

    return out


def build() -> list[GoldenAd]:
    entries: list[GoldenAd] = []
    for idx, (vehicle, offer) in enumerate(BASES):
        source = _source(vehicle, offer)
        for scenario, claims in _scenarios(vehicle, offer):
            result = engine.evaluate(CATALOG, claims, source, jurisdiction="US-CA")
            blockers = sorted(
                {f.rule_key for f in result.findings if f.severity is Severity.BLOCKER}
            )
            entries.append(
                GoldenAd(
                    id=f"{vehicle['model'].lower()}-{idx}-{scenario}",
                    scenario=scenario,
                    jurisdiction="US-CA",
                    source_facts=source.model_dump(mode="json"),
                    ad_copy=_render(claims, vehicle),
                    true_claims=claims.model_dump(mode="json"),
                    expected_verdict=result.verdict.value,
                    expected_blocker_rule_keys=blockers,
                )
            )
    return entries


def main() -> None:
    entries = build()
    GOLDEN_PATH.write_text(json.dumps([e.model_dump() for e in entries], indent=2) + "\n")
    verdicts = {}
    for e in entries:
        verdicts[e.expected_verdict] = verdicts.get(e.expected_verdict, 0) + 1
    print(f"Wrote {len(entries)} labeled ads to {GOLDEN_PATH}")
    print(f"Verdict distribution: {verdicts}")


if __name__ == "__main__":
    main()
