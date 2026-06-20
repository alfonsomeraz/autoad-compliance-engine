"""Human-in-the-loop review: the queue and the audit-logged decisions.

A reviewer approves/rejects/overrides runs that require review. The compliance
run's deterministic verdict is immutable; decisions are logged alongside it,
never silent.
"""
