"""Generate a small sample CSV for trying out batch inference.

The original BRFSS CSV is not redistributed with this repo, so the sample is
drawn from the fitted StandardScaler's own per-feature mean and standard
deviation. Values are clipped and rounded to each feature's valid domain, which
makes rows that are realistic enough to exercise the API without shipping
someone else's dataset.

Usage:
    python scripts/generate_sample_csv.py
"""
import csv
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.features import BINARY_FEATURES, FEATURE_ORDER, feature_bounds  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUTPUTS = [
    BACKEND_DIR / "tests" / "data" / "sample_batch.csv",
    BACKEND_DIR.parent / "frontend" / "public" / "sample_batch.csv",
]
ROWS = 20
SEED = 7


def main() -> None:
    scaler = joblib.load(BACKEND_DIR / "models" / "scaler.joblib")
    if list(scaler.feature_names_in_) != FEATURE_ORDER:
        raise SystemExit("Scaler feature order does not match app.features.FEATURE_ORDER")

    rng = np.random.default_rng(SEED)
    rows = []
    for _ in range(ROWS):
        row = {}
        for name, mean, std in zip(FEATURE_ORDER, scaler.mean_, scaler.scale_):
            low, high = feature_bounds(name)
            if name in BINARY_FEATURES:
                # mean of a 0/1 column is the prevalence of 1s.
                row[name] = int(rng.random() < mean)
            else:
                value = rng.normal(mean, std)
                row[name] = int(np.clip(round(value), low, high))
        rows.append(row)

    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FEATURE_ORDER)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
