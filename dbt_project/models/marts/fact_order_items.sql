{{
    config(
        materialized='incremental',
        unique_key='order_item_key',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns'
    )
}}

-- grain: satu baris per item produk per order
-- order_item_key adalah surrogate key (order_id + product_id): aman karena
-- satu order tidak pernah punya produk duplikat (random.sample menjamin
-- produk unik per order di extract_orders.py)
--
-- filter incremental menggunakan loaded_at (waktu ingestion), BUKAN date_key
-- (tanggal bisnis). Ini penting untuk backfill: date_key hasil backfill bisa
-- lebih lama dari date_key yang sudah ada (misal backfill 5 hari ke belakang),
-- tapi loaded_at selalu bertambah monoton mengikuti kapan data benar-benar
-- di-load, sehingga filter "lebih baru dari loaded_at terakhir" tetap valid
-- untuk kasus backfill maupun run harian normal
select
    oi.order_id || '_' || oi.product_id as order_item_key,
    oi.order_id,
    oi.product_id,
    oi.extraction_date as date_key,
    oi.quantity,
    oi.unit_price,
    oi.line_total,
    oi.discount_percentage,
    oi.line_discounted_total,
    oi.loaded_at
from {{ ref('stg_order_items') }} oi
{% if is_incremental() %}
where oi.loaded_at > (select coalesce(max(loaded_at), '1900-01-01'::timestamp_ntz) from {{ this }})
{% endif %}
