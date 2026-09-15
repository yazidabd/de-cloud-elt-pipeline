# Cloud ELT Pipeline: E-Commerce Sales Analytics

Batch ELT pipeline yang meng-extract data katalog produk dan transaksi
e-commerce, memuatnya ke Snowflake, mentransformasinya dengan dbt menjadi
star schema, mengorkestrasi seluruh alur dengan Airflow, mendorong ringkasan
harian ke Airtable lewat Reverse ETL, dan menyajikannya lewat dashboard
Streamlit. Pipeline dirancang backfill-safe dan cost-aware, bukan sekadar
skala portfolio.

## Arsitektur

```
FakeStoreAPI (katalog produk)
   -> Extractor (Python, generate order sintetis deterministik per execution_date)
   -> Snowflake internal stage
   -> COPY INTO raw table (Snowflake)
   -> dbt: staging -> marts (star schema, incremental)
   -> dbt test (data quality)
   -> Reverse ETL -> Airtable (batch upsert + retry backoff)
   -> Streamlit dashboard
```

Seluruh alur di atas diorkestrasi oleh satu Airflow DAG (`cloud_elt_dag`),
dijadwalkan berjalan harian, dan aman di-backfill untuk tanggal manapun.

## Tech Stack

| Layer | Tool |
|---|---|
| Sumber data | FakeStoreAPI (katalog produk), order sintetis (generator deterministik) |
| Validasi schema | Pydantic |
| Landing/raw storage | Snowflake internal stage |
| Data warehouse | Snowflake |
| Transformasi | dbt (dbt-snowflake), incremental models |
| Orchestration | Apache Airflow |
| Infrastructure as Code | Terraform |
| Reverse ETL | Airtable (batch upsert, exponential backoff) |
| BI/dashboard | Streamlit (cached, TTL 5 menit) |
| Testing | pytest, dbt test |
| CI/CD | GitHub Actions |

## Struktur Proyek

```
terraform/       Provisioning infra Snowflake (warehouse, database, schema, stage, role)
extractor/       Extract katalog produk + generate order sintetis (deterministik per execution_date)
loader/          Load data ke Snowflake (internal stage -> raw table, idempotent)
dbt_project/     Transformasi (staging -> marts, star schema, incremental)
airflow/         Orkestrasi seluruh pipeline (DAG harian, backfill-safe)
reverse_etl/     Push ringkasan harian ke Airtable (batch upsert + retry)
dashboard/       Dashboard Streamlit
```

## Setup

Setiap komponen punya virtual environment Python terpisah
(`extractor/venv`, `loader/venv`, `dbt_project/venv`, `reverse_etl/venv`,
`dashboard/venv`, `airflow/venv`), diinstall sesuai kebutuhan masing-masing
lewat `requirements.txt` di tiap folder.

### Prasyarat

- Python 3.12 (khusus `extractor/`, karena `pydantic-core` belum mendukung
  Python 3.14 saat proyek ini dibuat; komponen lain bisa pakai Python 3.12+)
- Terraform 1.x
- Akun Snowflake (trial cukup)
- Akun Airtable
- Key-pair authentication Snowflake (private key RSA, disimpan lokal di
  `secrets/`, tidak pernah dikomit)

### Environment Variables

```
SNOWFLAKE_ORGANIZATION_NAME
SNOWFLAKE_ACCOUNT_NAME
SNOWFLAKE_USER
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE
```

### Menjalankan Manual

```bash
# 1. Provisioning infra
cd terraform && terraform init && terraform apply

# 2. Extract (--execution-date opsional, default hari ini; dipakai Airflow untuk backfill)
cd extractor && source venv/bin/activate
python extract_products.py --execution-date 2026-09-15
python extract_orders.py --execution-date 2026-09-15

# 3. Load
cd loader && source venv/bin/activate
python load_to_snowflake.py

# 4. Transform
cd dbt_project && source venv/bin/activate
dbt run && dbt test

# 5. Reverse ETL
cd reverse_etl && source venv/bin/activate
python push_to_airtable.py

# 6. Dashboard
cd dashboard && source venv/bin/activate
streamlit run app.py
```

Atau jalankan semuanya sekaligus lewat Airflow DAG `cloud_elt_dag`
(dijadwalkan `@daily`). DAG ini backfill-safe: menjalankan ulang run untuk
tanggal manapun akan selalu menghasilkan data yang identik, dan dbt hanya
memproses data yang benar-benar baru (incremental).

## Dokumentasi Lebih Lanjut

Lihat [ARCHITECTURE.md](./ARCHITECTURE.md) untuk detail desain teknis,
keputusan arsitektur, dan known limitations.
