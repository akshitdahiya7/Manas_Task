# MANAS — Diabetes Risk Inference Service

A production-style inference service for the BRFSS 2015 diabetes health indicators models: a
FastAPI backend, a React frontend, and PostgreSQL for persistence, with model versioning, gated
promotion/rollback, and full inference logging.

Both supplied artifacts are served as two registered versions:

| Version | Model | Framework | Status on first run |
|---|---|---|---|
| `v1-rf` | `diabetes_random_forest_tuned.joblib` | scikit-learn | **production** |
| `v2-mlp` | `diabetes_mlp_tuned.keras` | Keras 3 | candidate |

- **[REPORT.md](REPORT.md)** — how each part was approached, design decisions and tradeoffs.
- **[DESIGN.md](DESIGN.md)** — the required answer on retraining after new labelled data arrives.

---

## Quick start

```bash
docker compose up --build
```

Then open:

| | URL |
|---|---|
| Frontend | <http://localhost:3000> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Health check | <http://localhost:8000/health> |

The first build takes a few minutes (Python dependencies). The backend waits for Postgres to pass
its healthcheck, creates its schema, and registers both model versions automatically — there is no
migration or seeding step to run.

### Demo accounts

| Username | Password | Role | Can do |
|---|---|---|---|
| `admin` | `admin123` | admin | everything, including promote and rollback |
| `viewer` | `viewer123` | viewer | predict and read; promotion returns 403 |

These defaults exist so a fresh clone runs with no setup. **Override them in `.env` for anything
that is not local development** — see [Configuration](#configuration).

### Try it in the UI

1. Log in as `admin`.
2. **Predict** — the form is pre-filled with a valid record; press *Predict*. Press *Try an invalid
   value* to see backend validation rendered inline.
3. **Batch** — download the sample CSV from the link on the page and upload it.
4. **History** — see the batch you just uploaded and drill into its rows.
5. **Models & Dashboard** — monitoring tiles, promote `v2-mlp`, watch the active version change,
   then roll back. Log in as `viewer` to confirm those buttons are gone.

---

## Running the tests

```bash
# inside the running stack
docker compose exec backend pytest -v

# or locally
cd backend
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

Tests use a temporary SQLite database and the real model artifacts, so no Postgres is needed. For a
coverage report:

```bash
pytest --cov=app --cov-report=term-missing
```

**Current result: 72 passed.** What is covered is listed in [REPORT.md](REPORT.md#4-testing).

---

## API

All endpoints except `/health` and `/api/auth/login` require `Authorization: Bearer <token>`.

| Method | Path | Role | Purpose |
|---|---|---|---|
| `GET` | `/health` | — | Liveness + database connectivity |
| `POST` | `/api/auth/login` | — | Exchange credentials for a JWT |
| `GET` | `/api/auth/me` | any | Current user and role |
| `POST` | `/api/predict` | any | Single record. `?version=` to pin a model |
| `POST` | `/api/predict/batch` | any | JSON array of records |
| `POST` | `/api/predict/csv` | any | Multipart CSV upload |
| `GET` | `/api/models` | any | All registered versions |
| `GET` | `/api/models/active` | any | The version serving traffic |
| `POST` | `/api/models/{version}/promote` | **admin** | Promote to production |
| `POST` | `/api/models/rollback` | **admin** | Restore the previous version |
| `GET` | `/api/models/promotions` | any | Promotion / rollback audit trail |
| `GET` | `/api/logs` | any | Recent inferences (`limit`, `offset`, `version`, `status`, `mine`) |
| `GET` | `/api/batches` | any | Uploaded batches |
| `GET` | `/api/batches/{id}` | any | One batch with every row's result |
| `GET` | `/api/metrics/summary` | any | Volume, error rate, latency, distribution, drift |

### Example: log in

```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "admin123"}'
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "username": "admin",
  "role": "admin"
}
```

### Example: single prediction

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://localhost:8000/api/predict \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "HighBP": 1, "HighChol": 1, "CholCheck": 1, "BMI": 34, "Smoker": 1,
    "Stroke": 0, "HeartDiseaseorAttack": 0, "PhysActivity": 0, "Fruits": 0,
    "Veggies": 1, "HvyAlcoholConsump": 0, "AnyHealthcare": 1, "NoDocbcCost": 0,
    "GenHlth": 4, "MentHlth": 10, "PhysHlth": 15, "DiffWalk": 1, "Sex": 1,
    "Age": 10, "Education": 4, "Income": 3
  }'
```

```json
{
  "inference_id": 1,
  "predicted_class": 1,
  "predicted_label": "Diabetes or prediabetes",
  "probability": 0.876627214169321,
  "model_version": "v1-rf",
  "preprocessing_version": "v1",
  "timestamp": "2026-09-14T17:06:12.366895",
  "input_hash": "eeb6ee402465df1484728986c0d0be120461c0a9f5340c37863b96d080ba81a5",
  "latency_ms": 112.47,
  "input": { "...": "the validated record, echoed back" }
}
```

`model_version`, `preprocessing_version`, `input_hash` and `timestamp` are together enough to
reproduce any past inference.

Pin a specific model with `?version=v2-mlp`.

### Example: batch prediction

```bash
curl -s -X POST http://localhost:8000/api/predict/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"records": [ {...record one...}, {...record two...} ]}'
```

```json
{
  "batch_id": 1,
  "model_version": "v1-rf",
  "preprocessing_version": "v1",
  "timestamp": "2026-09-14T17:05:40.605062",
  "row_count": 2,
  "success_count": 2,
  "error_count": 0,
  "results": [
    {
      "row_index": 0,
      "status": "success",
      "predicted_class": 1,
      "predicted_label": "Diabetes or prediabetes",
      "probability": 0.876627214169321,
      "input_hash": "eeb6ee402465df1484728986c0d0be120461c0a9f5340c37863b96d080ba81a5"
    },
    {
      "row_index": 1,
      "status": "success",
      "predicted_class": 0,
      "predicted_label": "No diabetes",
      "probability": 0.38974669986784255
    }
  ]
}
```

### Example: CSV upload

```bash
curl -s -X POST http://localhost:8000/api/predict/csv \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@backend/tests/data/sample_batch.csv'
```

Returns the same `BatchResponse` shape. Rows are validated individually — a bad row is reported in
`results` with its errors while the good rows are still scored.

### Example: a validation error

Every error uses one envelope, so a client can render them uniformly:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      { "field": "BMI",  "message": "Input should be less than or equal to 98", "type": "less_than_equal" },
      { "field": "Nope", "message": "Extra inputs are not permitted",           "type": "extra_forbidden" }
    ]
  }
}
```

| Status | When |
|---|---|
| `400` | Unparseable CSV, missing columns, empty file |
| `401` / `403` | Missing or invalid token / insufficient role |
| `404` | Unknown model version, batch or route |
| `413` | Batch row count or upload size over the limit |
| `422` | Schema, type or range violation |
| `503` | Model failed to load, or failed during inference |

---

## Configuration

Settings come from environment variables, with `.env` at the repo root read automatically. Copy the
template and edit:

```bash
cp .env.example .env
```

`.env` is gitignored. `docker-compose.yml` supplies working defaults for every value, so the stack
runs on a fresh clone without one; anything set in `.env` overrides those defaults.

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `manas` | Database container credentials |
| `DATABASE_URL` | `sqlite:///./manas.db` | Local runs only — compose overrides it with the Postgres URL |
| `JWT_SECRET` | `dev-secret-change-me` | **Change this.** Startup logs a warning while it is the placeholder |
| `JWT_EXPIRE_MINUTES` | `480` | Token lifetime |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin123` | Seeded on first start |
| `VIEWER_USERNAME` / `VIEWER_PASSWORD` | `viewer` / `viewer123` | Seeded on first start |
| `MAX_BATCH_ROWS` | `1000` | Rows per batch, else `413` |
| `MAX_UPLOAD_BYTES` | `5242880` | 5 MB upload cap, else `413` |
| `DRIFT_WINDOW` / `DRIFT_THRESHOLD` | `200` / `0.15` | Prediction-drift proxy |

Generate a real secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Local development (without Docker)

**Backend**

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
```

Defaults to SQLite (`backend/manas.db`), so no database server is needed.

**Frontend**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Vite proxies `/api` to `http://localhost:8000`, so the same relative paths work in both setups.

---

## Repository layout

```
├── backend/
│   ├── app/
│   │   ├── main.py          # app wiring + the exception handlers
│   │   ├── features.py      # the 21 features and their valid ranges
│   │   ├── schemas.py       # strict request/response validation
│   │   ├── registry.py      # artifact loading and caching
│   │   ├── predictor.py     # preprocessing + prediction
│   │   ├── db_models.py     # the five tables
│   │   └── routers/         # auth, predict, models, logs, metrics
│   ├── models/              # the committed model artifacts
│   ├── scripts/             # sample-CSV generator
│   ├── tests/               # pytest suite (72 tests)
│   └── Dockerfile
├── frontend/
│   ├── src/pages/           # Login, Predict, Batch, History, Models
│   ├── nginx.conf           # serves the build, proxies /api to the backend
│   └── Dockerfile
├── docker-compose.yml
├── README.md   REPORT.md   DESIGN.md   .env.example
```

Model artifacts are committed deliberately (21.5 MB total, under GitHub's limit) so that
`docker compose up` works on a fresh clone with no download step.

---

## Notes and limitations

- **Keras without TensorFlow.** The supplied `.keras` model is a plain Dense network, so it runs on
  Keras 3's inference-only numpy backend and the image does not need TensorFlow. Verified against
  `tensorflow-cpu` 2.20 on 200 random inputs: max absolute difference `1.19e-07`, identical class
  decisions. See [REPORT.md](REPORT.md#2-model-loading-and-the-keras-decision).
- **scikit-learn is pinned to 1.9.0**, the version the random forest was pickled with. Other
  versions load it with an `InconsistentVersionWarning` and are not guaranteed to be correct.
- **No Alembic.** The schema is created with `create_all()` on startup. With no migration history to
  preserve, a migration tool would be weight without benefit here; a real deployment needs one.
- **The drift metric watches predictions, not features.** It compares the recent positive rate to the
  50/50 training baseline. That flags a shift worth investigating; it does not prove input drift.
- **Auth is demo-grade.** Seeded accounts, no refresh tokens, no password rotation, tokens in
  `localStorage`. Enough to demonstrate RBAC around promotion, not a production auth system.
- **No canary/staged rollout.** Promotion switches all traffic at once. The registry would support a
  split; the routing does not.
- **`sample_batch.csv` is synthetic.** The BRFSS CSV is not redistributed here, so the sample is
  generated from the fitted scaler's own per-feature mean and standard deviation
  (`backend/scripts/generate_sample_csv.py`).
