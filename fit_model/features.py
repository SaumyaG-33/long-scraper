"""
Feature parsing for the RentTheRunway clothing-fit dataset
(Misra et al., "Decomposing fit semantics for product size recommendation
in metric spaces", RecSys 2018 — https://cseweb.ucsd.edu/~jmcauley/datasets.html#clothing_fit).

Raw fields are free-text-ish ("5' 8\"", "137lbs", "34d+") — this module turns
them into the numeric/categorical columns the model actually trains on.

NUMERIC_COLS + CATEGORICAL_COLS define the exact feature contract used by
both train.py and predict.py, so inference can't silently drift from
training.
"""
import re

import pandas as pd

HEIGHT_RE = re.compile(r"(\d+)'\s*(\d+)\"?")
BUST_RE = re.compile(r"(\d+)\s*([a-zA-Z/+]+)")

# Ordinal cup mapping. Not every notation in the dataset appears here, but
# every one we saw during exploration does; unmapped values fall back to a
# mid-range value rather than crashing the pipeline.
CUP_ORDER = ["aa", "a", "b", "c", "d", "d+", "dd", "ddd", "ddd/e", "e", "e+", "ee", "f", "g", "h", "i", "j"]
CUP_ORDINAL = {c: i + 1 for i, c in enumerate(CUP_ORDER)}
CUP_FALLBACK = CUP_ORDINAL["d"]

NUMERIC_COLS = ["height_in", "weight_lbs", "age", "bust_band", "cup_ordinal", "size"]
CATEGORICAL_COLS = ["body type", "category", "rented for"]
ALL_FEATURE_COLS = NUMERIC_COLS + CATEGORICAL_COLS
TARGET_COL = "fit"


def parse_height(value) -> float:
    """"5' 8\"" -> 68.0 (inches)."""
    if not isinstance(value, str):
        return float("nan")
    m = HEIGHT_RE.search(value)
    if not m:
        return float("nan")
    feet, inches = int(m.group(1)), int(m.group(2))
    return feet * 12 + inches


def parse_weight(value) -> float:
    """"137lbs" -> 137.0"""
    if not isinstance(value, str):
        return float("nan")
    m = re.search(r"(\d+(?:\.\d+)?)", value)
    return float(m.group(1)) if m else float("nan")


def parse_bust_size(value):
    """"34d+" -> (34.0, cup_ordinal). Missing/unrecognised -> (nan, nan)."""
    if not isinstance(value, str):
        return float("nan"), float("nan")
    m = BUST_RE.match(value.strip())
    if not m:
        return float("nan"), float("nan")
    band = float(m.group(1))
    cup = m.group(2).lower()
    return band, float(CUP_ORDINAL.get(cup, CUP_FALLBACK))


def parse_age(value) -> float:
    """Dataset has a handful of garbage ages (0, 117); treat implausible
    values as missing rather than letting them skew the model."""
    try:
        age = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return age if 10 <= age <= 90 else float("nan")


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Raw RentTheRunway rows -> the exact feature frame the model consumes."""
    out = pd.DataFrame(index=df.index)
    out["height_in"] = df["height"].apply(parse_height)
    out["weight_lbs"] = df["weight"].apply(parse_weight)
    out["age"] = df["age"].apply(parse_age)
    bust = df["bust size"].apply(parse_bust_size)
    out["bust_band"] = bust.apply(lambda t: t[0])
    out["cup_ordinal"] = bust.apply(lambda t: t[1])
    out["size"] = df["size"].astype(float)
    for col in CATEGORICAL_COLS:
        out[col] = df[col].fillna("missing").astype(str)
    return out


def build_feature_row(
    height_in: float,
    weight_lbs: float = None,
    bust_size: str = None,
    body_type: str = "missing",
    category: str = "dress",
    size: float = 8,
    age: float = None,
    rented_for: str = "missing",
) -> pd.DataFrame:
    """Build a single-row feature frame for inference, matching build_features'
    output schema exactly (same column names/order the model was trained on)."""
    band, cup = parse_bust_size(bust_size) if bust_size else (float("nan"), float("nan"))
    row = {
        "height_in": height_in,
        "weight_lbs": weight_lbs if weight_lbs is not None else float("nan"),
        "age": age if age is not None else float("nan"),
        "bust_band": band,
        "cup_ordinal": cup,
        "size": size,
        "body type": body_type or "missing",
        "category": category,
        "rented for": rented_for or "missing",
    }
    return pd.DataFrame([row], columns=ALL_FEATURE_COLS)
