"""
Old Navy scraper.

Unlike Uniqlo/Comfrt, Old Navy (Gap Inc) doesn't expose a clean public JSON
product API — price/images/sizes are server-rendered directly into the page
HTML (React SSR), so this one scrapes the DOM directly via data-testid
attributes, which Gap Inc's PDP template uses consistently.

Not a tall-specific retailer (Old Navy sells "Tall" as a size modifier on
some styles, not a separate line), so tall_specific is always False here.
"""
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper, logger


class OldNavyScraper(BaseScraper):
    retailer_name = "old_navy"

    CATEGORY_URLS = [
        "https://oldnavy.gap.com/browse/women/jeans?cid=85729",
        "https://oldnavy.gap.com/browse/women/dresses-and-jumpsuits?cid=15292",
    ]

    def listing_urls(self):
        return self.CATEGORY_URLS

    def scrape_listing_page(self, page: Page):
        for _ in range(4):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)

        hrefs = page.eval_on_selector_all(
            "div[data-testid='plp_product-card'] a[href*='product.do']",
            "elements => elements.map(el => el.href)",
        )
        seen_pids = set()
        urls = []
        for href in hrefs:
            match = re.search(r"pid=(\d+)", href)
            if not match:
                continue
            pid = match.group(1)
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            urls.append(f"https://oldnavy.gap.com/browse/product.do?pid={pid}")
        return urls

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        try:
            # state="attached" (not the default "visible") — the page renders
            # two h1[data-testid='product-title'] nodes (a hidden responsive
            # duplicate), and the first one in DOM order is sometimes the
            # hidden one, so waiting for visibility can time out even though
            # the text is already there and readable.
            page.wait_for_selector("h1[data-testid='product-title']", timeout=10000, state="attached")
        except Exception:
            logger.warning(f"[old_navy] No product title found on {url}")
            return None

        name = self._safe_text(page, "h1[data-testid='product-title']")

        price_text = self._safe_text(page, "span.current-sale-price")
        if not price_text:
            wrapper_text = self._safe_text(page, "[data-testid='pdp-title-price-wrapper']")
            price_match = re.search(r"\$[\d,.]+", wrapper_text or "")
            price_text = price_match.group() if price_match else None
        price = self._parse_price(price_text)

        if not name or price is None:
            logger.warning(f"[old_navy] Missing required fields on {url}, skipping")
            return None

        image_urls = page.eval_on_selector_all(
            "div[data-testid='pdp-photo-brick-image'] img",
            "elements => elements.map(el => el.src)",
        )
        # The photo brick grid sometimes mixes in marketing banners (served
        # from a different asset host, usually .svg) alongside real product
        # photos — keep only actual product images.
        image_urls = [u for u in image_urls if "content.gapinc.com" in u]

        sizes = page.eval_on_selector_all(
            ".pdp_size-selector-container .fds_selector__content",
            "elements => elements.map(el => el.textContent.trim()).filter(Boolean)",
        )

        description = page.eval_on_selector(
            "meta[name='description']", "el => el.content"
        ) or ""

        return {
            "name": name,
            "brand": "Old Navy",
            "price": price,
            "currency": "USD",
            "source_url": url,
            "image_urls": image_urls[:5],
            "sizes_available": sizes,
            "tall_specific": False,
            "category": self._guess_category(name),
            "description": description,
        }

    @staticmethod
    def _safe_text(page: Page, selector: str) -> Optional[str]:
        el = page.query_selector(selector)
        if el:
            return el.text_content().strip()
        return None

    @staticmethod
    def _parse_price(text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        cleaned = text.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None

    CATEGORY_KEYWORDS = [
        ("jeans", "jeans"),
        ("dress", "dresses"),
        ("jumpsuit", "dresses"),
        ("t-shirt", "tops"),
        ("tee", "tops"),
        ("shirt", "tops"),
        ("blouse", "tops"),
        ("sweater", "tops"),
        ("cardigan", "tops"),
        ("hoodie", "tops"),
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
    scraper = OldNavyScraper()
    products = scraper.run(max_products=20)
    print(f"Scraped {len(products)} products")
    for p in products[:3]:
        print(p)
