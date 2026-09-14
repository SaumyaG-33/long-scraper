"""
Downloads the RentTheRunway clothing-fit dataset (public, no auth needed).

Source: Misra et al., "Decomposing fit semantics for product size
recommendation in metric spaces", RecSys 2018.
https://cseweb.ucsd.edu/~jmcauley/datasets.html#clothing_fit

Run once:
    python -m fit_model.download_data
"""
import gzip
import shutil
from pathlib import Path

import requests

URL = "https://mcauleylab.ucsd.edu/public_datasets/data/renttherunway/renttherunway_final_data.json.gz"
HERE = Path(__file__).parent
GZ_PATH = HERE / "data" / "renttherunway_final_data.json.gz"
JSON_PATH = HERE / "data" / "renttherunway_final_data.json"


def main():
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if JSON_PATH.exists():
        print(f"already have {JSON_PATH}")
        return

    print(f"downloading {URL} ...")
    resp = requests.get(URL, timeout=120)
    resp.raise_for_status()
    GZ_PATH.write_bytes(resp.content)
    print(f"  {len(resp.content) / 1e6:.1f} MB")

    with gzip.open(GZ_PATH, "rb") as src, open(JSON_PATH, "wb") as dst:
        shutil.copyfileobj(src, dst)
    GZ_PATH.unlink()
    print(f"saved -> {JSON_PATH}")


if __name__ == "__main__":
    main()
