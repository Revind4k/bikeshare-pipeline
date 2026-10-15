-- One row per ride_id, typed. Rides that cross a month boundary appear in both monthly
-- files; the copy from the earlier file is kept.
with typed as (
    select
        ride_id,
        rideable_type,
        member_casual                                as rider_type,
        try_cast(started_at as timestamp)            as started_at,
        try_cast(ended_at as timestamp)              as ended_at,
        nullif(trim(start_station_id), '')           as start_station_id,
        nullif(trim(start_station_name), '')         as start_station_name,
        nullif(trim(end_station_id), '')             as end_station_id,
        nullif(trim(end_station_name), '')           as end_station_name,
        try_cast(nullif(start_lat, '') as double)    as start_lat,
        try_cast(nullif(start_lng, '') as double)    as start_lng,
        try_cast(nullif(end_lat, '') as double)      as end_lat,
        try_cast(nullif(end_lng, '') as double)      as end_lng,
        regexp_extract(filename, '(\d{6})\.csv$', 1) as source_month
    from {{ ref('base_trips') }}
)

select * exclude (rn)
from (
    select *, row_number() over (partition by ride_id order by source_month, started_at) as rn
    from typed
)
where rn = 1
