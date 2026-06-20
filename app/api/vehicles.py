"""GET /vehicles — inventory list to populate the UI's vehicle picker."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.tables import Vehicle

router = APIRouter()


class VehicleOut(BaseModel):
    id: int
    year: int
    make: str
    model: str
    trim: str
    dealer_price: Decimal
    stock_number: str


@router.get("/vehicles", response_model=list[VehicleOut], tags=["inventory"])
def list_vehicles(db: Session = Depends(get_db)) -> list[Vehicle]:
    return list(db.scalars(select(Vehicle).order_by(Vehicle.id)))
