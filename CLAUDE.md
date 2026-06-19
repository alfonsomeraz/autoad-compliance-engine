# CLAUDE.md — AutoAd Compliance AI Engine

Architecture principles and conventions for every session. The full scope lives
in `autoad-compliance-ai-engine-spec.md`; this file is the always-loaded summary.

## Mission

Generate **and** validate automotive dealership ad assets, and **block
non-compliant outputs before they ship**. Return one of `PASS` / `FAIL` /
`REQUIRES_REVIEW` with the exact rules implicated and the evidence behind each
finding. Ambiguous assets route to a human reviewer with a full audit trail.

## The non-negotiable principle

**The LLM never emits the final verdict.**

- The LLM **extracts** structured claims (`AdClaims`) from unstructured ad copy
  or a rendered image. That is all it does for compliance.
- A **deterministic rule engine** produces the verdict by evaluating a
  versioned rule catalog against the extracted claims + authoritative source
  data. The verdict is *code*, not generation — so no hallucinated verdicts are
  possible.
- **LLM-as-judge is quarantined**: it may contribute a signal for *subjective*
  checks only (brand voice / tone). It can **never** override a `blocker` and
  never decides numeric or legal facts.

If a change would let the model decide a verdict, a price, or a legal fact,
it is wrong. Stop and reconsider.

## Verdict logic (deterministic)

- Any unresolved `blocker` ⇒ `FAIL`.
- No blockers, but one or more `warning` findings **or** low-confidence
  extraction ⇒ `REQUIRES_REVIEW`.
- Clean ⇒ `PASS`.

Low extraction confidence is itself a `REQUIRES_REVIEW` trigger — never let a
shaky extraction become a confident `PASS`.

## The recall-over-precision tradeoff

Missing a real violation (false negative) is the costly error; a false positive
merely routes an ad to human review. **Tune for high recall on blocker
violations (target ≥ 0.95)** and favor `REQUIRES_REVIEW` over a risky `PASS`.

## Testing

- Rule-engine logic is pure functions over `(AdClaims, source_facts)` and
  **must** have deterministic `pytest` coverage — fast, no LLM, no flakiness.
- Every new rule ships with fixtures (expected findings) in the **same change**.
- Extraction quality and generation faithfulness are covered by DeepEval suites.
- CI must run the DeepEval gate and fail the build on blocker-recall regression
  or any generation faithfulness failure.
- Write tests in the same change as the code they cover.

## Conventions

- **Pydantic v2 everywhere**; typed agent outputs (enforce the `AdClaims`
  contract via Pydantic AI).
- **Postgres + SQLAlchemy 2.0 + Alembic.** JSONB for rule predicates, extracted
  claims, and evidence. *All* schema changes go through Alembic migrations —
  never hand-edit the DB.
- **Rules are data, not code.** Authored as YAML in `/rules`, stored as DB rows,
  versioned and pinned per run via `ruleset_version`. The predicate vocabulary
  stays small and well-tested; breadth comes from more rules.
- **Structured logging** (structlog) with a run ID on every compliance run for
  audit and traceability. Overrides are always logged, never silent.
- **Provider-swappable LLMs.** Default to the latest Claude models (frontier
  model for generation/extraction, a cheaper model for high-volume extraction /
  eval passes); keep the design vendor-agnostic.
- **Verify current library/SDK APIs against official docs** (Pydantic AI,
  DeepEval, AWS provider) before writing integration code — these move fast and
  the spec's snippets are illustrative, not authoritative.

## Repo layout

```
app/
  api/         FastAPI routes (thin HTTP layer)
  models/      Pydantic + SQLAlchemy models (AdClaims lives here)
  rules/       deterministic rule engine + predicate library
  llm/         Pydantic AI agents (extraction, generation, judge)
  generation/  copy gen + HTML template rendering
  validation/  orchestration: extract -> evaluate -> verdict
  vision/      image extraction (Phase 3)
rules/         rule catalog as YAML (authoring source)
evals/         golden datasets + DeepEval suites (extraction, faithfulness, e2e)
infra/         Terraform (Phase 4)
tests/         pytest — deterministic rule logic, always green
scripts/       synthetic inventory/offer generator
.github/workflows/  CI: pytest + DeepEval gate
```

## Build discipline

Build-first: each phase ships something demoable. Keep every change small and
reviewable. Do not build breadth before the Phase 0 vertical slice
(extraction → rule engine → `POST /validate`) works end to end.

This system assists a compliance team; it is **not legal advice**. Human
approval and `REQUIRES_REVIEW` are first-class features.

## Environment

- Application project (not a published library): `[tool.uv] package = false`.
  Run from the repo root so `app` is importable. Manage deps with `uv sync`;
  dev tooling lives in the `dev` optional-dependency group.
- Python 3.12.
