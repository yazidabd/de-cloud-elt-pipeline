-- level cart/order, belum termasuk detail produk di dalamnya (itu ada di stg_order_items)
select
    raw_data:record:id::int as order_id,
    raw_data:record:userId::int as user_id,
    raw_data:record:total::float as order_total,
    raw_data:record:discountedTotal::float as order_discounted_total,
    raw_data:record:totalProducts::int as total_products,
    raw_data:record:totalQuantity::int as total_quantity,
    raw_data:extraction_date::date as extraction_date,
    loaded_at
from {{ source('raw', 'raw_orders') }}
qualify row_number() over (partition by raw_data:record:id order by loaded_at desc) = 1
