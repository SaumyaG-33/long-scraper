"""
Train a fit-probability classifier on the RentTheRunway clothing-fit dataset.

This is a real, labeled dataset (192,544 rental reviews with body measurements
+ actual fit outcome: "fit" / "small" / "large" — Misra et al., RecSys 2018).
It is NOT the scraped Long catalog: the scraped retailers have no fit-feedback
loop of their own (no returns data, no "ran small" reviews), so there is
nothing in-house to train a real fit model on. This model is trained on
external, real customer fit-feedback data, then applied to (user height/
weight/measurements, garment category/size) pairs at inference time — see
predict.py.

Usage:
    python -m fit_model.download_data      # once, pulls the ~31MB dataset
    python -m fit_model.train               # trains + evaluates + saves

Honest scope: "garment measurements" here means rental size + category, not
physical garment dimensions (RentTheRunway doesn't publish those either —
almost no retailer does). "Body proportions" means height/weight/bust/body
type, as reported by renters.
"""
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.utils.class_weight import compute_sample_weight

from fit_model.features import (
    ALL_FEATURE_COLS, CATEGORICAL_COLS, NUMERIC_COLS, TARGET_COL, build_features,
)

HERE = Path(__file__).parent
DATA_PATH = HERE / "data" / "renttherunway_final_data.json"
MODEL_PATH = HERE / "artifacts" / "fit_model.joblib"
METRICS_PATH = HERE / "artifacts" / "metrics.json"


def load_raw() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DATA_PATH} not found — run `python -m fit_model.download_data` first."
        )
    return pd.read_json(DATA_PATH, lines=True)


def build_pipeline() -> Pipeline:
    preprocess = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), NUMERIC_COLS),
        ("cat", Pipeline([
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), CATEGORICAL_COLS),
    ])
    model = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_depth=6, random_state=42,
    )
    return Pipeline([("preprocess", preprocess), ("model", model)])


def main():
    print("loading raw data...")
    raw = load_raw()
    print(f"  {len(raw)} rows, fit distribution:\n{raw[TARGET_COL].value_counts(normalize=True)}")

    X = build_features(raw)
    y = raw[TARGET_COL]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\ntrain={len(X_train)}  test={len(X_test)}")

    pipe = build_pipeline()
    print("\ntraining HistGradientBoostingClassifier...")
    # "fit" is ~74% of the data; without rebalancing the model just learns to
    # always predict the majority class (74% accuracy, ~1% recall on
    # small/large). Weight samples inversely to class frequency instead.
    sample_weight = compute_sample_weight("balanced", y_train)
    pipe.fit(X_train, y_train, model__sample_weight=sample_weight)

    y_pred = pipe.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    print("\n" + classification_report(y_test, y_pred))
    print("confusion matrix (rows=true, cols=pred), labels =", sorted(y.unique()))
    print(confusion_matrix(y_test, y_pred, labels=sorted(y.unique())))

    print("\ncomputing permutation importance on a 5k-row sample (this takes a bit)...")
    sample_idx = X_test.sample(n=min(5000, len(X_test)), random_state=42).index
    perm = permutation_importance(
        pipe, X_test.loc[sample_idx], y_test.loc[sample_idx],
        n_repeats=5, random_state=42, n_jobs=-1,
    )
    importances = sorted(
        zip(ALL_FEATURE_COLS, perm.importances_mean), key=lambda t: -t[1]
    )
    print("\nfeature importance (permutation, drop in accuracy when shuffled):")
    for name, score in importances:
        print(f"  {name:<15} {score:+.4f}")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, MODEL_PATH)
    metrics = {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "classification_report": report,
        "permutation_importance": {name: score for name, score in importances},
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"\nsaved model -> {MODEL_PATH}")
    print(f"saved metrics -> {METRICS_PATH}")


if __name__ == "__main__":
    main()
