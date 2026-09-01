"""
Entrypoint: run one or more scrapers and upsert results into MongoDB Atlas.

Usage:
    python main.py --retailer asos_tall --max 30
    python main.py --retailer asos_tall --max 30 --dry-run   # scrape only, don't write to DB
"""
import argparse
from dotenv import load_dotenv

load_dotenv()

from scrapers.asos_tall import AsosTallScraper
from scrapers.uniqlo import UniqloScraper
from scrapers.comfrt import ComfrtScraper
from scrapers.old_navy import OldNavyScraper
from db import upsert_products

SCRAPERS = {
    "asos_tall": AsosTallScraper,
    "uniqlo": UniqloScraper,
    "comfrt": ComfrtScraper,
    "old_navy": OldNavyScraper,
    # "hm": HMScraper,
    # "zara": ZaraScraper,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retailer", required=True, choices=SCRAPERS.keys())
    parser.add_argument("--max", type=int, default=50, help="Max products to scrape")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't write to MongoDB")
    args = parser.parse_args()

    scraper_cls = SCRAPERS[args.retailer]
    scraper = scraper_cls()
    products = scraper.run(max_products=args.max)

    print(f"\nScraped {len(products)} products from {args.retailer}")

    if args.dry_run:
        print("Dry run — not writing to DB. Sample product:")
        if products:
            print(products[0])
        return

    result = upsert_products(products)
    print(f"MongoDB write result: {result}")


if __name__ == "__main__":
    main()
