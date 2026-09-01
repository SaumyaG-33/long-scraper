"""
Base scraper class. Each retailer scraper subclasses this and implements
`scrape_listing_page` and `scrape_product_page`.

Product schema (what every scraper must produce):
{
    "retailer": str,                # e.g. "asos_tall"
    "name": str,
    "brand": str,
    "price": float,
    "currency": str,               # e.g. "USD"
    "source_url": str,             # canonical product URL, used as dedupe key
    "image_urls": list[str],
    "sizes_available": list[str],
    "tall_specific": bool,         # True if this is a "Tall" fit line
    "category": str,               # e.g. "jeans", "dresses", "tops"
    "description": str,
}
"""
import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    retailer_name: str = "base"

    def __init__(self, headless: Optional[bool] = None, delay_seconds: Optional[float] = None):
        self.headless = headless if headless is not None else os.environ.get("HEADLESS", "true").lower() == "true"
        self.delay = delay_seconds if delay_seconds is not None else float(os.environ.get("REQUEST_DELAY_SECONDS", 2))

    @abstractmethod
    def listing_urls(self):
        """Category/listing page URLs to crawl for this retailer. Returns list[str]."""
        raise NotImplementedError

    @abstractmethod
    def scrape_listing_page(self, page: Page):
        """Given a loaded listing page, return product page URLs found on it. Returns list[str]."""
        raise NotImplementedError

    @abstractmethod
    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        """Given a loaded product page, return a product dict matching the schema above."""
        raise NotImplementedError

    def run(self, max_products: int = 100):
        products = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                )
            )
            page = context.new_page()

            product_urls = []
            for listing_url in self.listing_urls():
                logger.info(f"[{self.retailer_name}] Loading listing: {listing_url}")
                try:
                    page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(self.delay)
                    urls = self.scrape_listing_page(page)
                    logger.info(f"[{self.retailer_name}] Found {len(urls)} product links")
                    product_urls.extend(urls)
                except PWTimeout:
                    logger.warning(f"[{self.retailer_name}] Timeout loading {listing_url}, skipping")
                if len(product_urls) >= max_products:
                    break

            product_urls = list(dict.fromkeys(product_urls))[:max_products]  # dedupe, cap

            for url in product_urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(self.delay)
                    product = self.scrape_product_page(page, url)
                    if product:
                        product["retailer"] = self.retailer_name
                        products.append(product)
                        logger.info(f"[{self.retailer_name}] Scraped: {product.get('name')}")
                except PWTimeout:
                    logger.warning(f"[{self.retailer_name}] Timeout on product page {url}, skipping")
                except Exception as e:
                    logger.warning(f"[{self.retailer_name}] Failed on {url}: {e}")

            browser.close()
        return products
