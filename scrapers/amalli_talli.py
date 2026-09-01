"""
Amalli Talli scraper.

Amalli Talli (amallitalli.com) is a tall-women's clothing brand running on
Shopify, so — like comfrt.py / uniqlo.py — we use the store's own JSON rather
than scraping rendered DOM:

  - Collection listing:  /collections/<handle>/products.json?limit=250&page=N
  - Single product:      /products/<handle>.js   (price in cents)

Both are public, need no auth, and plain HTTP works (no bot wall here), which
makes this one of the more reliable scrapers in the set.

Everything Amalli Talli sells is cut for tall frames, so tall_specific is
always True. Their variants carry an explicit "Length" / inseam option
(e.g. 34" / 36" Inseam) — that gets folded into sizes_available since inseam
is the useful signal for the fit model later.
"""
import html
import re
from typing import Optional
from urllib.parse import urlparse
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper, logger

TAG_RE = re.compile(r"<[^>]+>")
BASE = "https://amallitalli.com"

# Option names (lowercased) that describe fit/length rather than a plain size.
# Values from these are still worth keeping in sizes_available as tall signal.
_LENGTH_OPTION_NAMES = {"length", "inseam", "rise"}


class AmalliTalliScraper(BaseScraper):
    retailer_name = "amalli_talli"

    # Category collections. Amalli Talli has many niche collections (see
    # /collections.json); these are the broad garment buckets.
    COLLECTIONS = [
        "jeans",
        "tall-pants",
        "tops",
        "dresses-skirts",
        "tall-skirts",
        "jackets",
        "outerwear",
        "shorts-for-tall-women",
    ]

    # How many listing pages to walk per collection (250 products per page).
    MAX_LISTING_PAGES = 3

    def listing_urls(self):
        return [f"{BASE}/collections/{handle}" for handle in self.COLLECTIONS]

    def scrape_listing_page(self, page: Page):
        # Use the collection's own products.json instead of scraping tiles —
        # far more stable than chasing Shopify theme CSS classes.
        collection_url = page.url.split("?")[0].rstrip("/")
        urls = []
        for page_num in range(1, self.MAX_LISTING_PAGES + 1):
            api_url = f"{collection_url}/products.json?limit=250&page={page_num}"
            try:
                resp = page.request.get(api_url)
                products = resp.json().get("products", [])
            except Exception as e:
                logger.warning(f"[amalli_talli] listing fetch failed {api_url}: {e}")
                break
            if not products:
                break
            urls.extend(f"{BASE}/products/{p['handle']}" for p in products if p.get("handle"))
            if len(products) < 250:
                break
        return list(dict.fromkeys(urls))

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        handle = urlparse(url).path.rstrip("/").split("/")[-1]
        api_url = f"{BASE}/products/{handle}.js"
        try:
            resp = page.request.get(api_url)
            item = resp.json()
        except Exception as e:
            logger.warning(f"[amalli_talli] API call failed for {url}: {e}")
            return None

        name = item.get("title")
        price_cents = item.get("price_min", item.get("price"))
        if not name or price_cents is None:
            logger.warning(f"[amalli_talli] Missing required fields on {url}, skipping")
            return None
        price = price_cents / 100.0

        image_urls = [
            f"https:{img}" if img.startswith("//") else img
            for img in item.get("images", [])
        ]

        sizes = []
        for option in item.get("options", []):
            for value in option.get("values", []):
                if value and value not in sizes:
                    sizes.append(value)

        description = TAG_RE.sub(" ", item.get("description") or "")
        description = html.unescape(re.sub(r"\s+", " ", description)).strip()

        return {
            "name": name,
            "brand": item.get("vendor") or "Amalli Talli",
            "price": price,
            "currency": "USD",
            "source_url": f"{BASE}/products/{handle}",
            "image_urls": image_urls[:5],
            "sizes_available": sizes,
            "tall_specific": True,  # the whole brand is tall-cut
            "category": self._guess_category(item.get("product_type"), name),
            "description": description,
        }

    CATEGORY_KEYWORDS = [
        ("jean", "jeans"),
        ("denim", "jeans"),
        ("dress", "dresses"),
        ("romper", "dresses"),
        ("jumpsuit", "dresses"),
        ("skirt", "skirts"),
        ("short", "shorts"),
        ("legging", "pants"),
        ("jogger", "pants"),
        ("sweatpant", "pants"),
        ("pant", "pants"),
        ("trouser", "pants"),
        ("tee", "tops"),
        ("t-shirt", "tops"),
        ("shirt", "tops"),
        ("blouse", "tops"),
        ("tank", "tops"),
        ("top", "tops"),
        ("sweater", "tops"),
        ("cardigan", "tops"),
        ("sweatshirt", "tops"),
        ("hoodie", "tops"),
        ("jacket", "jackets"),
        ("blazer", "jackets"),
        ("shacket", "jackets"),
        ("coat", "jackets"),
    ]

    @classmethod
    def _guess_category(cls, product_type: Optional[str], name: str) -> str:
        haystack = f"{product_type or ''} {name or ''}".lower()
        for keyword, category in cls.CATEGORY_KEYWORDS:
            if keyword in haystack:
                return category
        return (product_type or "other").lower()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    scraper = AmalliTalliScraper()
    products = scraper.run(max_products=20)
    print(f"Scraped {len(products)} products")
    for p in products[:3]:
        print(p)
