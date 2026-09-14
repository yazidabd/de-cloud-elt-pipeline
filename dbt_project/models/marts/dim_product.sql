select
    product_id,
    title,
    category,
    price,
    rating_rate,
    rating_count
from {{ ref('stg_products') }}
