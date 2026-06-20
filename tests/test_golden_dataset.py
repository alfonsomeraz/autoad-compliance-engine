"""Golden-dataset integrity (deterministic, no LLM — runs in CI).

Guards that every labeled ad's stored verdict + blocker keys still match what
the rule engine produces from its ground-truth claims. If a rule changes, this
fails until the dataset is rebuilt — preventing silent label drift.
"""

from __future__ import annotations

from app.models.claims import AdClaims, SourceFacts
from app.models.enums import Severity
from app.rules import engine
from app.rules.catalog import load_catalog
from evals.datasets.loader import load_golden

CATALOG = load_catalog()
GOLDEN = load_golden()


def test_dataset_is_reasonably_sized():
    assert len(GOLDEN) >= 40


def test_dataset_covers_all_verdicts():
    verdicts = {ad.expected_verdict for ad in GOLDEN}
    assert verdicts == {"PASS", "FAIL", "REQUIRES_REVIEW"}


def test_labels_match_engine_on_true_claims():
    """Every label must equal engine(true_claims) — the dataset is self-consistent."""
    for ad in GOLDEN:
        claims = AdClaims.model_validate(ad.true_claims)
        source = SourceFacts.model_validate(ad.source_facts)
        result = engine.evaluate(CATALOG, claims, source, jurisdiction=ad.jurisdiction)
        blockers = sorted({f.rule_key for f in result.findings if f.severity is Severity.BLOCKER})
        assert result.verdict.value == ad.expected_verdict, ad.id
        assert blockers == ad.expected_blocker_rule_keys, ad.id


def test_blocker_ads_are_labeled_fail():
    # Any ad with a blocker must be labeled FAIL (verdict logic sanity).
    for ad in GOLDEN:
        if ad.expected_blocker_rule_keys:
            assert ad.expected_verdict == "FAIL", ad.id
