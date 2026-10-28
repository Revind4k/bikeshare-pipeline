-- How does temperature relate to ridership? Rain and snow would muddy this (wet days are
-- also cooler on average), so only dry days count. Days are grouped into 5 °C bands of the
-- daily high and split by day type, since weekday commuting and weekend leisure respond
-- differently.
with dry_days as (
    select
        *,
        case
            when temp_max_c < 0  then 0
            when temp_max_c >= {{ var('temp_band_top_c') }} then {{ var('temp_band_top_c') // 5 + 1 }}
            else floor(temp_max_c / 5)::int + 1
        end as band_order
    from {{ ref('fct_daily_ridership') }}
    where weather = 'dry'
)

select
    band_order,
    case
        when band_order = 0 then '< 0 °C'
        when band_order = {{ var('temp_band_top_c') // 5 + 1 }} then '≥ {{ var("temp_band_top_c") }} °C'
        else ((band_order - 1) * 5)::varchar || '–' || (band_order * 5)::varchar || ' °C'
    end                                                        as temp_band,
    is_weekend,
    count(*)                                                   as days,
    round(avg(rides))                                          as avg_rides,
    round(avg(member_rides))                                   as avg_member,
    round(avg(casual_rides))                                   as avg_casual,
    round(sum(casual_rides) / nullif(sum(rides), 0) * 100, 1)  as casual_pct
from dry_days
group by all
order by is_weekend, band_order
