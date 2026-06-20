"""The deterministic rule engine — the crown jewel.

`evaluate` is a pure function over (rules, AdClaims, SourceFacts) producing a
verdict + findings. No LLM, no I/O, no hidden state. The verdict is *code*, so
no hallucinated verdicts are possible.

Verdict logic (§8):
  - any unresolved blocker            -> FAIL
  - else any warning OR low-confidence -> REQUIRES_REVIEW
  - else                               -> PASS
"""

from __future__ import annotations

from app.models.claims import AdClaims, SourceFacts
from app.models.enums import Severity, Verdict
from app.rules import predicates
from app.rules.predicates import EvalContext
from app.rules.schema import EvaluationResult, Finding, RuleSpec


def jurisdiction_applies(rule_jurisdiction: str, target: str) -> bool:
    """A rule applies if the target jurisdiction is the rule's jurisdiction or a
    more specific one beneath it. 'US' applies to 'US-CA'; 'US-CA' does not
    apply to a plain 'US' target."""
    return target == rule_jurisdiction or target.startswith(rule_jurisdiction + "-")


def evaluate(
    rules: list[RuleSpec],
    claims: AdClaims,
    source: SourceFacts,
    jurisdiction: str = "US",
) -> EvaluationResult:
    ctx = EvalContext(claims=claims, source=source)
    findings: list[Finding] = []

    for rule in rules:
        if not jurisdiction_applies(rule.jurisdiction, jurisdiction):
            continue
        applies = predicates.evaluate(rule.applies_when, ctx) if rule.applies_when else True
        if not applies:
            continue
        satisfied = predicates.evaluate(rule.requirement, ctx) if rule.requirement else True
        if satisfied:
            continue

        findings.append(
            Finding(
                rule_key=rule.rule_key,
                severity=rule.severity,
                message=rule.remediation or rule.description or rule.rule_key,
                evidence={
                    "applies_when": rule.applies_when,
                    "requirement": rule.requirement,
                    "claims": claims.model_dump(mode="json"),
                },
            )
        )

    low_confidence = claims.is_low_confidence
    verdict = _verdict_for(findings, low_confidence)
    return EvaluationResult(verdict=verdict, findings=findings, low_confidence=low_confidence)


def _verdict_for(findings: list[Finding], low_confidence: bool) -> Verdict:
    if any(f.severity is Severity.BLOCKER for f in findings):
        return Verdict.FAIL
    if low_confidence or any(f.severity is Severity.WARNING for f in findings):
        return Verdict.REQUIRES_REVIEW
    return Verdict.PASS
