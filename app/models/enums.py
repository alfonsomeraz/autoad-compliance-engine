"""Shared enums used across DB models, claims, and the rule engine."""

from __future__ import annotations

from enum import StrEnum


class Verdict(StrEnum):
    """Final compliance verdict for a run."""

    PASS = "PASS"
    FAIL = "FAIL"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class Severity(StrEnum):
    """Rule severity. Only a `blocker` can drive a FAIL."""

    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


class OfferType(StrEnum):
    LEASE = "lease"
    FINANCE = "finance"
    CASH = "cash"
    REBATE = "rebate"


class Channel(StrEnum):
    GOOGLE = "google"
    META = "meta"
    DISPLAY = "display"
    EMAIL = "email"


class AssetFormat(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    HTML = "html"


class PriceType(StrEnum):
    """How a price figure is being presented in the ad."""

    CASH = "cash"
    LEASE_MONTHLY = "lease_monthly"
    FINANCE_MONTHLY = "finance_monthly"
    MSRP = "msrp"
    UNKNOWN = "unknown"


class VehicleCondition(StrEnum):
    NEW = "new"
    USED = "used"
    CERTIFIED = "certified"


class ReviewDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    OVERRIDE = "override"
