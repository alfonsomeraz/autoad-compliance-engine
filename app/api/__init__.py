"""FastAPI HTTP layer — thin orchestration over generation, validation, review.

Routes live here; business logic lives in the validation/generation/rules
packages. Endpoints: POST /validate (Phase 0), generation + review (later).
"""
