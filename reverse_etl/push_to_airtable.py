import os
import sys
import time

import requests
import snowflake.connector
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
PRIVATE_KEY_PATH = os.path.join(PROJECT_ROOT, "secrets", "rsa_key.p8")

load_dotenv(os.path.join(PROJECT_ROOT, ".env.airtable"))

DATABASE = "ELT_PORTFOLIO"
SCHEMA = "STAGING_MARTS"
WAREHOUSE = "ELT_PORTFOLIO_WH"
ROLE = "ELT_LOADER_ROLE"

AIRTABLE_MAX_RECORDS_PER_REQUEST = 10  # batas resmi Airtable per API call
MAX_RETRIES = 5


def load_private_key():
    passphrase = os.environ["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"]
    with open(PRIVATE_KEY_PATH, "rb") as key_file:
        p_key = serialization.load_pem_private_key(
            key_file.read(),
            password=passphrase.encode(),
        )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_snowflake_connection():
    account = f"{os.environ['SNOWFLAKE_ORGANIZATION_NAME']}-{os.environ['SNOWFLAKE_ACCOUNT_NAME']}"
    return snowflake.connector.connect(
        account=account,
        user=os.environ["SNOWFLAKE_USER"],
        private_key=load_private_key(),
        warehouse=WAREHOUSE,
        database=DATABASE,
        schema=SCHEMA,
        role=ROLE,
    )


def fetch_daily_summary(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date_key, total_orders, total_quantity, total_revenue, total_discounted_revenue
        FROM agg_daily_sales_summary
        ORDER BY date_key
    """)
    columns = [col[0].lower() for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    return rows


def to_airtable_fields(row):
    return {
        "date_key": row["date_key"].isoformat(),
        "total_orders": row["total_orders"],
        "total_quantity": row["total_quantity"],
        "total_revenue": float(row["total_revenue"]),
        "total_discounted_revenue": float(row["total_discounted_revenue"]),
    }


def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# request wrapper dengan exponential backoff: kalau Airtable balikin 429 (rate limit)
# atau error 5xx sementara, retry dengan jeda yang makin lama tiap percobaan
# (1s, 2s, 4s, 8s, 16s), bukan langsung crash di percobaan pertama
def request_with_backoff(method, url, headers, json_payload):
    for attempt in range(MAX_RETRIES):
        response = requests.request(method, url, headers=headers, json=json_payload, timeout=15)

        if response.status_code == 429:
            wait_seconds = 2 ** attempt
            print(f"Rate limited (429), retry in {wait_seconds}s (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait_seconds)
            continue

        if response.status_code >= 500:
            wait_seconds = 2 ** attempt
            print(f"Server error {response.status_code}, retry in {wait_seconds}s (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait_seconds)
            continue

        response.raise_for_status()
        return response

    raise RuntimeError(f"Gagal setelah {MAX_RETRIES} kali percobaan: {method} {url}")


# upsert pakai endpoint batch resmi Airtable (performUpsert), sampai 10 record
# per request. fieldsToMergeOn: ["date_key"] artinya Airtable sendiri yang
# menentukan insert vs update berdasarkan kecocokan date_key, kita gak perlu
# lagi fetch existing record manual seperti pendekatan sebelumnya
def upsert_batch(base_url, headers, rows):
    for batch in chunk_list(rows, AIRTABLE_MAX_RECORDS_PER_REQUEST):
        payload = {
            "performUpsert": {"fieldsToMergeOn": ["date_key"]},
            "records": [{"fields": to_airtable_fields(row)} for row in batch],
        }
        response = request_with_backoff("PATCH", base_url, headers, payload)
        result = response.json()
        updated = len(result.get("updatedRecords", []))
        created = len(result.get("createdRecords", []))
        print(f"Batch pushed: {created} created, {updated} updated")


def main():
    token = os.environ["AIRTABLE_TOKEN"]
    base_id = os.environ["AIRTABLE_BASE_ID"]
    table_name = os.environ["AIRTABLE_TABLE_NAME"]

    base_url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    conn = get_snowflake_connection()
    try:
        rows = fetch_daily_summary(conn)
    finally:
        conn.close()

    if not rows:
        print("Tidak ada data untuk di-push")
        return

    upsert_batch(base_url, headers, rows)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Reverse ETL gagal: {e}", file=sys.stderr)
        sys.exit(1)
