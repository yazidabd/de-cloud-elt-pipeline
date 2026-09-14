import os
import sys

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


# baca private key terenkripsi, sama persis caranya kayak di loader
# supaya cara auth konsisten di semua komponen yang connect ke Snowflake
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


# ambil seluruh baris agregat harian dari marts, dikonversi jadi list of dict
# biar gampang dipetakan ke format field Airtable
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


# cari semua record yang udah ada di Airtable, dipetakan by date_key
# supaya push berikutnya bisa update record lama, bukan bikin duplikat
def fetch_existing_airtable_records(base_url, headers):
    existing = {}
    offset = None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        response = requests.get(base_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        for record in payload.get("records", []):
            date_key = record.get("fields", {}).get("date_key")
            if date_key:
                existing[date_key] = record["id"]
        offset = payload.get("offset")
        if not offset:
            break
    return existing


# konversi satu baris hasil query Snowflake jadi format field Airtable
# date_key dikonversi ke string ISO karena Airtable field Date butuh format itu
def to_airtable_fields(row):
    return {
        "date_key": row["date_key"].isoformat(),
        "total_orders": row["total_orders"],
        "total_quantity": row["total_quantity"],
        "total_revenue": float(row["total_revenue"]),
        "total_discounted_revenue": float(row["total_discounted_revenue"]),
    }


# upsert ke Airtable: PATCH kalau date_key udah ada record-nya, POST kalau belum
def upsert_to_airtable(base_url, headers, rows, existing_records):
    for row in rows:
        fields = to_airtable_fields(row)
        date_key = fields["date_key"]

        if date_key in existing_records:
            record_id = existing_records[date_key]
            response = requests.patch(
                f"{base_url}/{record_id}",
                headers=headers,
                json={"fields": fields},
                timeout=10,
            )
        else:
            response = requests.post(
                base_url,
                headers=headers,
                json={"fields": fields},
                timeout=10,
            )

        response.raise_for_status()
        print(f"Pushed {date_key} to Airtable")


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

    existing_records = fetch_existing_airtable_records(base_url, headers)
    upsert_to_airtable(base_url, headers, rows, existing_records)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Reverse ETL gagal: {e}", file=sys.stderr)
        sys.exit(1)
