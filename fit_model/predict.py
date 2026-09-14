"""
Inference wrapper around the trained fit model.

    from fit_model.predict import predict_fit
    predict_fit(height_in=71, category="gown", size=8)
    -> {"small": 0.09, "fit": 0.78, "large": 0.13}

Honest scope: this predicts P(fit outcome) the way RentTheRunway renters
report it — "small" / "fit" / "large" — from body measurements + rental
size/category. It is NOT trained on the scraped Long catalog (which has no
fit-feedback of its own) and "garment measurements" here means rental
size + category, not a tape-measure inseam. See train.py's docstring.
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional

import joblib

from fit_model.features import build_feature_row

MODEL_PATH = Path(__file__).parent / "artifacts" / "fit_model.joblib"


@lru_cache(maxsize=1)
def _load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"{MODEL_PATH} not found — run `python -m fit_model.train` first.")
    return joblib.load(MODEL_PATH)


def predict_fit(
    height_in: float,
    weight_lbs: Optional[float] = None,
    bust_size: Optional[str] = None,
    body_type: str = "missing",
    category: str = "dress",
    size: float = 8,
    age: Optional[float] = None,
    rented_for: str = "missing",
) -> dict:
    """Returns {"small": p, "fit": p, "large": p} summing to ~1.0."""
    model = _load_model()
    row = build_feature_row(
        height_in=height_in, weight_lbs=weight_lbs, bust_size=bust_size,
        body_type=body_type, category=category, size=size, age=age,
        rented_for=rented_for,
    )
    probs = model.predict_proba(row)[0]
    return dict(zip(model.classes_, (round(float(p), 4) for p in probs)))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--height-in", type=float, required=True)
    ap.add_argument("--category", default="dress")
    ap.add_argument("--size", type=float, default=8)
    ap.add_argument("--weight-lbs", type=float)
    ap.add_argument("--body-type", default="missing")
    args = ap.parse_args()

    result = predict_fit(
        height_in=args.height_in, weight_lbs=args.weight_lbs,
        category=args.category, size=args.size, body_type=args.body_type,
    )
    print(result)
