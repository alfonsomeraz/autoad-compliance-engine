"""AutoAd Compliance AI Engine.

Generate + validate automotive ad assets, blocking non-compliant outputs.

Core principle: the LLM never emits the final verdict. The LLM extracts a
typed `AdClaims` object from unstructured ad content; the deterministic rule
engine produces the PASS / FAIL / REQUIRES_REVIEW verdict.
"""
