import json
import os
import tempfile

import requests_mock

import extract_products
import extract_orders


def test_fetch_products_success():
    fake_response = [{"id": 1, "title": "Test Product", "price": 10.5}]
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


# cek satu order sintetis punya struktur field yang benar dan total sesuai hitungan manual
def test_generate_synthetic_order_structure():
    catalog = [
        {"id": 1, "title": "Product A", "price": 10.0},
        {"id": 2, "title": "Product B", "price": 20.0},
    ]
    order = extract_orders.generate_synthetic_order(order_id=999, catalog=catalog)

    assert order["id"] == 999
    assert 1 <= order["totalProducts"] <= 2
    assert order["totalQuantity"] > 0
    assert order["total"] >= order["discountedTotal"]
    for item in order["products"]:
        assert item["total"] == round(item["price"] * item["quantity"], 2)


# cek order_id nyambung dari state file, bukan reset ke 1 tiap kali dipanggil
def test_order_id_continues_from_state_file():
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = os.path.join(tmp_dir, "order_id_counter.txt")
        extract_orders.save_last_order_id(50, state_file=state_file)

        next_start = extract_orders.get_next_order_id_start(state_file=state_file)
        assert next_start == 51


# cek generate_orders benar-benar update state file setelah generate
def test_generate_orders_updates_state_file():
    catalog = [{"id": 1, "title": "A", "price": 10.0}]
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = os.path.join(tmp_dir, "order_id_counter.txt")

        original_state_file = extract_orders.STATE_FILE
        extract_orders.STATE_FILE = state_file
        try:
            orders = extract_orders.generate_orders(catalog, num_orders=5)
            assert len(orders) == 5
            assert orders[0]["id"] == 1
            assert orders[4]["id"] == 5

            with open(state_file) as f:
                assert f.read().strip() == "5"
        finally:
            extract_orders.STATE_FILE = original_state_file
