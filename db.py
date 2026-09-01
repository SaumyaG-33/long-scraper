"""
MongoDB Atlas connection + upsert helpers for the Long product catalog.
"""
import os
from datetime import datetime, timezone
from typing import List, Dict
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from dotenv import load_dotenv

load_dotenv()

_client = None


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


def upsert_products(products: List[Dict]) -> Dict:
    """
    Bulk upsert product dicts, keyed on source_url.
    Adds/updates a scraped_at timestamp on every write.
    Returns a summary dict of the bulk write result.
    """
    if not products:
        return {"matched": 0, "upserted": 0, "modified": 0}

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
    }
