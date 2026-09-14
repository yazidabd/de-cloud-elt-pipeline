# Cloud ELT Pipeline: E-Commerce Sales Analytics

Batch ELT pipeline yang meng-extract data katalog produk dan transaksi
e-commerce, memuatnya ke Snowflake, mentransformasinya dengan dbt menjadi
star schema, mengorkestrasi seluruh alur dengan Airflow, mendorong ringkasan
harian ke Airtable lewat Reverse ETL, dan menyajikannya lewat dashboard
Streamlit.

## Arsitektur

```
FakeStoreAPI (katalog produk)
   -> Extractor (Python, generate order sintetis berbasis katalog produk asli)
   -> Snowflake internal stage
   -> COPY INTO raw table (Snowflake)
   -> dbt: staging -> marts (star schema)
   -> dbt test (data quality)
   -> Reverse ETL -> Airtable
   -> Streamlit dashboard
```

Seluruh alur di atas diorkestrasi oleh satu Airflow DAG (`cloud_elt_dag`),
dijadwalkan berjalan harian.

## Tech Stack

| Layer | Tool |
|---|---|
| Sumber data | FakeStoreAPI (katalog produk), order sintetis (Faker) |
| Landing/raw storage | Snowflake internal stage |
| Data warehouse | Snowflake |
| Transformasi | dbt (dbt-snowflake) |
| Orchestration | Apache Airflow |
| Infrastructure as Code | Terraform |
| Reverse ETL | Airtable |
| BI/dashboard | Streamlit |
| Testing | pytest, dbt test |
| CI/CD | GitHub Actions |

## Struktur Proyek

```
terraform/       Provisioning infra Snowflake (warehouse, database, schema, stage, role)
extractor/       Extract katalog produk + generate order sintetis
loader/          Load data ke Snowflake (internal stage -> raw table)
dbt_project/     Transformasi (staging -> marts, star schema)
airflow/         Orkestrasi seluruh pipeline (DAG harian)
reverse_etl/     Push ringkasan harian ke Airtable
dashboard/       Dashboard Streamlit
```

## Setup

Setiap komponen punya virtual environment Python terpisah
(`extractor/venv`, `loader/venv`, `dbt_project/venv`, `reverse_etl/venv`,
`dashboard/venv`, `airflow/venv`), diinstall sesuai kebutuhan masing-masing
lewat `requirements.txt` di tiap folder.

### Prasyarat

- Python 3.12+
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

# 2. Extract
cd extractor && source venv/bin/activate
python extract_products.py
python extract_orders.py

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
(dijadwalkan `@daily`).

## Dokumentasi Lebih Lanjut

Lihat [ARCHITECTURE.md](./ARCHITECTURE.md) untuk detail desain teknis,
keputusan arsitektur, dan known limitations.
