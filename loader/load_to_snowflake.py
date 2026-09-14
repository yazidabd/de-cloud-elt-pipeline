import glob
import json
import os
import sys
from datetime import datetime, timezone

import snowflake.connector
from cryptography.hazmat.primitives import serialization

LANDING_DIR = os.path.join(os.path.dirname(__file__), "..", "extractor", "landing")
STAGING_TMP_DIR = os.path.join(os.path.dirname(__file__), "staging_tmp")
PRIVATE_KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "secrets", "rsa_key.p8")

DATABASE = "ELT_PORTFOLIO"
SCHEMA = "RAW"
STAGE = "RAW_LANDING_STAGE"
ROLE = "ELT_LOADER_ROLE"
WAREHOUSE = "ELT_PORTFOLIO_WH"

# daftar file yang mau diproses, dipetakan ke nama raw table tujuannya
SOURCE_FILE_PATTERNS = {
    "products": "RAW_PRODUCTS",
    "orders": "RAW_ORDERS",
}


# baca private key terenkripsi dan ubah ke format DER yang dibutuhkan snowflake-connector-python
# passphrase diambil dari env var, gak pernah ditulis di kode
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


# buka koneksi ke Snowflake pakai key-pair auth, konsisten sama cara auth di terraform
def get_connection():
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


# pastikan raw table dan tabel kontrol LOADED_FILES sudah ada sebelum load pertama kali
def ensure_tables_exist(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            raw_data VARIANT,
            loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS LOADED_FILES (
            file_name STRING,
            loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """)
    cursor.close()


# cek apakah file ini sudah pernah diproses sebelumnya, biar loader idempotent
# dan aman dijalanin berkali-kali tanpa duplikasi data
def is_already_loaded(conn, file_name):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM LOADED_FILES WHERE file_name = %s", (file_name,)
    )
    count = cursor.fetchone()[0]
    cursor.close()
    return count > 0


# buka file wrapper hasil extract (punya field extraction_date dan data),
# lalu pecah jadi satu baris JSON per record (JSONL), karena COPY INTO Snowflake
# butuh satu JSON object per baris/dokumen, bukan array bersarang di dalam objek
def unwrap_to_jsonl(landing_filepath, output_dir):
    with open(landing_filepath) as f:
        wrapper = json.load(f)

    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.basename(landing_filepath).replace(".json", ".jsonl")
    output_path = os.path.join(output_dir, base_name)

    with open(output_path, "w") as out:
        for record in wrapper["data"]:
            enriched_record = {
                "extraction_date": wrapper["extraction_date"],
                "source_file": os.path.basename(landing_filepath),
                "record": record,
            }
            out.write(json.dumps(enriched_record) + "\n")

    return output_path


# upload file JSONL ke internal stage, lalu COPY INTO raw table
# nama file di stage dijadikan unik pakai timestamp biar gak numpuk/ketimpa antar run
def upload_and_copy(conn, jsonl_path, table_name):
    cursor = conn.cursor()
    stage_filename = os.path.basename(jsonl_path)

    cursor.execute(f"PUT file://{jsonl_path} @{STAGE} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
    cursor.execute(f"""
        COPY INTO {table_name} (raw_data)
        FROM @{STAGE}/{stage_filename}.gz
        FILE_FORMAT = (TYPE = JSON)
        ON_ERROR = 'ABORT_STATEMENT'
    """)
    cursor.close()


def mark_as_loaded(conn, file_name):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO LOADED_FILES (file_name) VALUES (%s)", (file_name,))
    cursor.close()


def main():
    conn = get_connection()

    try:
        for prefix, table_name in SOURCE_FILE_PATTERNS.items():
            ensure_tables_exist(conn, table_name)

            pattern = os.path.join(LANDING_DIR, f"{prefix}_*.json")
            for landing_filepath in sorted(glob.glob(pattern)):
                file_name = os.path.basename(landing_filepath)

                if is_already_loaded(conn, file_name):
                    print(f"Skip {file_name}, sudah pernah di-load sebelumnya")
                    continue

                jsonl_path = unwrap_to_jsonl(landing_filepath, STAGING_TMP_DIR)
                upload_and_copy(conn, jsonl_path, table_name)
                mark_as_loaded(conn, file_name)
                print(f"Loaded {file_name} ke {table_name}")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Loader gagal: {e}", file=sys.stderr)
        sys.exit(1)
