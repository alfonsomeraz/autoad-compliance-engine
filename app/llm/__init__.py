"""Pydantic AI agents with typed, structured outputs.

- extraction: free-text / image -> AdClaims
- generation: vehicle + offer -> compliant copy
- judge: LLM-as-judge for subjective checks (tone/brand voice) ONLY; can
  contribute a signal but never override a deterministic blocker.
"""
