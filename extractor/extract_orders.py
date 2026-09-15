import argparse
import json
import os
import random
import sys
from datetime import date, datetime, timezone

import requests

FAKESTORE_PRODUCTS_URL = "https://fakestoreapi.com/products"
EPOCH_DATE = date(2026, 1, 1)  # tanggal referensi buat hitung day_index yang deterministik


# ambil katalog produk asli dari FakeStoreAPI, dipakai sebagai referensi
# harga dan judul produk biar order yang di-generate tetap konsisten sama katalog
def fetch_product_catalog(api_url=FAKESTORE_PRODUCTS_URL, timeout=10):
    response = requests.get(api_url, timeout=timeout)
    response.raise_for_status()
    return response.json()


# hitung day_index dari execution_date, dipakai sebagai basis order_id dan random seed
# ini yang bikin extractor idempotent dan backfill-safe: tanggal yang sama SELALU
# menghasilkan day_index yang sama, berapa kali pun di-run ulang (beda dari counter
# file yang incremental dan berubah tergantung riwayat eksekusi sebelumnya)
def get_day_index(execution_date):
    return (execution_date - EPOCH_DATE).days


# bikin satu order sintetis: pilih 1-5 produk acak dari katalog, quantity dan
# discount acak, lalu hitung total sesuai harga asli produknya
# rng di-pass dari luar (bukan modul random global) supaya hasilnya reproducible
# per execution_date, bukan tergantung state global yang bisa berubah antar run
def generate_synthetic_order(order_id, catalog, rng):
    num_items = rng.randint(1, 5)
    chosen_products = rng.sample(catalog, k=min(num_items, len(catalog)))

    items = []
    total = 0.0
    total_quantity = 0
    for product in chosen_products:
        quantity = rng.randint(1, 4)
        price = float(product["price"])
        discount_percentage = round(rng.uniform(0, 20), 2)
        item_total = round(price * quantity, 2)
        discounted_total = round(item_total * (1 - discount_percentage / 100), 2)

        items.append({
            "id": product["id"],
            "title": product["title"],
            "price": price,
            "quantity": quantity,
            "total": item_total,
            "discountPercentage": discount_percentage,
            "discountedTotal": discounted_total,
        })
        total += item_total
        total_quantity += quantity

    return {
        "id": order_id,
        "userId": rng.randint(1, 50),
        "products": items,
        "total": round(total, 2),
        "discountedTotal": round(sum(i["discountedTotal"] for i in items), 2),
        "totalProducts": len(items),
        "totalQuantity": total_quantity,
    }


# generate seluruh order buat satu execution_date, sepenuhnya deterministik:
# execution_date yang sama akan selalu menghasilkan jumlah order, order_id,
# dan isi order yang identik, aman untuk backfill/re-run tanpa duplikasi logic
def generate_orders_for_date(catalog, execution_date):
    day_index = get_day_index(execution_date)
    rng = random.Random(day_index)  # seed dari day_index, bukan random.seed() global

    num_orders = rng.randint(20, 40)
    start_id = day_index * 100 + 1  # blok 100 ID per hari, cukup untuk num_orders max 40

    orders = [generate_synthetic_order(start_id + i, catalog, rng) for i in range(num_orders)]
    return orders


def build_extraction_record(orders, extraction_date):
    return {
        "extraction_date": extraction_date,
        "source": "synthetic_orders_faker",
        "record_count": len(orders),
        "data": orders,
    }


def save_to_landing(record, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    filename = f"orders_{record['extraction_date']}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w") as f:
        json.dump(record, f, indent=2)
    return filepath


def parse_execution_date(date_str):
    if date_str is None:
        return datetime.now(timezone.utc).date()
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execution-date",
        type=str,
        default=None,
        help="Tanggal eksekusi (YYYY-MM-DD), default hari ini. Dikirim Airflow via {{ ds }}.",
    )
    args = parser.parse_args()
    execution_date = parse_execution_date(args.execution_date)

    output_dir = os.path.join(os.path.dirname(__file__), "landing")

    catalog = fetch_product_catalog()
    orders = generate_orders_for_date(catalog, execution_date)
    record = build_extraction_record(orders, execution_date.isoformat())
    filepath = save_to_landing(record, output_dir)

    print(f"Generated {record['record_count']} synthetic orders for {execution_date} to {filepath}")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch product catalog: {e}", file=sys.stderr)
        sys.exit(1)
