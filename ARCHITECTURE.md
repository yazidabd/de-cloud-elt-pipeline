# Architecture

## Ringkasan

Proyek ini mendemonstrasikan pola batch ELT (Extract-Load-Transform) end-to-end
menggunakan cloud data warehouse (Snowflake), berbeda dari pola streaming/real-time
yang didemonstrasikan pada proyek portfolio lain. Data mentah dimuat apa adanya
ke warehouse terlebih dahulu, baru ditransformasi menggunakan compute warehouse
itu sendiri lewat dbt, mengikuti praktik modern data warehousing.

## Sumber Data

Katalog produk diambil dari FakeStoreAPI (20 produk, data publik statis).
Data order/transaksi digenerate secara sintetis menggunakan pendekatan
Faker-style, mereferensikan katalog produk yang sama (harga dan judul produk
tetap konsisten dengan katalog), dengan quantity, user, dan jumlah order acak
per hari. Order ID bersifat kontinu antar hari (disimpan lewat state file lokal),
sehingga simulasi data transaksi tetap bertumbuh dan bervariasi setiap kali
pipeline dijalankan, sesuai karakteristik data transaksi pada sistem produksi.

## Data Flow

1. **Extract**: `extractor/` memanggil FakeStoreAPI untuk katalog produk, dan
   men-generate order sintetis berbasis katalog tersebut. Hasil disimpan sebagai
   JSON di `extractor/landing/`, dipartisi per `extraction_date`.
2. **Load**: `loader/` membaca file landing, mengubahnya menjadi JSONL, meng-PUT
   ke Snowflake internal stage, lalu `COPY INTO` ke raw table (kolom `VARIANT`).
   Loader bersifat idempotent, file yang sudah pernah dimuat dilacak lewat tabel
   kontrol `LOADED_FILES`.
3. **Transform**: dbt memproses raw table menjadi staging (flatten JSON jadi
   kolom biasa, termasuk `LATERAL FLATTEN` untuk array produk bersarang di
   dalam order), lalu marts (star schema: `dim_product`, `dim_date`,
   `fact_order_items`, `agg_daily_sales_summary`). 10 data test (uniqueness,
   not-null, referential integrity) memvalidasi kualitas data di setiap run.
4. **Orchestrate**: Airflow DAG `cloud_elt_dag` menjalankan seluruh alur di atas
   secara terjadwal, dengan retry policy per task.
5. **Reverse ETL**: `reverse_etl/` mengambil ringkasan harian dari
   `agg_daily_sales_summary`, dan melakukan upsert (berdasarkan `date_key`) ke
   Airtable, mendemonstrasikan pola reverse ETL yang umum dipakai untuk
   menyediakan data warehouse ke tools non-teknis.
6. **Serve**: Dashboard Streamlit membaca langsung dari marts Snowflake,
   menampilkan revenue per kategori, produk terlaris, hubungan harga-rating,
   dan tren revenue harian.

## Keputusan Arsitektur

### Mengapa Snowflake

Snowflake dipilih sebagai cloud data warehouse karena arsitektur separasi
compute-storage-nya yang menjadi standar industri saat ini, serta
ketersediaan trial account yang cukup untuk keperluan portfolio ini.

### Mengapa Batch, bukan Streaming

Pola batch ELT dipilih untuk melengkapi variasi pola data engineering yang
didemonstrasikan (pipeline lain menggunakan pola streaming/real-time dengan
Kafka). Batch ELT adalah pola paling umum digunakan untuk data non-real-time
seperti data penjualan, di mana kesegaran data setiap beberapa jam/harian
sudah mencukupi kebutuhan bisnis.

### Mengapa Internal Stage, bukan Cloud Storage Terpisah

Snowflake internal stage digunakan sebagai landing zone, alih-alih menggunakan
layanan object storage terpisah (S3/GCS/Blob Storage). Ini menyederhanakan
arsitektur tanpa mengorbankan pola landing-before-transform, karena internal
stage pada dasarnya adalah object storage terkelola yang sudah terintegrasi
langsung dengan Snowflake.

## Keamanan

- Autentikasi ke Snowflake menggunakan key-pair authentication (RSA, JWT),
  bukan password, sesuai rekomendasi keamanan Snowflake untuk service account
  dan integrasi otomatis.
- Role Snowflake dipisah berdasarkan prinsip least privilege: role khusus
  (`ELT_LOADER_ROLE`) hanya memiliki privilege yang benar-benar diperlukan
  pada database dan warehouse proyek ini, terpisah dari role administratif
  (`SYSADMIN`, `SECURITYADMIN`) yang hanya digunakan saat provisioning infra
  lewat Terraform.
- Seluruh credential (private key, token Airtable, token GitHub) disimpan
  secara lokal di dalam folder proyek namun sepenuhnya dikecualikan dari
  version control lewat `.gitignore`, tidak pernah dikomit ke repository.
- Di CI/CD, credential disimpan sebagai GitHub Secrets (private key dienkode
  base64 untuk menghindari korupsi format PEM saat disuntikkan ke shell
  runner), dan hanya diinject saat workflow berjalan, tidak pernah tersimpan
  dalam bentuk file dalam repository.
- Reverse ETL ke Airtable hanya mengirim data agregat (ringkasan harian),
  tidak pernah data mentah/transaksi individual, membatasi eksposur data pada
  sistem downstream yang kontrolnya lebih longgar dibanding data warehouse.

## Known Limitations

- Data bersifat sintetis/simulasi untuk keperluan portfolio, bukan data
  transaksi nyata. Katalog produk statis (20 item dari FakeStoreAPI), order
  digenerate secara sintetis untuk mensimulasikan variasi transaksi harian.
- CI job `test-dbt` melakukan koneksi langsung ke Snowflake pada setiap push
  ke branch `main`. Ini secara sadar dipilih agar CI benar-benar memvalidasi
  pipeline dbt end-to-end, dengan konsekuensi biaya compute Snowflake perlu
  dipantau setelah masa trial berakhir.
