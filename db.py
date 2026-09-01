"""
MongoDB Atlas connection + upsert helpers for the Long product catalog.
"""
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_client = None

# The category vocabulary every scraper is expected to map onto
# (see the product schema in scrapers/base_scraper.py).
KNOWN_CATEGORIES = {
    "jeans", "dresses", "tops", "pants", "skirts", "shorts", "jackets", "other",
}

# Prices outside this band are almost always a parse bug, not a real price.
MIN_REASONABLE_PRICE = 5.0
MAX_REASONABLE_PRICE = 2000.0

_URL_RE = re.compile(r"^https?://", re.I)


def validate_product(p: Dict) -> List[str]:
    """Return a list of human-readable problems with a scraped product dict.
    An empty list means the product is fit to write."""
    problems = []

    for field in ("retailer", "name", "source_url", "currency"):
        value = p.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field} missing/empty")

    if not _URL_RE.match(str(p.get("source_url", ""))):
        problems.append("source_url is not an http(s) URL")

    price = p.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool):
        problems.append("price is not a number")
    elif not (MIN_REASONABLE_PRICE <= price <= MAX_REASONABLE_PRICE):
        problems.append(f"price {price} outside {MIN_REASONABLE_PRICE}-{MAX_REASONABLE_PRICE}")

    images = p.get("image_urls")
    if not isinstance(images, list) or not images:
        problems.append("image_urls empty")
    elif not all(isinstance(u, str) and _URL_RE.match(u) for u in images):
        problems.append("image_urls has non-URL entries")

    if not isinstance(p.get("sizes_available"), list):
        problems.append("sizes_available is not a list")

    if not isinstance(p.get("tall_specific"), bool):
        problems.append("tall_specific is not a bool")

    category = p.get("category")
    if category not in KNOWN_CATEGORIES:
        problems.append(f"category {category!r} not in KNOWN_CATEGORIES")

    return problems


def partition_valid(products: List[Dict]) -> Tuple[List[Dict], List[Tuple[Dict, List[str]]]]:
    """Split products into (valid, [(invalid, problems), ...])."""
    valid, invalid = [], []
    for p in products:
        problems = validate_product(p)
        (valid if not problems else invalid).append(p if not problems else (p, problems))
    return valid, invalid


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.environ["MONGODB_URI"]
        _client = MongoClient(uri)
    return _client


def get_products_collection() -> Collection:
    client = get_client()
    db_name = os.environ.get("MONGODB_DB_NAME", "long")
    coll = client[db_name]["products"]
    # Unique index on source_url so re-scrapes upsert instead of duplicate
    coll.create_index("source_url", unique=True)
    return coll


def upsert_products(products: List[Dict], validate: bool = True) -> Dict:
    """
    Bulk upsert product dicts, keyed on source_url.
    Adds/updates a scraped_at timestamp on every write.

    When validate=True (default), products failing validate_product() are
    skipped (and logged) rather than written.

    Returns a summary dict of the bulk write result.
    """
    skipped_invalid = 0
    if validate:
        products, invalid = partition_valid(products)
        skipped_invalid = len(invalid)
        for bad, problems in invalid:
            logger.warning(
                "[db] skipping invalid product %s: %s",
                bad.get("source_url") or bad.get("name") or "<unknown>",
                "; ".join(problems),
            )

    if not products:
        return {"matched": 0, "upserted": 0, "modified": 0, "skipped_invalid": skipped_invalid}

    coll = get_products_collection()
    now = datetime.now(timezone.utc)

    ops = []
    for p in products:
        p["scraped_at"] = now
        ops.append(
            UpdateOne(
                {"source_url": p["source_url"]},
                {"$set": p},
                upsert=True,
            )
        )

    result = coll.bulk_write(ops, ordered=False)
    return {
        "matched": result.matched_count,
        "upserted": len(result.upserted_ids),
        "modified": result.modified_count,
        "skipped_invalid": skipped_invalid,
    }
