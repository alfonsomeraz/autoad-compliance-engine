"""Rule spec, finding, and evaluation-result types for the deterministic engine.

A `RuleSpec` is the engine's in-memory representation of a rule — data authored
as YAML and (from Milestone 1) loaded from the `rule` DB table. `applies_when`
and `requirement` are predicate trees: nested dicts using the predicate
vocabulary (see app/rules/predicates.py). The engine never executes arbitrary
code; it interprets this restricted vocabulary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import Severity, Verdict


class RuleSpec(BaseModel):
    rule_key: str
    version: int = 1
    jurisdiction: str = "US"
    severity: Severity
    description: str = ""
    # Predicate trees. If applies_when is true and requirement is false, the
    # rule produces a finding.
    applies_when: dict = Field(default_factory=dict)
    requirement: dict = Field(default_factory=dict)
    remediation: str = ""
    source_citation: str = ""


class Finding(BaseModel):
    """One rule that fired (its requirement was not met), with audit evidence."""

    rule_key: str
    severity: Severity
    message: str
    evidence: dict = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """The deterministic output: a verdict plus the findings behind it."""

    verdict: Verdict
    findings: list[Finding] = Field(default_factory=list)
    low_confidence: bool = False
