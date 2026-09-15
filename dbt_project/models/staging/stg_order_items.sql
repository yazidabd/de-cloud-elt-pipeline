-- setiap order punya array produk bersarang, LATERAL FLATTEN memecahnya
-- jadi satu baris per item produk per order, ini yang jadi calon fact table nanti
-- loaded_at diteruskan dari raw table, dipakai fact_order_items sebagai
-- basis filter incremental (waktu ingestion, bukan tanggal bisnis)
select
    raw_data:record:id::int as order_id,
    item.value:id::int as product_id,
    item.value:quantity::int as quantity,
    item.value:price::float as unit_price,
    item.value:total::float as line_total,
    item.value:discountPercentage::float as discount_percentage,
    item.value:discountedTotal::float as line_discounted_total,
    raw_data:extraction_date::date as extraction_date,
    loaded_at
from {{ source('raw', 'raw_orders') }},
lateral flatten(input => raw_data:record:products) item
