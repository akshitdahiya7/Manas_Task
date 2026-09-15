# REPORT.md - Approach, Decisions and Tradeoffs

How each part of the assignment was approached, what was decided and why, and what the limitations
are. Setup and API examples live in [README.md](README.md); the retraining question is answered in
[DESIGN.md](DESIGN.md).

---

## 1. Verifying the artifacts before writing any code

The supplied artifacts were inspected first, because three things could have invalidated everything
built on top of them. All three turned out to matter:

**The feature order.** The model card says "21 health indicators" but never lists them. The fitted
`StandardScaler` does: `scaler.feature_names_in_` gives the exact names *and* order it was fitted
on. That list is the single source of truth in `backend/app/features.py:FEATURE_ORDER`, and a
mismatch would have produced a service that returns confident nonsense - scaling BMI with
HighChol's mean, and so on, with no error anywhere. A guard in the sample-CSV generator asserts the
two still agree.

**The scikit-learn version.** The random forest was pickled with **scikit-learn 1.9.0**. Loading it
under 1.5.2 produced 17 `InconsistentVersionWarning`s ("Trying to unpickle estimator
DecisionTreeClassifier from version 1.9.0"). scikit-learn does not guarantee correctness across a
pickle version gap, so `requirements.txt` pins 1.9.0, under which it loads silently.

**The Keras output shape.** Reading `config.json` inside the `.keras` archive showed the
architecture without needing to install anything: `Input(21) -> Dense(128, relu) -> Dropout(0.4) ->
Dense(1, sigmoid)`, saved with Keras 3.15.0. The single sigmoid unit means the output *is*
P(diabetes) - a 2-unit softmax would have needed `[:, 1]` indexing instead, and getting that wrong
inverts predictions in a way that is easy to miss.

As a correctness check beyond "it runs", a clearly high-risk and a clearly low-risk profile are
pushed through both models. They separate as they should (RF: 0.89 vs 0.03; MLP: 0.93 vs 0.01),
which is strong evidence the feature ordering and scaling are right. That check is kept as a test
(`test_model_separates_high_and_low_risk`).

## 2. Model loading and the Keras decision

Serving a 58 KB MLP would normally mean adding TensorFlow - roughly 600 MB - to the image. Since the
network is only Dense and Dropout layers, it runs on **Keras 3's inference-only numpy backend**
(`KERAS_BACKEND=numpy`), with no TensorFlow at all.

This was verified rather than assumed. The same `.keras` file was loaded under `tensorflow-cpu`
2.20.0 and under the numpy backend, and both were run on the same 200 random inputs:

| | |
|---|---|
| Max absolute difference | `1.192e-07` |
| Mean absolute difference | `2.422e-08` |
| Identical class decisions at the 0.5 threshold | yes, 200/200 |

The difference is float32 rounding. The supplied artifact is served faithfully - same file, same
weights, same outputs - with a substantially smaller and faster-building image. (Keras' numpy
backend imports `jax` for a few operations, so `jax[cpu]` is a dependency; it is far lighter than
TensorFlow.)

`registry.py` caches loaded artifacts per version behind a lock, so the 21.5 MB forest is read once
per process rather than per request. The active model is warmed at startup, which also keeps a cold
load from being misreported as inference latency - an early version recorded a 3.8 s p95 that was
entirely disk IO.

## 3. The API

**Validation.** One Pydantic model, `PatientFeatures`, with `extra="forbid"` and `StrictInt` fields
carrying per-feature ranges from the BRFSS codebook. Strictness is the point: `"30"` as a string,
`30.5`, `True`, and an unexpected `SmokesCigars` field are all rejected rather than coerced, which
is what "no silent coercion of garbage data" requires. `extra="forbid"` in particular turns a
typo'd field name into a clear 422 instead of a silently ignored input.

**CSV is different, deliberately.** CSV carries no types, so every value arrives as a string and
*something* has to parse it. `_clean_csv_row` parses only exact integers - `"30"` is accepted,
`"30.5"` and `"abc"` are errors - and then runs the parsed row through the same `PatientFeatures`
model, so both paths end up enforcing identical rules.

**Partial CSV failure (an ambiguity in the brief).** The assignment does not say what a CSV with
some bad rows should do. The assumption taken: **score the good rows, report the bad ones per row,
return 200** with `success_count` / `error_count` and a per-row `errors` array. Rejecting a
1,000-row file because row 738 has a blank cell would be worse for the user, and the per-row detail
is what the frontend needs to be useful. A file that cannot be parsed at all is still a 400.

**Errors.** Every failure returns one envelope:

```json
{"error": {"code": "...", "message": "...", "details": [...]}}
```

Handlers in `main.py` cover our own `AppError` hierarchy, Pydantic's `RequestValidationError`
(flattened to one entry per offending field), Starlette's `HTTPException`, and a catch-all for
anything unanticipated - logged with its traceback, returned as a clean 500 with no stack trace.

One bug worth recording: the `HTTPException` handler was originally registered against FastAPI's
subclass, so unmatched routes - which Starlette raises from its *base* class - escaped it and
returned a bare `{"detail": "Not Found"}`. A test asserting the envelope on an unknown route caught
it; the handler is now registered on the Starlette base class and covers both.

## 4. Testing

**72 tests, all passing**, in five files:

| File | Covers |
|---|---|
| `test_inference.py` | Valid single/batch/CSV, metadata completeness, hash stability, version selection, both frameworks serving |
| `test_validation.py` | Missing/extra fields, out-of-range and wrong-type values, malformed and empty CSVs, row/size limits, partial CSV failure |
| `test_model_failures.py` | Corrupt artifact, missing artifact, missing scaler, mid-inference exception, wrong prediction count, unsupported framework, registry caching |
| `test_versioning.py` | Promotion, rollback, the single-production invariant, audit trail, and all RBAC cases |
| `test_persistence.py` | Logs and batches written and read back, filters, metrics aggregates, health |

Tests run against the **real artifacts** with a temporary SQLite database. Using the genuine scaler
and forest is the point - a mocked model would not have caught a feature-order mistake. SQLite keeps
the suite dependency-free; the code uses no Postgres-specific features.

Two choices worth noting. Failure modes are provoked honestly rather than asserted about: a corrupt
artifact is a real file of garbage bytes, and the mid-inference failure monkeypatches
`predict_proba` on the genuinely loaded estimator. And each failure test asserts both the status
code *and* that the response is not a 500 - the requirement is specifically about clean errors
rather than crashes.

Result:

```
72 passed in 15.14s
```

## 5. Versioning and logging design

**Five tables** (`app/db_models.py`):

| Table | Holds |
|---|---|
| `users` | Username, bcrypt hash, role |
| `model_versions` | One row per servable artifact: version, framework, paths, status, training metrics |
| `promotion_events` | Every promotion / rollback / archive: who, when, from, to, why |
| `upload_batches` | One row per CSV or JSON batch submission |
| `inference_logs` | One row per attempted prediction, successes *and* failures |

**Versioning** is database state over immutable files. Artifacts on disk are never written to; the
`status` column (`candidate` -> `production` -> `archived`) decides what serves traffic.
`/api/predict` with no `?version=` resolves to whichever row holds `production`. This is what makes
rollback trivial: the previous artifact never went anywhere.

The "exactly one production model" invariant is maintained by doing both status changes in a single
transaction in `_switch_production` - the incumbent is archived and the target promoted together,
never leaving a window with zero or two production models. A test asserts the invariant directly.

**Logging** writes one `inference_logs` row per prediction, carrying `model_version_id`,
`preprocessing_version` (via the model version), `input_json`, `input_hash`, `predicted_class`,
`probability`, `latency_ms`, `requested_by` and `created_at`. That is enough to answer "what model,
what input, what output, for whom, when" for any historical prediction. Failed inferences are logged
too, with `status='error'` and the message - an error rate is only meaningful if failures are
recorded.

`input_hash` is a SHA-256 of the canonical JSON with sorted keys, so the same record submitted with
differently ordered fields produces the same digest (tested).

## 6. Promotion and rollback

New models arrive as `candidate`. A candidate is loadable and testable on demand via
`?version=`, but serves no default traffic. Promotion requires the **admin** role, accepts a reason,
and writes a `promotion_events` row. `POST /api/models/rollback` restores the most recently archived
version - found via the promotion history rather than a guess - and is likewise admin-only and
recorded.

The full evaluation-and-approval process this is designed to support is in [DESIGN.md](DESIGN.md),
including which parts are implemented here and which are described.

## 7. Frontend

Vite + React with plain JavaScript, `react-router-dom`, `fetch` and hand-written CSS. No TypeScript,
no state library, no component library - at five pages, each would cost more than it returns.

One `api.js` module owns all HTTP: it attaches the token, parses the error envelope and throws a
typed `ApiError` exposing `fieldErrors` keyed by field name. That is what lets the Predict form show
each backend validation message inline next to the offending input, rather than dumping a blob of
JSON. Every page handles loading, error and data states.

Two small affordances for whoever reviews this: the Predict form is pre-filled with a valid record
so it can be submitted in one click, and a *Try an invalid value* button demonstrates the validation
path without hand-editing a field.

## 8. Containerization

Three services. Postgres has a `pg_isready` healthcheck and the backend `depends_on` it with
`condition: service_healthy`, so the backend never races the database on a cold start. The backend
image is `python:3.11-slim`, runs as a non-root user, has its own `/health` healthcheck, and copies
requirements before source so the slow dependency layer caches across code edits. Tests are included
in the image so `docker compose exec backend pytest` works.

The frontend is a multi-stage build - Node builds, nginx serves - and **nginx proxies `/api` to the
backend**. Because the browser only ever talks to one origin, there is no CORS configuration and no
build-time API URL baked into the bundle. That one decision removes a whole category of
"works locally, breaks in Docker" problems.

Compose supplies working defaults via `${VAR:-default}` for every variable, so a fresh clone runs
with no `.env`, while a present `.env` overrides them. Secrets are therefore configurable without
the repo ever carrying real ones.

## 9. Assumptions, tradeoffs and limitations

**Assumptions**

- A CSV with some invalid rows should be partially processed (section 3).
- A `Diabetes_binary` label column in an uploaded CSV is ignored rather than rejected, since exported
  data usually still carries it.
- The decision threshold is 0.5. The model card notes recall matters most clinically, so a lower
  threshold would be defensible - but changing it is a clinical decision, not an implementation
  detail, so the default is left explicit and configurable in one place (`DECISION_THRESHOLD`).
- Batches are capped at 1,000 rows and uploads at 5 MB. Unbounded batches are a denial-of-service
  vector against a synchronous endpoint.

**Tradeoffs**

| Decision | Why | Cost |
|---|---|---|
| Keras numpy backend instead of TensorFlow | ~600 MB and several minutes off every build, outputs verified identical | Would need revisiting for a model using ops the numpy backend lacks |
| `create_all()` instead of Alembic | No migration history to preserve in a take-home | A real deployment needs migrations before the first schema change |
| SQLite for tests, Postgres in compose | Zero-setup test runs; no Postgres-specific SQL is used | Tests would not catch a Postgres-only issue |
| Routers call SQLAlchemy directly | At this size, a repository/service layer is indirection without benefit | Would want extracting if the logic grew |
| Model artifacts committed to the repo | `docker compose up` works offline on a fresh clone | 21.5 MB in git history |
| Synchronous batch inference | Simple and predictable; 1,000 rows score in well under a second | A much larger batch would need a job queue |

**Limitations**

- Auth is demo-grade: seeded accounts, no refresh tokens or rotation, tokens in `localStorage`.
  Sufficient to demonstrate RBAC around promotion; not a production auth system.
- The drift metric watches the *output* distribution, not input features. It flags a shift worth
  investigating; it does not prove drift. Real feature drift monitoring needs the training
  distribution retained for comparison.
- Promotion switches all traffic at once - no canary or staged rollout.
- Metrics are computed per request from the log table. Fine at this scale, wrong at large volume,
  where they should be exported to a time-series store.
- `sample_batch.csv` is synthetic, generated from the fitted scaler's per-feature statistics, because
  the BRFSS dataset is not redistributed with this repo.
- The frontend's feature metadata duplicates `features.py`. Generating it from the backend's OpenAPI
  schema would remove the duplication; for 21 stable fields, the manual copy was the lesser evil.
