{{
    config(
        materialized='incremental',
        unique_key='date_key',
        incremental_strategy='merge'
    )
}}

-- ringkasan harian, dikirim ke Airtable lewat reverse ETL
-- hanya me-recompute date_key yang punya fact row baru (bukan seluruh histori),
-- sehingga biaya compute sebanding dengan volume data baru, bukan total data
select
    date_key,
    count(distinct order_id) as total_orders,
    sum(quantity) as total_quantity,
    round(sum(line_total), 2) as total_revenue,
    round(sum(line_discounted_total), 2) as total_discounted_revenue,
    max(loaded_at) as loaded_at
from {{ ref('fact_order_items') }}
{% if is_incremental() %}
where date_key in (
    select distinct date_key
    from {{ ref('fact_order_items') }}
    where loaded_at > (select coalesce(max(loaded_at), '1900-01-01'::timestamp_ntz) from {{ this }})
)
{% endif %}
group by date_key
