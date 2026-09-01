"""
Scaffolds for Zara and H&M. These are NOT tall-specific retailers, so for
these you'll want to:
  - Set tall_specific=False in scrape_product_page
  - Consider filtering to items with longer inseams/lengths where the
    product data mentions it (useful signal for your fit model later)

IMPORTANT: These sites are significantly harder to scrape than ASOS:
  - Zara: heavy client-side rendering, region/currency redirects, bot detection
  - H&M: similar JS-heavy rendering, occasional CAPTCHA challenges

Uniqlo is done — see scrapers/uniqlo.py. Recommended order was
Uniqlo -> H&M -> Zara (roughly easiest to hardest); H&M is next.

Fill in listing_urls / scrape_listing_page / scrape_product_page the same
way asos_tall.py / uniqlo.py do, once you've inspected each site's live DOM.
"""
from typing import Optional
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper


class HMScraper(BaseScraper):
    retailer_name = "hm"

    def listing_urls(self):
        raise NotImplementedError("Fill in H&M category URLs once you're ready to build this one")

    def scrape_listing_page(self, page: Page):
        raise NotImplementedError

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        raise NotImplementedError


class ZaraScraper(BaseScraper):
    retailer_name = "zara"

    def listing_urls(self):
        raise NotImplementedError("Fill in Zara category URLs once you're ready to build this one")

    def scrape_listing_page(self, page: Page):
        raise NotImplementedError

    def scrape_product_page(self, page: Page, url: str) -> Optional[dict]:
        raise NotImplementedError
