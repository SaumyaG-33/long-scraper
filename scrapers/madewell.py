"""
Madewell scraper.

Madewell (J.Crew Group, Salesforce Commerce Cloud) sits behind Akamai Bot
Manager: plain HTTP requests get a 403. A real headless Chromium (what
BaseScraper drives) currently passes the challenge, but this is the
fragile one in the set — if it starts returning 403 / "Access Denied":

  1. Set HEADLESS=false in .env and run with --max 1 to watch it
  2. If headful also fails, the IP/UA is likely flagged — try later, from a
     different network, or add a stealth plugin / residential proxy

Data source: every Madewell PDP embeds a JSON-LD <script type="application/ld+json">
block with @type "Product" (name, description, brand, price, currency,
images, colour, sku). That's the primary source here — it's far more stable
than the auto-generated React class names. Size/length options are read from
the DOM since they aren't in the JSON-LD.

Not a tall-specific retailer, but many Madewell styles offer a "Tall" length
alongside Standard/Petite/Short/Plus — when a product does, tall_specific is
set True and the length options are folded into sizes_available as fit signal.
"""
import html
import json
import re
from typing import Optional
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper, logger

BASE = "https://www.madewell.com"

# Length/fit options Madewell shows as "size" buttons on a PDP; "Size Chart"
# is a link that lands in the same container and must be dropped.
_LENGTH_WORDS = {"standard", "petite", "short", "tall", "plus", "regular"}
_SIZE_BUTTON_NOISE = {"size chart", "size guide", ""}


class MadewellScraper(BaseScraper):
    retailer_name = "madewell"

    CATEGORY_URLS = [
        f"{BASE}/womens/clothing/jeans",
        f"{BASE}/womens/clothing/dresses",
        f"{BASE}/womens/clothing/tops-shirts",
        f"{BASE}/womens/clothing/pants",
        f"{BASE}/womens/clothing/skirts",
        f"{BASE}/womens/clothing/sweaters",
    ]

    def listing_urls(self):
        return self.CATEGORY_URLS

    def scrape_listing_page(self, page: Page):
        # PLP lazy-loads tiles on scroll.
        for _ in range(8):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(600)

        hrefs = page.eval_on_selector_all(
            "a[class*='ProductTile'][href], [class*='ProductTile'] a[href]",
            "els => els.map(e => e.getAttribute('href'))",
        )
        urls = []
        for href in hrefs:
            if not href or "/p/" not in href:
                continue
            full = href if href.startswith("http") else BASE + href
            urls.append(full.split("?")[0] if "?" not in href else full)
        return list(dict.fromkeys(urls))

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        try:
            # state="attached" — a <script> node is never "visible", so the
            # default visibility wait would always time out.
            page.wait_for_selector(
                "script[type='application/ld+json']", timeout=10000, state="attached"
            )
        except Exception:
            logger.warning(f"[madewell] No JSON-LD on {url}")
            return None

        # The Product block is injected by React a beat after the first
        # JSON-LD script shows up — poll for it rather than a fixed sleep.
        product = None
        for _ in range(6):
            product = self._extract_product_ld(page)
            if product:
                break
            page.wait_for_timeout(1000)

        if product:
            name = product.get("name")
            offers = product.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = self._parse_price(offers.get("price"))
            currency = offers.get("priceCurrency") or "USD"
            brand = product.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            image = product.get("image") or []
            if isinstance(image, str):
                image = [image]
            description = (product.get("description") or "").strip()
        else:
            # Not every Madewell PDP ships a Product JSON-LD block — fall back
            # to <h1> + og/meta tags + the visible price.
            logger.info(f"[madewell] No Product JSON-LD on {url}, using DOM fallback")
            name = self._safe_text(page, "h1")
            price = self._fallback_price(page)
            currency = "USD"
            brand = "Madewell"
            image = self._fallback_images(page)
            description = self._meta(page, "og:description") or self._meta(page, "description") or ""

        brand = brand or "Madewell"
        if brand.upper() == "MW":
            brand = "Madewell"

        if not name or price is None:
            logger.warning(f"[madewell] Missing required fields on {url}, skipping")
            return None

        lengths = self._length_options(page)
        sizes = self._numeric_sizes(page)
        tall_specific = "tall" in {l.lower() for l in lengths}
        # Fold length options in as fit signal (Tall / Petite / etc.)
        sizes_available = list(dict.fromkeys(lengths + sizes))

        return {
            "name": name,
            "brand": brand,
            "price": price,
            "currency": currency,
            "source_url": url,
            "image_urls": image[:5],
            "sizes_available": sizes_available,
            "tall_specific": tall_specific,
            "category": self._guess_category(url),
            "description": html.unescape((description or "").strip()),
        }

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _safe_text(page: Page, selector: str) -> Optional[str]:
        el = page.query_selector(selector)
        return el.text_content().strip() if el else None

    @staticmethod
    def _meta(page: Page, key: str) -> Optional[str]:
        el = page.query_selector(f"meta[property='{key}'], meta[name='{key}']")
        return el.get_attribute("content") if el else None

    @classmethod
    def _fallback_price(cls, page: Page) -> Optional[float]:
        for text in page.eval_on_selector_all(
            "[class*='Price'], [class*='price'], [data-testid*='price']",
            "els => els.map(e => e.textContent)",
        ):
            m = re.search(r"\$[\d,]+(?:\.\d{2})?", text or "")
            if m:
                return cls._parse_price(m.group())
        return None

    @staticmethod
    def _fallback_images(page: Page) -> list:
        srcs = page.eval_on_selector_all(
            "img[src*='/images/']",
            "els => els.map(e => e.getAttribute('src'))",
        )
        out = []
        for s in srcs:
            if not s or "madewell.com/images/" not in s:
                continue
            clean = s.split("?")[0]
            if clean not in out:
                out.append(clean)
        og = page.query_selector("meta[property='og:image']")
        if og and og.get_attribute("content"):
            out.insert(0, og.get_attribute("content").split("?")[0])
        return list(dict.fromkeys(out))

    @staticmethod
    def _extract_product_ld(page: Page) -> Optional[dict]:
        """Find the JSON-LD node with @type == 'Product' across all blocks,
        handling bare objects, arrays, and @graph containers."""
        blocks = page.eval_on_selector_all(
            "script[type='application/ld+json']", "els => els.map(e => e.textContent)"
        )
        for raw in blocks:
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue
            candidates = []
            if isinstance(data, list):
                candidates = data
            elif isinstance(data, dict):
                candidates = data.get("@graph", [data])
            for node in candidates:
                if isinstance(node, dict) and node.get("@type") == "Product":
                    return node
        return None

    @staticmethod
    def _length_options(page: Page) -> list:
        raw = page.eval_on_selector_all(
            "button[class*='Size']",
            "els => els.map(e => (e.textContent || '').trim())",
        )
        out = []
        for t in raw:
            if t.lower() in _SIZE_BUTTON_NOISE:
                continue
            if t.lower() in _LENGTH_WORDS:
                out.append(t)
        return list(dict.fromkeys(out))

    @staticmethod
    def _numeric_sizes(page: Page) -> list:
        raw = page.eval_on_selector_all(
            "[class*='SizeList'] button, [class*='sizeList'] button, "
            "fieldset [class*='swatch'] button[aria-label]",
            "els => els.map(e => (e.getAttribute('aria-label') || e.textContent || '').trim())",
        )
        out = []
        for t in raw:
            t = re.sub(r"\s+", " ", t).strip()
            if t and t.lower() not in _SIZE_BUTTON_NOISE and t.lower() not in _LENGTH_WORDS:
                out.append(t)
        return list(dict.fromkeys(out))

    @staticmethod
    def _parse_price(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(str(value).replace("$", "").replace(",", "").strip())
        except ValueError:
            return None

    CATEGORY_MAP = [
        ("jeans", "jeans"),
        ("dress", "dresses"),
        ("jumpsuit", "dresses"),
        ("tops-shirts", "tops"),
        ("sweater", "tops"),
        ("pants", "pants"),
        ("skirt", "skirts"),
    ]

    @classmethod
    def _guess_category(cls, url: str) -> str:
        low = url.lower()
        for needle, category in cls.CATEGORY_MAP:
            if needle in low:
                return category
        return "other"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    scraper = MadewellScraper()
    products = scraper.run(max_products=20)
    print(f"Scraped {len(products)} products")
    for p in products[:3]:
        print(p)
