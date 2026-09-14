-- date spine 2 tahun (2025-2026) cukup buat cakupan portfolio ini,
-- dibikin generate otomatis bukan hardcode list tanggal manual
with spine as (
    {{
        dbt_utils.date_spine(
            datepart="day",
            start_date="cast('2025-01-01' as date)",
            end_date="cast('2027-01-01' as date)"
        )
    }}
)

select
    date_day as date_key,
    year(date_day) as year,
    month(date_day) as month,
    day(date_day) as day,
    dayname(date_day) as day_name,
    dayofweek(date_day) as day_of_week
from spine
