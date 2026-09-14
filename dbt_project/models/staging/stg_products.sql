-- flatten kolom VARIANT raw_data jadi kolom biasa, dan dedup kalau produk yang sama
-- ke-load lebih dari sekali (ambil versi paling baru berdasarkan loaded_at)
select
    raw_data:record:id::int as product_id,
    raw_data:record:title::string as title,
    raw_data:record:category::string as category,
    raw_data:record:price::float as price,
    raw_data:record:rating:rate::float as rating_rate,
    raw_data:record:rating:count::int as rating_count,
    raw_data:extraction_date::date as extraction_date,
    loaded_at
from {{ source('raw', 'raw_products') }}
qualify row_number() over (partition by raw_data:record:id order by loaded_at desc) = 1
