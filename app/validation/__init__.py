"""Validation orchestration: extract -> evaluate -> verdict.

Fetches authoritative vehicle + offer, runs claims extraction, calls the rule
engine, and assembles the verdict + per-rule findings + evidence. Writes the
immutable compliance_run audit record.
"""
