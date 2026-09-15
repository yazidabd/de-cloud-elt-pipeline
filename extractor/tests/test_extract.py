import json
import os
import tempfile
from datetime import date

import requests_mock

import extract_products
import extract_orders


def test_fetch_products_success():
    fake_response = [{
        "id": 1,
        "title": "Test Product",
        "price": 10.5,
        "description": "A test product",
        "category": "test category",
        "image": "https://example.com/image.png",
        "rating": {"rate": 4.0, "count": 10},
    }]
    with requests_mock.Mocker() as m:
        m.get(extract_products.FAKESTORE_API_URL, json=fake_response)
        result = extract_products.fetch_products()
    assert result == fake_response


def test_fetch_products_http_error():
    with requests_mock.Mocker() as m:
        m.get(extract_products.FAKESTORE_API_URL, status_code=500)
        try:
            extract_products.fetch_products()
            assert False, "harusnya raise exception saat API error"
        except Exception:
            pass


def test_build_extraction_record():
    products = [{"id": 1}, {"id": 2}]
    record = extract_products.build_extraction_record(products, "2026-01-01")
    assert record["extraction_date"] == "2026-01-01"
    assert record["record_count"] == 2
    assert record["source"] == "fakestoreapi"


def test_save_to_landing_writes_valid_json():
    record = {"extraction_date": "2026-01-01", "record_count": 1, "data": [{"id": 1}]}
    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = extract_products.save_to_landing(record, tmp_dir)
        assert os.path.exists(filepath)
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded == record


def test_generate_synthetic_order_structure():
    catalog = [
        {"id": 1, "title": "Product A", "price": 10.0},
        {"id": 2, "title": "Product B", "price": 20.0},
    ]
    rng = extract_orders.random.Random(42)
    order = extract_orders.generate_synthetic_order(order_id=999, catalog=catalog, rng=rng)

    assert order["id"] == 999
    assert 1 <= order["totalProducts"] <= 2
    assert order["totalQuantity"] > 0
    assert order["total"] >= order["discountedTotal"]
    for item in order["products"]:
        assert item["total"] == round(item["price"] * item["quantity"], 2)


# inti dari backfill-safety: tanggal yang sama harus selalu menghasilkan
# jumlah order dan order_id yang identik, berapa kali pun dipanggil
def test_generate_orders_for_date_is_deterministic():
    catalog = [{"id": 1, "title": "A", "price": 10.0}]
    execution_date = date(2026, 3, 15)

    run_1 = extract_orders.generate_orders_for_date(catalog, execution_date)
    run_2 = extract_orders.generate_orders_for_date(catalog, execution_date)

    assert run_1 == run_2
    assert len(run_1) > 0


# tanggal berbeda harus punya order_id range yang berbeda (gak overlap),
# supaya backfill banyak hari sekaligus gak menghasilkan ID yang bentrok
def test_different_dates_produce_different_id_ranges():
    catalog = [{"id": 1, "title": "A", "price": 10.0}]

    orders_day1 = extract_orders.generate_orders_for_date(catalog, date(2026, 3, 15))
    orders_day2 = extract_orders.generate_orders_for_date(catalog, date(2026, 3, 16))

    day1_ids = {o["id"] for o in orders_day1}
    day2_ids = {o["id"] for o in orders_day2}
    assert day1_ids.isdisjoint(day2_ids)


def test_parse_execution_date():
    parsed = extract_orders.parse_execution_date("2026-03-15")
    assert parsed == date(2026, 3, 15)


def test_products_parse_execution_date_with_value():
    result = extract_products.parse_execution_date("2026-03-15")
    assert result == "2026-03-15"


def test_products_parse_execution_date_defaults_to_today():
    result = extract_products.parse_execution_date(None)
    assert len(result) == 10  # format YYYY-MM-DD


def test_fetch_products_rejects_malformed_schema():
    # simulasi API berubah struktur: price jadi string, bukan number
    malformed_response = [{
        "id": 1,
        "title": "Test",
        "price": "not_a_number",
        "description": "desc",
        "category": "cat",
        "image": "url",
        "rating": {"rate": 4.0, "count": 10},
    }]
    with requests_mock.Mocker() as m:
        m.get(extract_products.FAKESTORE_API_URL, json=malformed_response)
        try:
            extract_products.fetch_products()
            assert False, "harusnya gagal karena price bukan angka"
        except Exception:
            pass


def test_fetch_products_accepts_valid_schema():
    valid_response = [{
        "id": 1,
        "title": "Test",
        "price": 10.5,
        "description": "desc",
        "category": "cat",
        "image": "url",
        "rating": {"rate": 4.0, "count": 10},
    }]
    with requests_mock.Mocker() as m:
        m.get(extract_products.FAKESTORE_API_URL, json=valid_response)
        result = extract_products.fetch_products()
    assert result == valid_response
