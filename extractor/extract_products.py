import json
import os
import sys
from datetime import datetime, timezone

import requests

FAKESTORE_API_URL = "https://fakestoreapi.com/products"


# ambil seluruh data produk dari FakeStoreAPI
# dipisah dari logic penyimpanan supaya gampang di-unit-test tanpa perlu nulis file
def fetch_products(api_url=FAKESTORE_API_URL, timeout=10):
    response = requests.get(api_url, timeout=timeout)
    response.raise_for_status()
    return response.json()


# bungkus data mentah dengan metadata extraction_date
# extraction_date dipakai loader buat partisi dan buat filter incremental load
def build_extraction_record(products, extraction_date):
    return {
        "extraction_date": extraction_date,
        "source": "fakestoreapi",
        "record_count": len(products),
        "data": products,
    }


# simpan record ke landing folder lokal, sebelum di-PUT ke Snowflake stage
# nama file include tanggal biar gampang dicek manual dan gak numpuk jadi satu file besar
def save_to_landing(record, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"products_{record['extraction_date']}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w") as f:
        json.dump(record, f, indent=2)
    return filepath


def main():
    extraction_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = os.path.join(os.path.dirname(__file__), "landing")

    products = fetch_products()
    record = build_extraction_record(products, extraction_date)
    filepath = save_to_landing(record, output_dir)

    print(f"Extracted {record['record_count']} products to {filepath}")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch products: {e}", file=sys.stderr)
        sys.exit(1)
