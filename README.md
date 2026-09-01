# Long — Scraper

Scrapes tall-fit fashion product data into MongoDB Atlas. Phase 1 of the Long build.

## Setup (run once)

```bash
# from inside the scraper/ folder
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium     # downloads the browser Playwright drives

cp .env.example .env
# now open .env and paste in your real MongoDB Atlas connection string
```

### Getting a MongoDB Atlas connection string
1. Go to your Atlas cluster → **Connect** → **Drivers**
2. Copy the connection string (looks like `mongodb+srv://user:pass@cluster.mongodb.net/...`)
3. Paste it into `.env` as `MONGODB_URI`
4. In Atlas → **Network Access**, make sure your current IP is allowlisted (or allow 0.0.0.0/0 for now while developing locally — tighten later)

## Running it

```bash
source venv/bin/activate   # if not already active

# Dry run first — scrapes but doesn't write to DB, good for checking selectors work
python main.py --retailer asos_tall --max 10 --dry-run

# Once that looks right, run for real
python main.py --retailer asos_tall --max 50
```

## When selectors break (they will)

ASOS changes their site structure periodically. If `scrape_listing_page` or
`scrape_product_page` in `scrapers/asos_tall.py` returns nothing or errors:

1. Set `HEADLESS=false` in `.env`
2. Run with `--max 1` so it stops after one product
3. Watch the actual browser window Playwright opens, and open devtools (F12)
   on the real page to find the current selectors
4. Update the selectors in `asos_tall.py`

This is a normal part of scraping — not a sign anything is broken beyond repair.

## What gets stored

Every scraped product lands in the `products` collection in MongoDB, matching
the schema documented in `scrapers/base_scraper.py`. Re-running the scraper
upserts (updates existing products by URL, doesn't duplicate).

## Next steps after this works

1. Get `asos_tall` reliably pulling 100+ products across a few categories
2. Fill in `mainstream_stubs.py` for Uniqlo → H&M → Zara (in that order —
   easiest to hardest)
3. Move to Phase 2: CLIP embeddings over the scraped catalog
