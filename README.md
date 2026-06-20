# AutoAd Compliance AI Engine

[![CI](https://github.com/alfonsomeraz/autoad-compliance-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/alfonsomeraz/autoad-compliance-engine/actions/workflows/ci.yml)

> A production-grade AI pipeline that **generates** automotive dealership ad copy
> from inventory data and **validates** any ad against state / OEM / FTC
> compliance rules — **blocking non-compliant outputs before they ship** through
> deterministic rule checks, automated evals, and human-in-the-loop review.

Automotive advertising is one of the most heavily regulated categories of
consumer marketing in the US. A single ad that quotes a lease payment without the
required disclosures, or shows a price that doesn't match the actual vehicle, can
trigger FTC action, state enforcement, or an OEM pulling co-op ad funds. Dealer
groups produce thousands of ads a month — far too many to review by hand.

AutoAd sits between *"generate the ad"* and *"publish the ad."* It returns one of
`PASS` / `FAIL` / `REQUIRES_REVIEW` with the exact rules implicated and the
evidence behind each finding. Non-compliant assets are blocked; ambiguous ones
route to a reviewer with a full audit trail.

> **Not legal advice.** This system encodes a curated approximation of advertising
> rules to assist a compliance team; it does not replace legal review. Human
> approval and `REQUIRES_REVIEW` are first-class features.

---

## The one architectural decision that matters

**The LLM never produces the final compliance verdict.**

The LLM *extracts structured claims* from unstructured ad content into a typed
`AdClaims` object. A *deterministic rule engine* — pure functions, fully
unit-tested — produces the verdict by comparing those claims against
authoritative inventory/offer data. The verdict is **code, not generation**, so a
hallucinated price or a missed disclosure can never become a confident `PASS`.

```mermaid
flowchart LR
    AD[Ad copy or image] --> X[Claims extraction agent<br/>LLM, structured output]
    X --> CLAIMS[AdClaims<br/>typed]
    DB[(Postgres<br/>source of truth)] --> FACTS[SourceFacts]
    CLAIMS --> R[Deterministic rule engine<br/>versioned catalog]
    FACTS --> R
    R --> V[PASS / FAIL / REQUIRES_REVIEW<br/>+ per-rule evidence]
```

Subjective checks (brand voice/tone) may use an LLM-as-judge, but it can only
contribute a *signal* — it can never override a deterministic `blocker`.

### Verdict logic
- Any unresolved `blocker` ⇒ `FAIL`
- No blockers, but a `warning` **or** low-confidence extraction ⇒ `REQUIRES_REVIEW`
- Clean ⇒ `PASS`

### Recall over precision (a deliberate tradeoff)
Missing a real violation (false negative) is the costly error; a false positive
merely routes an ad to a human. So the system is tuned for **high recall on
blocker violations** and favors `REQUIRES_REVIEW` over a risky `PASS`.

---

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
# 1. Install dependencies (application project; uv manages the venv)
uv sync --extra dev

# 2. Start Postgres and apply migrations
docker compose up -d
uv run alembic upgrade head

# 3. Seed synthetic inventory (deterministic)
uv run python -m scripts.seed

# 4. Configure your key
cp .env.example .env   # then set ANTHROPIC_API_KEY

# 5. Run the API + web UI
uv run uvicorn app.main:app --reload
```

Then open **http://localhost:8000** for the thin web UI (validate, generate,
review queue), or **/docs** for the interactive API explorer.

Validate an ad:

```bash
curl -s localhost:8000/validate -H 'content-type: application/json' -d '{
  "vehicle_id": 1,
  "copy_text": "Drive home the Honda Civic Touring for just $249/mo!"
}' | jq
```

The seeded Civic is a **Sport** with no advertised lease disclosures, so this
returns `FAIL` on `ADVERTISED_TRIM_MATCHES_SOURCE` (trim mismatch) and
`LEASE_DISCLOSURE_REQUIRED` (missing Regulation M trigger-term disclosures) —
with the extracted claims and evidence attached.

### The two-minute demo

```bash
uv run python -m scripts.demo
```

Runs the whole pitch against the seeded inventory:

1. **Validate** a deceptive ad ("Civic *Touring* for $249/mo", no disclosures) →
   `FAIL` on the exact rules broken (wrong trim, wrong price, missing CA stock id).
2. **Generate** a compliant ad for the same vehicle → auto-validated to `PASS`,
   self-correcting if the first draft falls short.
3. **Validate an ad image** whose displayed price says `$19,999` while inventory
   says `$26,200` → `FAIL` on `ADVERTISED_PRICE_MATCHES_SOURCE`.

In every act the LLM only *extracts claims* — the deterministic engine decides
the verdict, and each run is written to the audit trail with a structured log
line carrying its run ID.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/validate` | Validate ad copy for a vehicle → verdict + violations |
| `POST` | `/validate-image` | Validate an ad **image** (vision-extract displayed values → cross-check) |
| `POST` | `/generate` | Generate compliant copy (auto-validate + self-correct) |
| `GET` | `/reviews?status=REQUIRES_REVIEW` | The review queue |
| `GET` | `/runs/{id}` | Full audit detail for one compliance run |
| `POST` | `/runs/{id}/decisions` | Log a reviewer decision (approve/reject/override) |
| `GET` | `/ruleset/active` | The active ruleset and its rules (catalog view) |

Every run is pinned to an immutable `ruleset_version`, and reviewer decisions
are appended to the audit trail — the deterministic verdict itself is never
mutated, so overrides are logged, never silent.

### Multimodal validation

Ads can be rendered as HTML/PNG from source data (price/trim/disclaimers
deterministic *by construction*), and any ad **image** can be validated: a
vision model extracts the *displayed* values into the same `AdClaims` schema,
which the same deterministic engine cross-checks against inventory. This catches
"the picture says $19,999 but the offer is $26,200" — proven live in
`evals/deepeval/test_vision_money_shot.py` (tampered image → `FAIL` on
`ADVERTISED_PRICE_MATCHES_SOURCE`).

---

## Testing & evals

```bash
uv run pytest                          # deterministic suite — fast, no API calls
uv run pytest evals/deepeval --no-cov  # live eval (uses ANTHROPIC_API_KEY)
```

Three independently testable surfaces:

| Surface | Tooling | What it proves |
|---|---|---|
| **Rule-logic correctness** | `pytest` (pure functions) | Every predicate + rule fixture; deterministic, always green |
| **Extraction quality** | DeepEval | Recall on trigger-term detection (the dangerous miss) |
| **Generation faithfulness** | DeepEval + field-match | Zero hallucinated facts in generated copy |
| **End-to-end accuracy** | golden set (50 labeled ads) | Confusion matrix + blocker recall over the full pipeline |

**The eval gate** (`evals/deepeval/`, CI-gated) runs the live pipeline over a
golden set of 50 labeled ads and fails the build if blocker recall regresses
below 0.95 or generation hallucinates a fact. Current run:

```
Trigger-term recall: 1.000 (78/78)
Blocker recall:      1.000 (31/31)
Confusion matrix (expected -> predicted):
              PASS: {'PASS': 7,  'FAIL': 0,  'REQUIRES_REVIEW': 0}
              FAIL: {'PASS': 0,  'FAIL': 31, 'REQUIRES_REVIEW': 0}
   REQUIRES_REVIEW: {'PASS': 0,  'FAIL': 0,  'REQUIRES_REVIEW': 12}
```

The golden dataset is built by `scripts/build_golden.py`; a deterministic test
(`tests/test_golden_dataset.py`) guards its labels against drift in CI.

---

## Project layout

```
app/
  api/         FastAPI routes (thin HTTP layer)
  models/      Pydantic + SQLAlchemy models (AdClaims lives here)
  rules/       deterministic rule engine + predicate library + catalog loader
  llm/         Pydantic AI agents (extraction; generation/judge later)
  validation/  orchestration: extract -> evaluate -> verdict
  generation/  copy gen + HTML rendering (Phase 2)
  vision/      image extraction (Phase 3)
rules/         rule catalog as YAML (authoring source)
evals/         golden datasets + DeepEval suites
tests/         pytest — deterministic rule logic, always green
scripts/       synthetic inventory/offer seeder
infra/         Terraform (Phase 4)
```

See [`CLAUDE.md`](CLAUDE.md) for architecture principles and conventions, and
[`autoad-compliance-ai-engine-spec.md`](autoad-compliance-ai-engine-spec.md) for
the full scope and roadmap.

---

## Architecture decisions

The choices that matter, and why:

- **The LLM never emits the verdict.** Fuzzy extraction in, deterministic
  judgment out. The model turns messy ad text/images into a typed `AdClaims`
  object; pure-function rules produce `PASS`/`FAIL`/`REQUIRES_REVIEW`. This is
  what makes the system testable, auditable, and trustworthy enough to *block*.
- **Recall over precision on blockers.** A missed violation is the costly error;
  a false positive only routes an ad to a human. We target ≥ 0.95 blocker recall
  and favor `REQUIRES_REVIEW` over a risky `PASS` (low extraction confidence is
  itself a review trigger). The eval gate enforces this in CI.
- **Rules are data, not code.** Authored as YAML, stored as versioned `rule`
  rows, pinned per run via an immutable `ruleset_version`. The catalog grows
  without redeploys; the predicate *vocabulary* stays small and fully tested.
- **Deterministic by construction for rendered creative.** HTML/image ads are
  populated from source data, so displayed price/trim/disclaimers are faithful
  by design; vision OCR becomes a belt-and-suspenders cross-check, not the sole
  guard.
- **Immutable audit, human override logged.** The verdict on a run is never
  mutated; reviewer approve/reject/override decisions are appended. Every run is
  pinned to its ruleset version and emits a structured log line with its run ID.
- **Provider-swappable, typed agents.** Pydantic AI enforces the `AdClaims`
  contract; models are configured, not hard-coded. v1 runs a synchronous stack
  for simplicity (async is a Phase 4 concern when the queue lands).

## Status

| Phase | Scope | State |
|---|---|---|
| **0** | Vertical slice: data foundation, `AdClaims`, rule engine, extraction, `POST /validate` | ✅ Done |
| **1** | Rules as versioned DB rows + `ruleset_version` pinning, 12-rule catalog (federal + CA + OEM), audit trail + review-queue API | ✅ Done |
| **2** | Copy generation + the eval hero + CI gate | ✅ Done |
| **3** | Multimodal validation (HTML render + vision extraction) | ✅ Done |
| **4** | Production on AWS (Docker, Terraform, async pipeline) | 🚧 Next |

**Tech:** Python 3.12 · FastAPI · Pydantic AI · Pydantic v2 · PostgreSQL +
SQLAlchemy 2.0 + Alembic · DeepEval · Docker.
