"""
Uniqlo scraper.

Not a tall-specific retailer, so tall_specific is always False here. Sizes
returned include Uniqlo's "length" options (e.g. inseam) where available,
which is the useful signal for the fit model later.

NOTE ON APPROACH: Uniqlo's product detail pages fetch price/name/images via
a client-side call to their own JSON API (`/us/api/commerce/v5/en/products`)
after the initial page load — the price is NOT present in the server-rendered
HTML, so waiting longer on the page or re-querying the DOM won't surface it.
Rather than fighting that render timing, we call the same JSON endpoint the
page itself uses (via page.request, reusing the browser context) to get
name/price/images/sizes directly. Description text IS server-rendered, so
that part is still scraped from the DOM.
"""
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper, logger

PRODUCT_URL_RE = re.compile(r"/products/([A-Z0-9\-]+)/(\d+)")


class UniqloScraper(BaseScraper):
    retailer_name = "uniqlo"

    CATEGORY_URLS = [
        "https://www.uniqlo.com/us/en/women/bottoms/jeans",
        "https://www.uniqlo.com/us/en/women/tops",
    ]

    def listing_urls(self):
        return self.CATEGORY_URLS

    def scrape_listing_page(self, page: Page):
        for _ in range(4):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)

        hrefs = page.eval_on_selector_all(
            "a.product-tile__link",
            "elements => elements.map(el => el.getAttribute('href'))",
        )
        urls = [f"https://www.uniqlo.com{href}" for href in hrefs if href]
        return list(dict.fromkeys(urls))

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        match = PRODUCT_URL_RE.search(url)
        if not match:
            logger.warning(f"[uniqlo] Could not parse product id from {url}")
            return None
        product_id, price_group = match.groups()

        api_url = (
            f"https://www.uniqlo.com/us/api/commerce/v5/en/products"
            f"?productIds={product_id}&priceGroups={price_group}"
        )
        try:
            resp = page.request.get(api_url)
            data = resp.json()
        except Exception as e:
            logger.warning(f"[uniqlo] API call failed for {url}: {e}")
            return None

        items = data.get("result", {}).get("items", [])
        if not items:
            logger.warning(f"[uniqlo] No product data returned for {url}")
            return None
        item = items[0]

        name = item.get("name")
        price = item.get("prices", {}).get("base", {}).get("value")
        currency = item.get("prices", {}).get("base", {}).get("currency", {}).get("code", "USD")

        if not name or price is None:
            logger.warning(f"[uniqlo] Missing required fields on {url}, skipping")
            return None

        color_code = parse_qs(urlparse(url).query).get("colorDisplayCode", [None])[0]
        color_code = color_code or item.get("representativeColorDisplayCode")

        image_urls = []
        main_images = item.get("images", {}).get("main", {})
        if color_code and color_code in main_images:
            image_urls.append(main_images[color_code]["image"])
        for sub in item.get("images", {}).get("sub", []):
            if sub.get("image"):
                image_urls.append(sub["image"])

        sizes = []
        for entry in item.get("sizes", []) + item.get("plds", []):
            size_name = entry.get("name")
            if size_name and size_name not in sizes:
                sizes.append(size_name)

        description = self._extract_description(page)

        return {
            "name": name,
            "brand": "Uniqlo",
            "price": float(price),
            "currency": currency,
            "source_url": url,
            "image_urls": image_urls[:5],
            "sizes_available": sizes,
            "tall_specific": False,
            "category": self._guess_category(name),
            "description": description,
        }

    @staticmethod
    def _extract_description(page: Page) -> str:
        parts = page.eval_on_selector_all(
            ".image-plus-text__horizontal-large-description",
            "elements => elements.map(el => el.textContent.trim())",
        )
        return " ".join(p for p in parts if p)

    # Uniqlo product URLs are just /products/<id>/<priceGroup> — no category
    # info in the path (unlike ASOS), so guess from the product name instead.
    CATEGORY_KEYWORDS = [
        ("jeans", "jeans"),
        ("dress", "dresses"),
        ("t-shirt", "tops"),
        ("tee", "tops"),
        ("shirt", "tops"),
        ("blouse", "tops"),
        ("sweater", "tops"),
        ("cardigan", "tops"),
        ("hoodie", "tops"),
        ("sweatshirt", "tops"),
        ("pant", "pants"),
        ("trouser", "pants"),
        ("skirt", "skirts"),
        ("jacket", "jackets"),
        ("coat", "jackets"),
    ]

    @classmethod
    def _guess_category(cls, name: str) -> str:
        name_lower = (name or "").lower()
        for keyword, category in cls.CATEGORY_KEYWORDS:
            if keyword in name_lower:
                return category
        return "other"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    scraper = UniqloScraper()
    products = scraper.run(max_products=20)
    print(f"Scraped {len(products)} products")
    for p in products[:3]:
        print(p)
