# Architecture

## Ringkasan

Proyek ini mendemonstrasikan pola batch ELT (Extract-Load-Transform) end-to-end
menggunakan cloud data warehouse (Snowflake), berbeda dari pola streaming/real-time
yang didemonstrasikan pada proyek portfolio lain. Data mentah dimuat apa adanya
ke warehouse terlebih dahulu, baru ditransformasi menggunakan compute warehouse
itu sendiri lewat dbt, mengikuti praktik modern data warehousing. Pipeline
dirancang dengan prinsip production-grade: backfill-safe, incremental, dan
resilient terhadap kegagalan API eksternal.

## Sumber Data

Katalog produk diambil dari FakeStoreAPI (20 produk, data publik statis),
divalidasi strukturnya lewat Pydantic sebelum diproses lebih lanjut (lihat
bagian Schema Validation). Data order/transaksi digenerate secara sintetis,
mereferensikan katalog produk yang sama (harga dan judul produk tetap
konsisten dengan katalog).

Generasi order bersifat deterministik terhadap `execution_date`: jumlah
order, `order_id`, dan seluruh isi order untuk tanggal tertentu SELALU sama
berapa kali pun tanggal itu diproses ulang (di-seed dari `day_index`, bukan
dari state file yang incremental). Ini yang membuat proses backfill aman,
menjalankan ulang pipeline untuk tanggal 3 hari lalu akan menghasilkan data
yang identik dengan run originalnya, bukan data yang berbeda.

## Data Flow

1. **Extract**: `extractor/` menerima parameter `--execution-date` (dikirim
   Airflow lewat `{{ ds }}`), memanggil FakeStoreAPI untuk katalog produk,
   dan men-generate order sintetis deterministik berbasis katalog tersebut.
   Hasil disimpan sebagai JSON di `extractor/landing/`, dipartisi per
   `extraction_date`.
2. **Load**: `loader/` membaca file landing, mengubahnya menjadi JSONL, meng-PUT
   ke Snowflake internal stage, lalu `COPY INTO` ke raw table (kolom `VARIANT`).
   Loader bersifat idempotent, file yang sudah pernah dimuat dilacak lewat tabel
   kontrol `LOADED_FILES`.
3. **Transform**: dbt memproses raw table menjadi staging (flatten JSON jadi
   kolom biasa, termasuk `LATERAL FLATTEN` untuk array produk bersarang di
   dalam order), lalu marts (star schema: `dim_product`, `dim_date`,
   `fact_order_items`, `agg_daily_sales_summary`). `fact_order_items` dan
   `agg_daily_sales_summary` menggunakan materialisasi `incremental` (merge
   strategy), memproses hanya data baru berdasarkan `loaded_at`, bukan
   full-refresh seluruh histori setiap run. 12 data test (uniqueness,
   not-null, referential integrity) memvalidasi kualitas data di setiap run.
4. **Orchestrate**: Airflow DAG `cloud_elt_dag` menjalankan seluruh alur di atas
   secara terjadwal, dengan retry policy per task, dan aman untuk backfill.
5. **Reverse ETL**: `reverse_etl/` mengambil ringkasan harian dari
   `agg_daily_sales_summary`, dan melakukan batch upsert (endpoint resmi
   Airtable `performUpsert`, hingga 10 record per request, berdasarkan
   `date_key`) ke Airtable, dengan exponential backoff retry pada respons
   429/5xx.
6. **Serve**: Dashboard Streamlit membaca dari marts Snowflake (dengan caching
   `st.cache_data`), menampilkan revenue per kategori, produk terlaris,
   hubungan harga-rating, dan tren revenue harian.

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

### Mengapa Filter Incremental Berdasarkan loaded_at, bukan Business Date

Model incremental dbt (`fact_order_items`, `agg_daily_sales_summary`)
memfilter data baru berdasarkan `loaded_at` (waktu ingestion), bukan
`date_key`/`extraction_date` (tanggal bisnis). Business date tidak aman
dipakai sebagai filter incremental karena backfill bisa memasukkan tanggal
yang LEBIH LAMA dari data yang sudah ada, sementara `loaded_at` selalu
bertambah monoton mengikuti urutan proses load yang sebenarnya, sehingga
filter "lebih baru dari loaded_at terakhir" tetap valid baik untuk run
harian normal maupun backfill.

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

## Reliability & Data Quality

- **Backfill-safe extraction**: seluruh generasi data bersifat deterministik
  terhadap `execution_date`, bukan bergantung state lokal yang incremental.
  Menjalankan ulang tanggal yang sama, kapanpun, akan selalu menghasilkan
  data yang identik.
- **Incremental dbt models**: `fact_order_items` dan `agg_daily_sales_summary`
  hanya memproses data baru di tiap run, sehingga biaya compute Snowflake
  sebanding dengan volume data baru, bukan total histori data.
- **Schema validation di edge**: `extractor/schemas.py` memvalidasi struktur
  response FakeStoreAPI dengan Pydantic sebelum data diproses lebih lanjut.
  Jika API mengubah struktur data secara tidak terduga, proses gagal cepat
  dengan pesan error yang jelas, bukan meloloskan data korup ke tahap
  berikutnya.
- **Resilient reverse ETL**: `push_to_airtable.py` menggunakan batch upsert
  (hingga 10 record per request) dan exponential backoff retry pada respons
  429 (rate limit) atau 5xx (server error), mencegah kegagalan total saat
  volume data membesar atau Airtable mengalami gangguan sementara.

## Known Limitations

- Data bersifat sintetis/simulasi untuk keperluan portfolio, bukan data
  transaksi nyata. Katalog produk statis (20 item dari FakeStoreAPI), order
  digenerate secara sintetis untuk mensimulasikan variasi transaksi harian.
- CI job `test-dbt` melakukan koneksi langsung ke Snowflake pada setiap push
  ke branch `main`. Ini secara sadar dipilih agar CI benar-benar memvalidasi
  pipeline dbt end-to-end, dengan konsekuensi biaya compute Snowflake perlu
  dipantau setelah masa trial berakhir.
- `extractor/venv` menggunakan Python 3.12, bukan versi Python terbaru sistem,
  karena `pydantic-core` (dependency Pydantic) belum mendukung kompilasi pada
  Python 3.14 saat proyek ini dibuat.
