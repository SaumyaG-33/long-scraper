"""
Phase 2, step 1: embed the scraped catalog for text search.

For every product in MongoDB we compute a single 512-d vector that blends:
  - a CLIP *image* embedding of the product photo (image_urls[0])
  - a CLIP *text* embedding of "<name>. <brand>. <category>. <description>"

Both live in the same CLIP space, so we L2-normalise each and take a weighted
average (IMAGE_WEIGHT). At query time the search encodes the query string with
the same CLIP text encoder and does cosine / $vectorSearch against this field.

We also stamp a `style_id` on each doc so colourway near-duplicates
("The Devon Pant" x9) can be collapsed at query time.

Usage:
    python embed.py                     # embed everything missing an embedding
    python embed.py --retailer madewell # just one retailer
    python embed.py --limit 20          # first N (smoke test)
    python embed.py --force             # re-embed even if already done
    python embed.py --create-index      # (re)create the Atlas vector index, then exit

Needs: open_clip_torch, torch, torchvision, Pillow, requests  (see requirements.txt)
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

try:  # lets Pillow decode the AVIF that Gap Inc's CDN serves for Old Navy
    import pillow_avif  # noqa: F401
except ImportError:
    pass

load_dotenv()

from db import get_products_collection  # noqa: E402

EMBED_MODEL = "ViT-B-32"
EMBED_PRETRAINED = "laion2b_s34b_b79k"
EMBED_DIM = 512
EMBED_VERSION = f"clip:{EMBED_MODEL}/{EMBED_PRETRAINED}"
IMAGE_WEIGHT = 0.5  # 0 = text only, 1 = image only
VECTOR_INDEX_NAME = "products_vec"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# --- style_id derivation (colourway grouping) ---------------------------------

_MADEWELL_STYLE_RE = re.compile(r"/p/.+?/([A-Z0-9]{4,10})/?(?:\?|$)")
_UNIQLO_ID_RE = re.compile(r"/products/([A-Z0-9\-]+)/\d+")
_OLDNAVY_PID_RE = re.compile(r"pid=(\d+)")


def style_id(product: dict) -> str:
    """A key shared by colourways of the same garment. Falls back to
    source_url when we can't do better (already ~one doc per style)."""
    retailer = product.get("retailer")
    url = product.get("source_url", "")
    name = product.get("name", "")

    if retailer == "madewell":
        m = _MADEWELL_STYLE_RE.search(url)
        if m:
            return f"madewell:{m.group(1)}"
    if retailer == "amalli_talli":
        # names look like "Lennon Tall Wide Leg Jean - Light Wash"
        base = name.split(" - ")[0].strip().lower()
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        if base:
            return f"amalli_talli:{base}"
    if retailer == "uniqlo":
        m = _UNIQLO_ID_RE.search(url)
        if m:
            return f"uniqlo:{m.group(1)}"
    if retailer == "old_navy":
        m = _OLDNAVY_PID_RE.search(url)
        if m:
            return f"old_navy:{m.group(1)}"
    return url or f"{retailer}:{name}"


# --- embedding ---------------------------------------------------------------

def _build_text(product: dict) -> str:
    parts = [
        product.get("name", ""),
        product.get("brand", ""),
        product.get("category", ""),
        (product.get("description") or "")[:400],
    ]
    return ". ".join(p for p in parts if p)


def _fetch_image(url: str):
    from PIL import Image

    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=20)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


class BrowserImageFetcher:
    """Fetch images through a real Chromium page navigation. Needed for
    retailers whose image CDNs sit behind the same bot wall as the site
    (Madewell / Akamai), where an API-style request gets a 403 but a real
    navigation passes. Also handles Old Navy's AVIF (via pillow-avif-plugin).

    Use as a context manager; call .fetch(url) -> PIL.Image.
    """

    def __init__(self, warm_urls=(
        "https://www.madewell.com/womens/clothing/jeans",
        "https://oldnavy.gap.com",
    )):
        self._warm_urls = warm_urls

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(user_agent=_UA)
        self._page = self._ctx.new_page()
        for url in self._warm_urls:
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                self._page.wait_for_timeout(1500)
            except Exception:
                pass
        return self

    def __exit__(self, *exc):
        for closer in (getattr(self, "_ctx", None), getattr(self, "_browser", None)):
            try:
                closer and closer.close()
            except Exception:
                pass
        try:
            self._pw.stop()
        except Exception:
            pass

    def fetch(self, url: str):
        from PIL import Image

        resp = self._page.goto(url, wait_until="commit", timeout=20000)
        if resp is None or not resp.ok:
            raise RuntimeError(f"HTTP {resp.status if resp else 'none'}")
        return Image.open(io.BytesIO(resp.body())).convert("RGB")


class Embedder:
    def __init__(self, device: str = "cpu"):
        import open_clip
        import torch

        self.torch = torch
        self.device = device
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            EMBED_MODEL, pretrained=EMBED_PRETRAINED
        )
        self.model.eval().to(device)
        self.tokenizer = open_clip.get_tokenizer(EMBED_MODEL)

    def _norm(self, t):
        return t / t.norm(dim=-1, keepdim=True)

    def embed(self, product: dict, fetch_image=_fetch_image):
        """Return (vector, had_image). `fetch_image` is a callable url -> PIL
        image; on failure for every candidate URL we fall back to a text-only
        vector (had_image=False)."""
        torch = self.torch
        text = self._build_text_tokens(product)
        with torch.no_grad():
            txt_vec = self._norm(self.model.encode_text(text))

            img_vec = None
            urls = product.get("image_urls") or []
            for url in urls[:3]:
                try:
                    img = fetch_image(url)
                except Exception:
                    continue
                tensor = self.preprocess(img).unsqueeze(0).to(self.device)
                img_vec = self._norm(self.model.encode_image(tensor))
                break

            if img_vec is None:
                combined = txt_vec
                had_image = False
            else:
                combined = self._norm(IMAGE_WEIGHT * img_vec + (1 - IMAGE_WEIGHT) * txt_vec)
                had_image = True

        return combined.squeeze(0).cpu().tolist(), had_image

    def _build_text_tokens(self, product: dict):
        return self.tokenizer([_build_text(product)]).to(self.device)

    def encode_query(self, text: str) -> list[float]:
        """Encode a free-text search query into the same normalised CLIP
        space as the stored product vectors."""
        torch = self.torch
        tokens = self.tokenizer([text]).to(self.device)
        with torch.no_grad():
            vec = self._norm(self.model.encode_text(tokens))
        return vec.squeeze(0).cpu().tolist()


# --- Atlas vector index -----------------------------------------------------

def create_vector_index() -> None:
    coll = get_products_collection()
    definition = {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": EMBED_DIM,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "tall_specific"},
            {"type": "filter", "path": "category"},
            {"type": "filter", "path": "retailer"},
            {"type": "filter", "path": "price"},
        ]
    }
    existing = {ix["name"] for ix in coll.list_search_indexes()}
    if VECTOR_INDEX_NAME in existing:
        coll.update_search_index(VECTOR_INDEX_NAME, definition)
        print(f"updated search index {VECTOR_INDEX_NAME!r}")
    else:
        coll.create_search_index(
            {"name": VECTOR_INDEX_NAME, "type": "vectorSearch", "definition": definition}
        )
        print(f"created search index {VECTOR_INDEX_NAME!r} (build takes ~1 min to become queryable)")


# --- main ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retailer")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true", help="Re-embed docs that already have one")
    parser.add_argument("--missing-image", action="store_true",
                        help="Only (re-)embed docs whose current vector is text-only")
    parser.add_argument("--image-fetcher", choices=("requests", "browser"), default="requests",
                        help="'browser' routes image downloads through Chromium (Madewell / Old Navy CDNs)")
    parser.add_argument("--device", default="cpu", help="cpu | mps | cuda")
    parser.add_argument("--create-index", action="store_true", help="(Re)create the Atlas vector index and exit")
    args = parser.parse_args()

    if args.create_index:
        create_vector_index()
        return

    coll = get_products_collection()
    query: dict = {}
    if args.retailer:
        query["retailer"] = args.retailer
    if args.missing_image:
        query["embedding_has_image"] = False
    elif not args.force:
        query["embedding"] = {"$exists": False}

    cursor = coll.find(query, projection={
        "name": 1, "brand": 1, "category": 1, "description": 1,
        "image_urls": 1, "retailer": 1, "source_url": 1,
    })
    if args.limit:
        cursor = cursor.limit(args.limit)
    products = list(cursor)

    print(f"{len(products)} products to embed  "
          f"(model {EMBED_VERSION}, device {args.device}, images via {args.image_fetcher})")
    if not products:
        return

    embedder = Embedder(device=args.device)
    now = datetime.now(timezone.utc)
    done = no_image = failed = 0

    def run(fetch_image):
        nonlocal done, no_image, failed
        for i, p in enumerate(products, 1):
            try:
                vector, had_image = embedder.embed(p, fetch_image=fetch_image)
            except Exception as e:
                failed += 1
                print(f"  [{i}/{len(products)}] FAILED {p.get('source_url')}: {e}")
                continue
            coll.update_one(
                {"_id": p["_id"]},
                {"$set": {
                    "embedding": vector,
                    "embedding_has_image": had_image,
                    "embed_version": EMBED_VERSION,
                    "embedded_at": now,
                    "style_id": style_id(p),
                }},
            )
            done += 1
            if not had_image:
                no_image += 1
            if i % 25 == 0 or i == len(products):
                print(f"  [{i}/{len(products)}] embedded={done} text_only={no_image} failed={failed}")

    if args.image_fetcher == "browser":
        with BrowserImageFetcher() as bf:
            run(bf.fetch)
    else:
        run(_fetch_image)

    print(f"\ndone: {done} embedded ({no_image} text-only, no image), {failed} failed")
    if not args.create_index:
        print("next: python embed.py --create-index   (only needed once)")


if __name__ == "__main__":
    sys.exit(main())
