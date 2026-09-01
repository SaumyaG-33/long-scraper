"""
Comfrt scraper.

Comfrt runs on Shopify, which exposes a clean public JSON endpoint for every
product at /products/<handle>.js (title, price, variants, images, options —
no auth needed). Same approach as uniqlo.py: use the site's own JSON rather
than scraping rendered DOM, which is far more reliable than chasing CSS
classes that Shopify themes change often.

Not a tall-specific retailer (loungewear, sized XS-3X), so tall_specific is
always False here.
"""
import re
from typing import Optional
from urllib.parse import urlparse
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper, logger

TAG_RE = re.compile(r"<[^>]+>")


class ComfrtScraper(BaseScraper):
    retailer_name = "comfrt"

    # 36 products per page; a few pages gives a decent first pull
    CATEGORY_URLS = [
        "https://comfrt.com/collections/all-products?page=1",
        "https://comfrt.com/collections/all-products?page=2",
    ]

    def listing_urls(self):
        return self.CATEGORY_URLS

    def scrape_listing_page(self, page: Page):
        for _ in range(4):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)

        hrefs = page.eval_on_selector_all(
            "a[data-orly-type='all-products']",
            "elements => elements.map(el => el.getAttribute('href'))",
        )
        urls = [f"https://comfrt.com{href}" for href in hrefs if href]
        return list(dict.fromkeys(urls))

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        handle = urlparse(url).path.rstrip("/").split("/")[-1]
        api_url = f"https://comfrt.com/products/{handle}.js"
        try:
            resp = page.request.get(api_url)
            item = resp.json()
        except Exception as e:
            logger.warning(f"[comfrt] API call failed for {url}: {e}")
            return None

        name = item.get("title")
        price_cents = item.get("price_min", item.get("price"))
        if not name or price_cents is None:
            logger.warning(f"[comfrt] Missing required fields on {url}, skipping")
            return None
        price = price_cents / 100.0

        image_urls = [
            f"https:{img}" if img.startswith("//") else img
            for img in item.get("images", [])
        ]

        sizes = []
        for option in item.get("options", []):
            if option.get("name", "").lower() == "size":
                sizes = option.get("values", [])
                break

        description = TAG_RE.sub(" ", item.get("description") or "").strip()
        description = re.sub(r"\s+", " ", description)

        return {
            "name": name,
            "brand": item.get("vendor") or "Comfrt",
            "price": price,
            "currency": "USD",
            "source_url": f"https://comfrt.com/products/{handle}",
            "image_urls": image_urls[:5],
            "sizes_available": sizes,
            "tall_specific": False,
            "category": self._guess_category(item.get("type"), name),
            "description": description,
        }

    # Comfrt's Shopify product_type is free-form (hoodie, sweatpants, kids
    # sweatshirt, blanket, bag, ...). Map it — plus the product name — onto
    # the fixed category set from base_scraper.py; anything non-apparel
    # (blankets, bags) falls through to "other".
    CATEGORY_KEYWORDS = [
        ("jean", "jeans"),
        ("denim", "jeans"),
        ("dress", "dresses"),
        ("jumpsuit", "dresses"),
        ("romper", "dresses"),
        ("skirt", "skirts"),
        ("short", "shorts"),
        ("jogger", "pants"),
        ("sweatpant", "pants"),
        ("legging", "pants"),
        ("trouser", "pants"),
        ("pant", "pants"),
        ("hoodie", "tops"),
        ("sweatshirt", "tops"),
        ("quarter-zip", "tops"),
        ("quarter zip", "tops"),
        ("pullover", "tops"),
        ("crew", "tops"),
        ("tee", "tops"),
        ("t-shirt", "tops"),
        ("shirt", "tops"),
        ("tank", "tops"),
        ("bra", "tops"),
        ("sweater", "tops"),
        ("cardigan", "tops"),
        ("top", "tops"),
        ("jacket", "jackets"),
        ("shacket", "jackets"),
        ("coat", "jackets"),
    ]

    @classmethod
    def _guess_category(cls, product_type: Optional[str], name: str) -> str:
        haystack = f"{product_type or ''} {name or ''}".lower()
        for keyword, category in cls.CATEGORY_KEYWORDS:
            if keyword in haystack:
                return category
        return "other"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    scraper = ComfrtScraper()
    products = scraper.run(max_products=20)
    print(f"Scraped {len(products)} products")
    for p in products[:3]:
        print(p)
