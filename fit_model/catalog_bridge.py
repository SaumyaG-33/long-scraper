"""
Bridges the Long product catalog to the fit model's feature space.

The fit model was trained on RentTheRunway's category vocabulary ("dress",
"jacket", "jeans", ...), which doesn't line up 1:1 with the catalog's
category set (see scrapers/base_scraper.py). This is the one place that
mapping lives, so it doesn't get duplicated between search.py/api.py.

Categories with no reasonable RTR analog ("shorts", "other") map to None,
which predict_fit() treats as an unknown category — the model still runs,
just without that signal, rather than guessing wrong.
"""
from typing import Optional

from fit_model.predict import predict_fit

CATALOG_TO_RTR_CATEGORY = {
    "dresses": "dress",
    "jackets": "jacket",
    "jeans": "jeans",
    "pants": "pants",
    "skirts": "skirt",
    "tops": "top",
    "shorts": None,
    "other": None,
}

# RentTheRunway "size" is a rental-brand-specific numeric code (median ~12,
# not a US dress size 1:1) — there's no clean way to derive it from the
# catalog's size labels, so we use the dataset's overall median as a neutral
# default when the caller doesn't have anything better.
DEFAULT_RTR_SIZE = 12


def fit_probability_for_product(
    height_in: float,
    product: dict,
    weight_lbs: Optional[float] = None,
    body_type: Optional[str] = None,
) -> dict:
    """product is a catalog dict with at least a 'category' key (as stored
    in MongoDB). Returns {"small": p, "fit": p, "large": p}."""
    rtr_category = CATALOG_TO_RTR_CATEGORY.get(product.get("category"))
    return predict_fit(
        height_in=height_in,
        weight_lbs=weight_lbs,
        body_type=body_type or "missing",
        category=rtr_category or "missing",
        size=DEFAULT_RTR_SIZE,
    )
