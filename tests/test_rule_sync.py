"""Rule DB sync + ruleset_version pinning tests.

Rules are authored as YAML but become versioned DB rows; an immutable
ruleset_version snapshots which rules are in force. These pin the upsert,
activation, and round-trip-to-RuleSpec behavior.
"""

from __future__ import annotations

from app.models.enums import Severity
from app.models.tables import Rule, RulesetVersion
from app.rules import sync
from app.rules.schema import RuleSpec

SPEC_A = RuleSpec(
    rule_key="TEST_RULE_A",
    version=1,
    severity=Severity.BLOCKER,
    applies_when={"claim_present": "advertised_price"},
    requirement={"claim_present": "advertised_trim"},
    source_citation="test",
)
SPEC_B = RuleSpec(
    rule_key="TEST_RULE_B",
    version=1,
    severity=Severity.WARNING,
    applies_when={"claim_present": "apr"},
    requirement={"claim_present": "apr"},
    source_citation="test",
)


def test_sync_inserts_rule_rows(db_session):
    rows = sync.sync_rules(db_session, [SPEC_A, SPEC_B])
    assert len(rows) == 2
    assert {r.rule_key for r in rows} == {"TEST_RULE_A", "TEST_RULE_B"}
    # Predicate trees persisted as JSONB.
    a = db_session.query(Rule).filter_by(rule_key="TEST_RULE_A").one()
    assert a.requirement == {"claim_present": "advertised_trim"}


def test_sync_is_idempotent_and_updates_in_place(db_session):
    sync.sync_rules(db_session, [SPEC_A])
    # Re-sync with a changed field at the same (rule_key, version).
    changed = SPEC_A.model_copy(update={"remediation": "new guidance"})
    sync.sync_rules(db_session, [changed])
    rows = db_session.query(Rule).filter_by(rule_key="TEST_RULE_A").all()
    assert len(rows) == 1
    assert rows[0].remediation == "new guidance"


def test_create_ruleset_version_activates_and_deactivates_prior(db_session):
    rows = sync.sync_rules(db_session, [SPEC_A, SPEC_B])
    v1 = sync.create_ruleset_version(db_session, "v1", rows)
    v2 = sync.create_ruleset_version(db_session, "v2", rows)
    db_session.refresh(v1)
    assert v1.is_active is False
    assert v2.is_active is True
    assert sync.get_active_ruleset(db_session).id == v2.id


def test_ruleset_version_snapshots_member_rules(db_session):
    rows = sync.sync_rules(db_session, [SPEC_A, SPEC_B])
    v1 = sync.create_ruleset_version(db_session, "v1", rows)
    assert {r.rule_key for r in v1.rules} == {"TEST_RULE_A", "TEST_RULE_B"}


def test_rulespec_from_row_round_trip(db_session):
    rows = sync.sync_rules(db_session, [SPEC_A])
    spec = sync.rulespec_from_row(rows[0])
    assert spec.rule_key == "TEST_RULE_A"
    assert spec.severity is Severity.BLOCKER
    assert spec.applies_when == {"claim_present": "advertised_price"}


def test_sync_and_activate_loads_yaml_catalog(db_session):
    rv = sync.sync_and_activate(db_session, label="catalog-test")
    assert isinstance(rv, RulesetVersion)
    assert rv.is_active is True
    # The real YAML catalog has several rules.
    assert len(rv.rules) >= 5
