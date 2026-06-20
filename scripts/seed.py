"""Synthetic inventory + offer seeder.

Deterministic by design — the same vehicles/offers every run so demos and
golden datasets are reproducible. Run with:

    uv run python -m scripts.seed

Re-running wipes inventory/offer/ad/run data and reinserts it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.db import SessionLocal
from app.models.enums import OfferType, VehicleCondition
from app.models.tables import (
    OEM,
    AdAsset,
    ComplianceRun,
    Dealership,
    Offer,
    ReviewDecision,
    Vehicle,
    Violation,
)
from app.rules import sync

# A fixed VIN stem keeps IDs VIN-shaped (17 chars) but deterministic.
_VIN_STEM = "1HGCM82633A0000"


def _vin(n: int) -> str:
    """Return a 17-char VIN-shaped id seeded by n (deterministic)."""
    return f"{_VIN_STEM}{n:02d}"


def _clear(session) -> None:
    """Remove dependent rows first, then inventory, so FKs stay satisfied."""
    session.execute(delete(ReviewDecision))
    session.execute(delete(Violation))
    session.execute(delete(ComplianceRun))
    session.execute(delete(AdAsset))
    session.execute(delete(Offer))
    session.execute(delete(Vehicle))
    session.execute(delete(Dealership))
    session.execute(delete(OEM))


def seed() -> None:
    today = date.today()
    future = today + timedelta(days=30)

    with SessionLocal() as session:
        _clear(session)

        oem = OEM(name="Honda", brand_guidelines_ref="honda-coop-v1")
        session.add(oem)
        session.flush()

        dealer = Dealership(
            name="Bayview Honda",
            dba_name="Bayview Honda of San Jose",
            oem=oem,
            jurisdiction="US-CA",
        )
        session.add(dealer)
        session.flush()

        # (vehicle kwargs, [offers]) — a small, realistic, deterministic set.
        records: list[tuple[dict, list[Offer]]] = [
            (
                dict(
                    vin=_vin(1),
                    year=2024,
                    make="Honda",
                    model="Civic",
                    trim="Sport",
                    msrp=Decimal("27500.00"),
                    dealer_price=Decimal("26200.00"),
                    mileage=12,
                    condition=VehicleCondition.NEW,
                    stock_number="H24001",
                    body_style="sedan",
                ),
                [
                    Offer(
                        type=OfferType.LEASE,
                        monthly_payment=Decimal("299.00"),
                        term_months=36,
                        due_at_signing=Decimal("2999.00"),
                        residual=Decimal("16500.00"),
                        apr=Decimal("4.90"),
                        expiration_date=future,
                        jurisdiction="US-CA",
                    ),
                ],
            ),
            (
                dict(
                    vin=_vin(2),
                    year=2024,
                    make="Honda",
                    model="Accord",
                    trim="EX-L",
                    msrp=Decimal("34100.00"),
                    dealer_price=Decimal("32750.00"),
                    mileage=8,
                    condition=VehicleCondition.NEW,
                    stock_number="H24002",
                    body_style="sedan",
                ),
                [
                    Offer(
                        type=OfferType.FINANCE,
                        apr=Decimal("3.90"),
                        term_months=60,
                        monthly_payment=Decimal("589.00"),
                        down_payment=Decimal("3000.00"),
                        expiration_date=future,
                        jurisdiction="US-CA",
                    ),
                ],
            ),
            (
                dict(
                    vin=_vin(3),
                    year=2023,
                    make="Honda",
                    model="CR-V",
                    trim="EX",
                    msrp=Decimal("33200.00"),
                    dealer_price=Decimal("31900.00"),
                    mileage=18234,
                    condition=VehicleCondition.CERTIFIED,
                    stock_number="H23003",
                    body_style="suv",
                ),
                [
                    Offer(
                        type=OfferType.CASH,
                        expiration_date=future,
                        jurisdiction="US-CA",
                    ),
                ],
            ),
            (
                dict(
                    vin=_vin(4),
                    year=2022,
                    make="Honda",
                    model="Pilot",
                    trim="Touring",
                    msrp=Decimal("48900.00"),
                    dealer_price=Decimal("44500.00"),
                    mileage=31420,
                    condition=VehicleCondition.USED,
                    stock_number="H22004",
                    body_style="suv",
                ),
                [
                    Offer(
                        type=OfferType.REBATE,
                        down_payment=Decimal("2500.00"),
                        expiration_date=future,
                        jurisdiction="US-CA",
                    ),
                ],
            ),
        ]

        for vkwargs, offers in records:
            vehicle = Vehicle(dealership=dealer, **vkwargs)
            for offer in offers:
                offer.vehicle = vehicle
            session.add(vehicle)

        session.commit()

        # Sync the YAML catalog into versioned rule rows and activate a ruleset
        # snapshot so the API pins every run to it.
        ruleset = sync.sync_and_activate(session)
        session.commit()

        n_vehicles = session.query(Vehicle).count()
        n_offers = session.query(Offer).count()
        print(
            f"Seeded {n_vehicles} vehicles and {n_offers} offers for {dealer.name}; "
            f"activated ruleset '{ruleset.label}' with {len(ruleset.rules)} rules."
        )


if __name__ == "__main__":
    seed()
