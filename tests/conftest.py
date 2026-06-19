"""Shared pytest fixtures.

`db_session` binds a Session to a connection inside an outer transaction that is
always rolled back, so tests that write (including code that calls commit()) are
fully isolated. Uses SQLAlchemy 2.0's join_transaction_mode="create_savepoint".
Requires the local Postgres (docker-compose) to be running.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models.enums import OfferType, VehicleCondition
from app.models.tables import Dealership, OEM, Offer, Vehicle


@pytest.fixture
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def civic(db_session) -> Vehicle:
    """A seeded-style 2024 Civic Sport (dealer_price 26200) with a $299 lease,
    in a US-CA dealership. Created inside the rolled-back test transaction."""
    oem = OEM(name="Honda (test fixture)")
    dealer = Dealership(name="Test Honda", oem=oem, jurisdiction="US-CA")
    vehicle = Vehicle(
        dealership=dealer,
        vin="1HGCM82633A000999",
        year=2024,
        make="Honda",
        model="Civic",
        trim="Sport",
        msrp=Decimal("27500.00"),
        dealer_price=Decimal("26200.00"),
        mileage=12,
        condition=VehicleCondition.NEW,
        stock_number="TST001",
        body_style="sedan",
    )
    Offer(
        vehicle=vehicle,
        type=OfferType.LEASE,
        monthly_payment=Decimal("299.00"),
        term_months=36,
        due_at_signing=Decimal("2999.00"),
        apr=Decimal("4.90"),
        jurisdiction="US-CA",
    )
    db_session.add(vehicle)
    db_session.flush()
    return vehicle
