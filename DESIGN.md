# DESIGN.md — Handling 1,000 New Labelled Samples After Deployment

> **The question:** You receive 1,000 new labelled samples after deployment. Would your deployed
> model automatically retrain itself? Design the update process.

## Short answer

**No. The deployed model never retrains itself, and nothing about the live service changes when new
labelled data arrives.**

New data is an input to an *offline* process that may eventually produce a new, separately versioned
model. That model only reaches patients after it beats the incumbent on held-out data and a human
approves the switch. In a clinical setting an unattended feedback loop is a patient-safety problem
before it is an engineering one: labels arriving post-deployment are often biased by the model's own
behaviour (clinicians investigate the patients it flagged), so training on them silently can degrade
the model in exactly the population it is failing, with no one watching.

The rest of this document describes the process, and points at the parts already implemented in this
repository.

---

## The pipeline

```
  new labelled data
         │
         ▼
  ┌──────────────┐   frozen, versioned snapshot; never touches the serving path
  │ 1. Ingest    │
  └──────┬───────┘
         ▼
  ┌──────────────┐   offline job, separate process/container from the API
  │ 2. Retrain   │
  └──────┬───────┘
         ▼
  ┌──────────────┐   register as status='candidate' — servable only on request
  │ 3. Register  │
  └──────┬───────┘
         ▼
  ┌──────────────┐   challenger vs champion on a held-out eval set, fixed gates
  │ 4. Validate  │
  └──────┬───────┘
         ▼
  ┌──────────────┐   human decision, recorded with a reason  ← the safety gate
  │ 5. Approve   │
  └──────┬───────┘
         ▼
  ┌──────────────┐   status flips to 'production'; artifact is never overwritten
  │ 6. Deploy    │
  └──────┬───────┘
         ▼
  ┌──────────────┐   watch; one call returns to the previous version
  │ 7. Monitor / │
  │    Rollback  │
  └──────────────┘
```

### 1. Ingest — the data lands somewhere inert

The 1,000 samples are written to a versioned dataset store (object storage with a date-stamped
prefix, or a `labelled_samples` table with a `batch_id`). They are **not** written anywhere the
inference service reads, and the service has no code path that consumes labels.

Before anything is trained, the batch is checked: schema and ranges (the same rules the API
enforces), label balance, duplicates against existing data, and where the labels came from. 1,000
rows against ~70,000 training rows is roughly 1.4% more data — worth accumulating, rarely worth
retraining for on its own. **A fixed trigger is better than an ad-hoc one:** retrain on a schedule,
or when accumulated new data crosses a threshold (say 5–10% of the training set), or when monitoring
shows real degradation — not simply because a batch arrived.

### 2. Retrain — offline, isolated, reproducible

A separate job runs outside the API process: a scheduled CI job, or a manually started container.
It does not share a process, a deployment, or a runtime dependency with the live service, so a
retraining failure cannot affect serving.

The job pins its seed, dataset version, and hyperparameters, and records them alongside the output.
The split matters: the evaluation set is held out **before** the new data is merged, and a slice of
the new data is kept out of training so the candidate is measured on data it has never seen.

### 3. Register — new models land as candidates, not as production

The output is written as a **new artifact file with a new version string** (`v3-rf-2026-09`). It is
registered in the `model_versions` table with `status='candidate'`.

This is already implemented. A candidate is fully loadable and can be exercised on demand via
`POST /api/predict?version=v3-rf-2026-09`, which is how you smoke-test it against real traffic
shapes — but it serves no default traffic, because `/api/predict` without a version resolves to
whichever row holds `status='production'` (`app/services.py:get_active_model`). The repo ships in
exactly this state: `v1-rf` is in production and `v2-mlp` sits as a candidate.

### 4. Validate — challenger vs champion, on gates fixed in advance

Both models are scored on the *same* frozen evaluation set, and the thresholds are written down
**before** the numbers are seen, so a marginal result cannot be argued into a deployment.

For this problem the gates would be:

| Gate | Why |
|---|---|
| **Recall ≥ champion's recall** (primary) | A false negative is a missed diabetes case. The model card puts recall ahead of accuracy for the same reason. |
| Precision not down more than a small agreed margin | Guards against buying recall with a flood of false positives. |
| Accuracy / F1 not materially worse | Overall sanity. |
| **No subgroup regression** — by age band, sex, income | An aggregate win can hide a loss in one group. In a health context this is the gate that matters most, and the one an accuracy-only comparison misses. |
| Calibration (predicted probability ≈ observed rate) | The UI shows a confidence score; it should mean something. |
| Latency and artifact size within budget | An operational, not statistical, constraint. |

A candidate failing any gate stops here. The results are attached to the version record
(`model_versions.metrics`) so the comparison is visible next to the model rather than living in
someone's notebook.

### 5. Approve — an explicit human decision

Passing the gates makes a model *eligible*, not deployed. A person with the admin role promotes it,
and the reason is recorded.

Implemented: `POST /api/models/{version}/promote` requires the `admin` role
(`app/security.py:require_admin`) and accepts a `reason`. A `viewer` calling it gets a 403. Every
promotion writes a `promotion_events` row — version, action, from/to status, who, why, when — which
the UI shows as promotion history. Nothing in the codebase can change the production model without
going through this endpoint.

### 6. Deploy — versioned, never in place

Promotion is a **status change inside one transaction**, not a file operation
(`app/routers/models.py:_switch_production`): the incumbent moves to `archived`, the candidate moves
to `production`, and both events are recorded. The old artifact stays on disk, still registered,
still loadable.

This is the difference between a versioned deployment and overwriting `model.joblib`. With an
overwrite, the previous model is gone and "roll back" means finding an old file and hoping it is the
right one. Here, rollback is a state change against a model that never left the registry. Because
the `production` row is the single source of truth, the switch is atomic from the API's point of
view — in-flight requests finish on the model they started with, and the next request picks up the
new one.

### 7. Monitor and roll back

After promotion, watch error rate, latency, and prediction distribution — `GET /api/metrics/summary`
provides these, including a prediction-drift proxy against the 50/50 training baseline. Ground-truth
metrics (recall in the field) need labels and therefore lag; the fast signals are operational.

If the new version underperforms, `POST /api/models/rollback` restores the most recently archived
version and records the reason. Recovery is one call, and the rollback itself appears in the audit
trail. A staged rollout — candidate serving a small share of traffic before the full switch — is the
natural next step; the registry already supports it, the routing does not, and that is noted as a
limitation rather than pretended.

---

## Why not continuous automatic retraining

The assignment asks specifically about this, so, plainly:

1. **Feedback loops.** The model influences which patients get investigated, so post-deployment
   labels are shaped by its own predictions. Training on them amplifies existing bias instead of
   correcting it.
2. **Silent failure.** An automatic pipeline that quietly degrades has no natural moment where a
   human looks at it. The gates above exist to create that moment.
3. **Poisoning and pipeline bugs.** 1,000 mislabelled or adversarial rows should not be able to
   reach production without anyone reviewing them.
4. **Accountability and traceability.** In a clinical context you must be able to answer "which model
   produced this prediction, on what data, approved by whom?" That is why every inference stores its
   `model_version`, `preprocessing_version` and `input_hash`, and every deployment writes a
   `promotion_events` row.
5. **Regulatory reality.** Clinical decision-support tools are generally validated as a fixed
   version. A model that mutates itself is a different model from the one that was validated.

The design keeps the useful part of continuous learning — new data genuinely improves the model over
time — while putting a person, a comparison, and an audit record between that data and a patient.

---

## What is implemented here vs. what is described

Being explicit, since the difference matters:

**Implemented in this repo:** the candidate/production/archived lifecycle; version-pinned inference;
admin-gated promotion and rollback; the promotion/rollback audit trail; immutable artifacts;
per-inference logging with model version, preprocessing version and input hash; operational
monitoring with a drift proxy.

**Described but not built** (out of scope for a take-home, and called out rather than implied): the
ingestion store and retraining job; automated computation of the challenger-vs-champion gates;
subgroup and calibration analysis; staged/canary traffic splitting. The registry schema is designed
so these attach to it without restructuring — a retraining job's only contract with the service is
"write an artifact, insert a `candidate` row".
