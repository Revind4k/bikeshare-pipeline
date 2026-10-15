-- One row per day, every day in the weather calendar (a day with no rides still appears).
with rides as (
    select
        ride_date,
        count(*)                                              as rides,
        count(*) filter (where rider_type = 'member')         as member_rides,
        count(*) filter (where rider_type = 'casual')         as casual_rides,
        count(*) filter (where rideable_type = 'electric_bike') as ebike_rides,
        median(duration_s) / 60.0                             as median_minutes
    from {{ ref('fct_trips') }}
    group by ride_date
)

select
    w.weather_date                                   as ride_date,
    coalesce(r.rides, 0)                             as rides,
    coalesce(r.member_rides, 0)                      as member_rides,
    coalesce(r.casual_rides, 0)                      as casual_rides,
    round(coalesce(r.ebike_rides, 0) / nullif(r.rides, 0), 3) as ebike_share,
    round(r.median_minutes, 1)                       as median_minutes,
    w.temp_max_c,
    w.precip_mm,
    w.snowfall_cm,
    case
        when w.snowfall_cm >= {{ var('snow_cm') }}                       then 'snow'
        when w.precip_mm >= {{ var('heavy_rain_mm') }} then 'heavy_rain'
        when w.precip_mm >= {{ var('light_rain_mm') }} then 'light_rain'
        else 'dry'
    end                                              as weather,
    dayofweek(w.weather_date) in (0, 6)              as is_weekend,
    strftime(w.weather_date, '%Y-%m')                as month
from {{ ref('stg_weather') }} w
left join rides r on r.ride_date = w.weather_date
