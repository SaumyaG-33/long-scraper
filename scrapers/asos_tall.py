"""
ASOS Tall scraper.

NOTE ON SELECTORS: ASOS (like every retailer) changes its DOM/class names
periodically. The selectors below are a reasonable starting point based on
ASOS's typical structure (data-testid attributes, which tend to be more
stable than auto-generated CSS classes) but you WILL likely need to:
  1. Run this with HEADLESS=false once to watch it in a real browser
  2. Open devtools on an actual ASOS Tall listing/product page
  3. Adjust the selectors below to match what you see

This is normal for scraping — budget 30-60 min for selector debugging
the first time you run this against the live site.
"""
from typing import Optional
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper, logger


class AsosTallScraper(BaseScraper):
    retailer_name = "asos_tall"

    # Start with a couple of categories; add more once this works end-to-end
    CATEGORY_URLS = [
        "https://www.asos.com/us/women/tall/jeans-denim/cat/?cid=20300",
        "https://www.asos.com/us/women/tall/dresses/cat/?cid=19780",
    ]

    def listing_urls(self):
        return self.CATEGORY_URLS

    def scrape_listing_page(self, page: Page):
        # ASOS product tiles are typically <article> elements with an <a> link.
        # Scroll a bit first since ASOS lazy-loads tiles as you scroll.
        for _ in range(4):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)

        # Broad selector: any link whose href contains '/prd/' (ASOS product page pattern).
        # Not scoped to <article> since the real tile wrapper element is unverified —
        # if this over-matches (e.g. catches nav links), tighten it once you've
        # inspected the live DOM in devtools.
        links = page.eval_on_selector_all(
            "a[href*='/prd/']",
            "elements => elements.map(el => el.href)",
        )
        return list(dict.fromkeys(links))

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        try:
            page.wait_for_selector("h1", timeout=10000)
        except Exception:
            logger.warning(f"[asos_tall] No h1 found on {url}")
            return None

        name = self._safe_text(page, "h1")
        brand = self._safe_text(page, "[data-testid='product-brand']") or "ASOS"
        price_text = self._safe_text(page, "[data-testid='current-price']")
        price = self._parse_price(price_text)

        image_urls = page.eval_on_selector_all(
            "[data-testid='gallery'] img",
            "elements => elements.map(el => el.src)",
        )

        sizes = page.eval_on_selector_all(
            "select[id*='sizeSelect'] option, [data-testid='sizeSelector'] option",
            "elements => elements.map(el => el.textContent.trim()).filter(t => t && !t.toLowerCase().includes('select'))",
        )

        description = self._safe_text(page, "[data-testid='product-description']")

        if not name or price is None:
            logger.warning(f"[asos_tall] Missing required fields on {url}, skipping")
            return None

        return {
            "name": name,
            "brand": brand,
            "price": price,
            "currency": "USD",
            "source_url": url,
            "image_urls": image_urls[:5],
            "sizes_available": sizes,
            "tall_specific": True,  # everything from this scraper is the Tall line
            "category": self._guess_category(url),
            "description": description or "",
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

    @staticmethod
    def _guess_category(url: str) -> str:
        for cat in ["jeans", "dresses", "tops", "pants", "skirts", "jackets"]:
            if cat in url:
                return cat
        return "other"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    scraper = AsosTallScraper()
    products = scraper.run(max_products=20)
    print(f"Scraped {len(products)} products")
    for p in products[:3]:
        print(p)
