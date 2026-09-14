# Fit-prediction model

Predicts P(fit outcome) — `small` / `fit` / `large` — from body measurements
and garment attributes.

## Honest scope

- **Trained on RentTheRunway's public fit-feedback dataset** (Misra et al.,
  RecSys 2018 — 192,544 labeled rental reviews with body measurements and
  actual reported fit outcome). Not the scraped Long catalog: those
  retailers have no fit-feedback loop of their own (no returns data, no
  "ran small" reviews), so there's nothing in-house to train on.
- **"Garment measurements" = rental size + category**, not a tape-measure
  inseam. RentTheRunway doesn't publish physical garment dimensions either
  — almost no retailer does.
- **"Body proportions" = height, weight, bust size, body type, age**, as
  self-reported by renters.

## What it actually found

- `size` (which rental size the person picked) and `weight_lbs` dominate the
  prediction by a wide margin (permutation importance ~0.13 and ~0.07).
  `height_in` matters, but modestly (~0.007) — on this dataset, whether a
  garment "fits" is driven far more by choosing the right size than by a
  renter's height alone.
- Holding size/weight/body-type fixed and varying height (`demo.py`),
  there's a small, somewhat noisy upward trend in predicted "runs large" at
  the tallest heights (6'2"+) across most categories — consistent with the
  premise this project is built on, but it's a modest signal, not a clean
  slam-dunk. Reporting it as it is rather than oversold.
- Class-rebalanced (the dataset is ~74% "fit" / 13% "small" / 13% "large" —
  training without rebalancing just predicts the majority class every time).
  After rebalancing: macro F1 ≈ 0.35, recall on "small"/"large" ≈ 0.5–0.6,
  precision on those classes ≈ 0.2 — this is a genuinely hard prediction
  task (a size chart mismatch that isn't visible in these features is a
  major real-world confound), and these numbers are in the range other
  published work on this exact dataset reports. See `artifacts/metrics.json`
  for the full classification report.

## Usage

```bash
python -m fit_model.download_data   # once, pulls the ~31MB dataset
python -m fit_model.train           # trains, evaluates, saves the model
python -m fit_model.demo            # the height-vs-fit story above
python -m fit_model.predict --height-in 71 --category gown --size 8
```

```python
from fit_model.predict import predict_fit
predict_fit(height_in=71, weight_lbs=140, category="gown", size=8)
# {"small": 0.19, "fit": 0.41, "large": 0.40}
```
