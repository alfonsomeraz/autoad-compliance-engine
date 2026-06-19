"""Deterministic rule engine + predicate library.

Pure functions over (AdClaims, source_facts) -> findings. Predicate vocabulary:
claim_present, claim_equals_source, claim_within_tolerance, disclaimer_contains,
expiration_in_future, plus all/any/not combinators. Small, fully unit-tested
vocabulary; breadth comes from more rules, not more predicate types.
"""
