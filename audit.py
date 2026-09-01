"""
Read-only audit of the scraped product catalog in MongoDB Atlas.

Run this after a scrape batch to decide whether the corpus is clean enough
to move on to Phase 2 (embeddings):

    python audit.py                # audit everything
    python audit.py --retailer madewell

It never writes. It reports:
  - counts by retailer and by category
  - data-completeness gaps (no images, no sizes, no/short description)
  - price min / median / max per retailer (spots parse bugs)
  - tall_specific true/false split
  - likely duplicates (same normalised name, different source_url)
  - anything currently in the collection that fails validate_product()
"""
from __future__ import annotations

import argparse
import statistics
from collections import Counter, defaultdict

from dotenv import load_dotenv

load_dotenv()

from db import get_products_collection, validate_product  # noqa: E402


def _norm_name(name: str) -> str:
    return " ".join((name or "").lower().split())


def _pct(n: int, total: int) -> str:
    return f"{(100 * n / total):.1f}%" if total else "-"


def audit(retailer: str | None = None) -> None:
    coll = get_products_collection()
    query = {"retailer": retailer} if retailer else {}
    products = list(coll.find(query))
    total = len(products)

    print(f"\n=== Long catalog audit ===")
    print(f"collection: {coll.full_name}")
    print(f"filter: {query or '(all)'}")
    print(f"total products: {total}")
    if not total:
        print("nothing to audit.")
        return

    # --- counts by retailer / category ---
    by_retailer = Counter(p.get("retailer", "?") for p in products)
    by_category = Counter(p.get("category", "?") for p in products)

    print("\n-- by retailer --")
    for name, n in by_retailer.most_common():
        print(f"  {name:<16} {n:>6}  {_pct(n, total)}")

    print("\n-- by category --")
    for name, n in by_category.most_common():
        print(f"  {str(name):<16} {n:>6}  {_pct(n, total)}")

    # --- completeness gaps ---
    no_images = [p for p in products if not p.get("image_urls")]
    no_sizes = [p for p in products if not p.get("sizes_available")]
    thin_desc = [p for p in products if len((p.get("description") or "").strip()) < 20]
    no_price = [p for p in products if not isinstance(p.get("price"), (int, float))]

    print("\n-- completeness gaps --")
    print(f"  no image_urls      {len(no_images):>6}  {_pct(len(no_images), total)}")
    print(f"  no sizes_available {len(no_sizes):>6}  {_pct(len(no_sizes), total)}")
    print(f"  desc < 20 chars    {len(thin_desc):>6}  {_pct(len(thin_desc), total)}")
    print(f"  no numeric price   {len(no_price):>6}  {_pct(len(no_price), total)}")

    # --- price sanity per retailer ---
    prices_by_retailer = defaultdict(list)
    for p in products:
        if isinstance(p.get("price"), (int, float)):
            prices_by_retailer[p.get("retailer", "?")].append(p["price"])

    print("\n-- price min / median / max (USD) --")
    for name in sorted(prices_by_retailer):
        vals = prices_by_retailer[name]
        print(
            f"  {name:<16} {min(vals):>8.2f} {statistics.median(vals):>8.2f} "
            f"{max(vals):>8.2f}   (n={len(vals)})"
        )

    # --- tall_specific split ---
    tall = Counter(bool(p.get("tall_specific")) for p in products)
    print("\n-- tall_specific --")
    print(f"  True  {tall.get(True, 0):>6}  {_pct(tall.get(True, 0), total)}")
    print(f"  False {tall.get(False, 0):>6}  {_pct(tall.get(False, 0), total)}")

    # --- likely duplicates (same normalised name, different source_url) ---
    by_name = defaultdict(set)
    for p in products:
        by_name[_norm_name(p.get("name", ""))].add(p.get("source_url"))
    dupes = {name: urls for name, urls in by_name.items() if name and len(urls) > 1}
    print(f"\n-- likely duplicate names -- ({len(dupes)} groups)")
    for name, urls in sorted(dupes.items(), key=lambda kv: -len(kv[1]))[:15]:
        print(f"  {name!r}: {len(urls)} products")

    # --- rows that fail current validation ---
    invalid = [(p, validate_product(p)) for p in products]
    invalid = [(p, probs) for p, probs in invalid if probs]
    print(f"\n-- rows failing validate_product() -- ({len(invalid)})")
    for p, probs in invalid[:20]:
        print(f"  {p.get('source_url')}: {'; '.join(probs)}")
    if len(invalid) > 20:
        print(f"  ... and {len(invalid) - 20} more")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--retailer", help="Audit only this retailer")
    args = parser.parse_args()
    audit(args.retailer)
