-- grain: satu baris per item produk per order
-- extraction_date dipakai sebagai foreign key ke dim_date
select
    oi.order_id,
    oi.product_id,
    oi.extraction_date as date_key,
    oi.quantity,
    oi.unit_price,
    oi.line_total,
    oi.discount_percentage,
    oi.line_discounted_total
from {{ ref('stg_order_items') }} oi
