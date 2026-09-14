import json
import os
import random
import sys
from datetime import datetime, timezone

import requests

FAKESTORE_PRODUCTS_URL = "https://fakestoreapi.com/products"
STATE_FILE = os.path.join(os.path.dirname(__file__), "order_id_counter.txt")


# ambil katalog produk asli dari FakeStoreAPI, dipakai sebagai referensi
# harga dan judul produk biar order yang di-generate tetap konsisten sama katalog
def fetch_product_catalog(api_url=FAKESTORE_PRODUCTS_URL, timeout=10):
    response = requests.get(api_url, timeout=timeout)
    response.raise_for_status()
    return response.json()


# baca order_id terakhir yang pernah dipakai, biar ID terus nambah antar hari
# bukan reset dari 1 tiap kali extractor jalan
# state_file di-resolve di dalam fungsi (bukan di default parameter) supaya
# kalau STATE_FILE di-reassign dari luar (misal dari test), perubahannya kepakai
def get_next_order_id_start(state_file=None):
    if state_file is None:
        state_file = STATE_FILE
    if not os.path.exists(state_file):
        return 1
    with open(state_file) as f:
        return int(f.read().strip()) + 1


def save_last_order_id(last_id, state_file=None):
    if state_file is None:
        state_file = STATE_FILE
    with open(state_file, "w") as f:
        f.write(str(last_id))


# bikin satu order sintetis: pilih 1-5 produk acak dari katalog, quantity dan
# discount acak, lalu hitung total sesuai harga asli produknya
def generate_synthetic_order(order_id, catalog):
    num_items = random.randint(1, 5)
    chosen_products = random.sample(catalog, k=min(num_items, len(catalog)))

    items = []
    total = 0.0
    total_quantity = 0
    for product in chosen_products:
        quantity = random.randint(1, 4)
        price = float(product["price"])
        discount_percentage = round(random.uniform(0, 20), 2)
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
        "userId": random.randint(1, 50),
        "products": items,
        "total": round(total, 2),
        "discountedTotal": round(sum(i["discountedTotal"] for i in items), 2),
        "totalProducts": len(items),
        "totalQuantity": total_quantity,
    }


# generate sejumlah order acak (20-40 per hari) buat satu batch extraction
def generate_orders(catalog, num_orders=None):
    if num_orders is None:
        num_orders = random.randint(20, 40)

    start_id = get_next_order_id_start()
    orders = [generate_synthetic_order(start_id + i, catalog) for i in range(num_orders)]
    save_last_order_id(start_id + num_orders - 1)
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


def main():
    extraction_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = os.path.join(os.path.dirname(__file__), "landing")

    catalog = fetch_product_catalog()
    orders = generate_orders(catalog)
    record = build_extraction_record(orders, extraction_date)
    filepath = save_to_landing(record, output_dir)

    print(f"Generated {record['record_count']} synthetic orders to {filepath}")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch product catalog: {e}", file=sys.stderr)
        sys.exit(1)
