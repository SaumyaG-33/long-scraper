"""
Phase 2, step 3: HTTP + minimal web UI for catalog text search.

    ./venv/bin/uvicorn api:app --reload
    open http://127.0.0.1:8000

    GET  /              -> the search page
    POST /search        -> {"query": "...", "k": 20, "category": null,
                            "max_price": null, "include_non_tall": false,
                            "height_in": null, "weight_lbs": null}
                           -> {"query": ..., "results": [ ... ]}

The heavy lifting (CLIP encode + Atlas $vectorSearch + colourway collapse)
lives in search.py; this file is just transport + a single HTML page.
The CLIP model loads once on first request.

height_in is optional — when given, each result gets a `fit_probability`
field ({"small": p, "fit": p, "large": p}) from fit_model/, scored against
that height (see fit_model/catalog_bridge.py for the honest scope of what
that model actually predicts and from what data).
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from search import search

app = FastAPI(title="Long — tall-fit search")


class SearchRequest(BaseModel):
    query: str
    k: int = 20
    category: Optional[str] = None
    max_price: Optional[float] = None
    include_non_tall: bool = False
    height_in: Optional[float] = None
    weight_lbs: Optional[float] = None


@app.post("/search")
def do_search(req: SearchRequest) -> dict:
    results = search(
        req.query,
        k=req.k,
        category=req.category,
        max_price=req.max_price,
        tall_only=not req.include_non_tall,
        height_in=req.height_in,
        weight_lbs=req.weight_lbs,
    )
    return {"query": req.query, "count": len(results), "results": results}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _PAGE


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Long — tall-fit search</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 15px/1.5 system-ui, -apple-system, sans-serif;
         background: #faf9f7; color: #1a1a1a; }
  @media (prefers-color-scheme: dark) {
    body { background: #14140f; color: #ececec; }
    .card { background: #1e1e1a; border-color: #333; }
    input, select { background: #1e1e1a; color: #ececec; border-color: #444; }
  }
  header { padding: 24px 20px 12px; max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0 0 12px; }
  form { display: flex; flex-wrap: wrap; gap: 8px; max-width: 1100px;
         margin: 0 auto; padding: 0 20px; }
  input[type=text] { flex: 1 1 320px; padding: 10px 12px; font-size: 15px;
                     border: 1px solid #ccc; border-radius: 8px; }
  select, input[type=number] { padding: 10px; border: 1px solid #ccc; border-radius: 8px; }
  button { padding: 10px 18px; font-size: 15px; border: 0; border-radius: 8px;
           background: #2f6f4f; color: #fff; cursor: pointer; }
  button:disabled { opacity: .5; cursor: wait; }
  label.chk { display: flex; align-items: center; gap: 6px; font-size: 13px; }
  #meta { max-width: 1100px; margin: 12px auto 0; padding: 0 20px; color: #888; font-size: 13px; }
  #grid { max-width: 1100px; margin: 8px auto 60px; padding: 12px 20px;
          display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 16px; }
  .card { border: 1px solid #e4e2dd; border-radius: 10px; overflow: hidden;
          background: #fff; display: flex; flex-direction: column; }
  .card a { color: inherit; text-decoration: none; display: flex; flex-direction: column; height: 100%; }
  .thumb { aspect-ratio: 3/4; background: #ece9e4; display: flex; align-items: center;
           justify-content: center; overflow: hidden; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .thumb .noimg { color: #aaa; font-size: 12px; }
  .body { padding: 10px 12px; display: flex; flex-direction: column; gap: 3px; flex: 1; }
  .brand { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #888; }
  .name { font-size: 13px; font-weight: 600; }
  .row { margin-top: auto; display: flex; justify-content: space-between; align-items: baseline;
         font-size: 12px; color: #777; padding-top: 6px; }
  .price { color: inherit; font-weight: 600; }
  .tag { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 6px;
         background: #e7f0ea; color: #2f6f4f; }
  .tag.fit-good { background: #e7f0ea; color: #2f6f4f; }
  .tag.fit-mid { background: #f5eee0; color: #8a6d1f; }
  .tag.fit-poor { background: #f5e3e0; color: #a5432f; }
  @media (prefers-color-scheme: dark) {
    .tag { background: #24382c; }
    .tag.fit-mid { background: #3a301a; }
    .tag.fit-poor { background: #3a241f; }
  }
</style>
</head>
<body>
<header><h1>Long — tall-fit search</h1></header>
<form id="f">
  <input type="text" id="q" placeholder="e.g. high-waisted wide-leg tall jeans" autofocus>
  <select id="category">
    <option value="">any category</option>
    <option>jeans</option><option>pants</option><option>tops</option>
    <option>dresses</option><option>skirts</option><option>shorts</option><option>jackets</option>
  </select>
  <input type="number" id="max_price" placeholder="max $" min="0" step="10" style="width:100px">
  <input type="number" id="height_in" placeholder="height (in)" min="48" max="90" step="1" style="width:110px"
         title="Optional — e.g. 71 for 5'11&quot;. Scores each result with the fit-probability model.">
  <label class="chk"><input type="checkbox" id="non_tall"> include non-tall</label>
  <button type="submit" id="go">Search</button>
</form>
<div id="meta"></div>
<div id="grid"></div>
<script>
const f = document.getElementById('f'), grid = document.getElementById('grid'),
      meta = document.getElementById('meta'), go = document.getElementById('go');

f.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = document.getElementById('q').value.trim();
  if (!query) return;
  go.disabled = true; meta.textContent = 'searching…'; grid.innerHTML = '';
  try {
    const r = await fetch('/search', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query,
        category: document.getElementById('category').value || null,
        max_price: parseFloat(document.getElementById('max_price').value) || null,
        include_non_tall: document.getElementById('non_tall').checked,
        height_in: parseFloat(document.getElementById('height_in').value) || null,
      }),
    });
    const data = await r.json();
    meta.textContent = data.count + ' results for "' + data.query + '"';
    for (const p of data.results) grid.appendChild(card(p));
  } catch (err) {
    meta.textContent = 'error: ' + err;
  } finally {
    go.disabled = false;
  }
});

function card(p) {
  const el = document.createElement('div');
  el.className = 'card';
  const img = (p.image_urls && p.image_urls[0])
    ? `<img src="${p.image_urls[0]}" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'noimg',textContent:'no image'}))">`
    : `<span class="noimg">no image</span>`;
  const colours = p.colour_count > 1 ? ` · +${p.colour_count - 1} colours` : '';
  const tall = p.tall_specific ? `<span class="tag">tall</span>` : '';
  el.innerHTML = `
    <a href="${p.source_url}" target="_blank" rel="noopener">
      <div class="thumb">${img}</div>
      <div class="body">
        <span class="brand">${p.brand || p.retailer}</span>
        <span class="name">${p.name}</span>
        <div class="row">
          <span class="price">$${p.price.toFixed(0)}</span>
          <span>${p.category}${colours}</span>
        </div>
        <div class="row"><span>score ${p.score.toFixed(3)}</span>${tall}${fitTag(p.fit_probability)}</div>
      </div>
    </a>`;
  return el;
}

function fitTag(fitProbability) {
  if (!fitProbability) return '';
  const fitP = fitProbability.fit || 0;
  const cls = fitP >= 0.45 ? 'fit-good' : fitP >= 0.3 ? 'fit-mid' : 'fit-poor';
  return `<span class="tag ${cls}" title="small ${((fitProbability.small||0)*100).toFixed(0)}% · fit ${(fitP*100).toFixed(0)}% · large ${((fitProbability.large||0)*100).toFixed(0)}%">${(fitP*100).toFixed(0)}% fit</span>`;
}
</script>
</body>
</html>"""
