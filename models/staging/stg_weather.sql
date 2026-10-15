select
    cast(date as date)                   as weather_date,
    cast(temperature_2m_max as double)   as temp_max_c,
    cast(temperature_2m_min as double)   as temp_min_c,
    cast(precipitation_sum as double)    as precip_mm,
    cast(snowfall_sum as double)         as snowfall_cm,
    cast(wind_speed_10m_max as double)   as wind_max_kmh
from {{ source('raw', 'weather') }}
