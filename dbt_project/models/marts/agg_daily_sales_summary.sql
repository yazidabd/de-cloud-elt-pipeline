-- ringkasan harian, ini yang nanti dikirim ke Airtable lewat reverse ETL
-- bukan data mentah per item, karena tujuannya buat dibaca orang non-teknis
select
    date_key,
    count(distinct order_id) as total_orders,
    sum(quantity) as total_quantity,
    round(sum(line_total), 2) as total_revenue,
    round(sum(line_discounted_total), 2) as total_discounted_revenue
from {{ ref('fact_order_items') }}
group by date_key
