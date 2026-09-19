"""
Phase 2, step 2: text search over the embedded catalog.

query string --> CLIP text vector --> Atlas $vectorSearch on `embedding`
             --> hard filter to tall_specific=true
             --> collapse colourways by style_id (keep best-scoring colour)
             --> ranked results

CLI:
    python search.py "high waisted wide leg tall jeans"
    python search.py "linen midi dress" --k 15 --category dresses --max-price 120
    python search.py --queries queries.txt        # one query per line, batch eyeball

The same search() function backs the HTTP API in api.py.
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from db import get_products_collection  # noqa: E402
from embed import Embedder, VECTOR_INDEX_NAME  # noqa: E402

_embedder: Embedder | None = None


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder(device="cpu")
    return _embedder


def search(
    query: str,
    k: int = 20,
    category: str | None = None,
    max_price: float | None = None,
    tall_only: bool = True,
    candidates: int = 80,
    height_in: float | None = None,
    weight_lbs: float | None = None,
) -> list[dict]:
    """Return up to `k` ranked results, one per garment style."""
    qvec = _get_embedder().encode_query(query)

    vs_filter: dict = {}
    if tall_only:
        vs_filter["tall_specific"] = True
    if category:
        vs_filter["category"] = category
    if max_price is not None:
        vs_filter["price"] = {"$lte": max_price}

    stage = {
        "$vectorSearch": {
            "index": VECTOR_INDEX_NAME,
            "path": "embedding",
            "queryVector": qvec,
            "numCandidates": max(candidates * 4, 200),
            "limit": candidates,
        }
    }
    if vs_filter:
        stage["$vectorSearch"]["filter"] = vs_filter

    pipeline = [
        stage,
        {
            "$project": {
                "_id": 0,
                "name": 1, "brand": 1, "price": 1, "currency": 1,
                "category": 1, "retailer": 1, "tall_specific": 1,
                "source_url": 1, "image_urls": 1, "style_id": 1,
                "embedding_has_image": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    rows = list(get_products_collection().aggregate(pipeline))

    # collapse colourways: keep the best-scoring row per style_id
    seen: dict[str, dict] = {}
    for r in rows:
        sid = r.get("style_id") or r["source_url"]
        if sid not in seen:
            r["colour_count"] = 1
            seen[sid] = r
        else:
            seen[sid]["colour_count"] += 1

    ranked = sorted(seen.values(), key=lambda r: r["score"], reverse=True)[:k]

    # Fit scoring is an enrichment, not a ranking factor (v1) — it only runs
    # over the final k results, and only when the caller gave us a height.
    if height_in is not None:
        from fit_model.catalog_bridge import fit_probability_for_product

        for r in ranked:
            try:
                r["fit_probability"] = fit_probability_for_product(
                    height_in=height_in, product=r, weight_lbs=weight_lbs,
                )
            except Exception:
                r["fit_probability"] = None

    return ranked


def _print_results(query: str, results: list[dict]) -> None:
    print(f"\n=== {query!r} — {len(results)} results ===")
    for i, r in enumerate(results, 1):
        img = "" if r.get("embedding_has_image") else " [text-only]"
        colours = f" (+{r['colour_count'] - 1} colours)" if r.get("colour_count", 1) > 1 else ""
        fit = r.get("fit_probability")
        fit_str = f"\n      fit: {fit}" if fit else ""
        print(
            f"{i:>2}. {r['score']:.3f}  {r['brand']} — {r['name']}{colours}\n"
            f"      {r['category']:<10} ${r['price']:.2f} {r['currency']}  {r['retailer']}{img}\n"
            f"      {r['source_url']}{fit_str}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", help="Search query")
    ap.add_argument("--queries", help="File with one query per line (batch mode)")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--category")
    ap.add_argument("--max-price", type=float)
    ap.add_argument("--include-non-tall", action="store_true", help="Don't hard-filter to tall_specific")
    ap.add_argument("--height-in", type=float, help="Attach fit-probability scoring for this height (inches)")
    ap.add_argument("--weight-lbs", type=float)
    args = ap.parse_args()

    queries: list[str] = []
    if args.queries:
        with open(args.queries) as fh:
            queries = [ln.strip() for ln in fh if ln.strip()]
    elif args.query:
        queries = [args.query]
    else:
        ap.error("pass a query or --queries FILE")

    for q in queries:
        results = search(
            q, k=args.k, category=args.category, max_price=args.max_price,
            tall_only=not args.include_non_tall,
            height_in=args.height_in, weight_lbs=args.weight_lbs,
        )
        _print_results(q, results)


if __name__ == "__main__":
    sys.exit(main())
