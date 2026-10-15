-- One row per station ID. Stations get renamed (JC118 is both "Pacific Ave & Communipaw
-- Ave" and "Communipaw Ave & Pacific Ave"), so the name is the most recently seen one.
with sightings as (
    select start_station_id as station_id, start_station_name as station_name, start_lat as lat, start_lng as lng, started_at as seen_at, 1 as started
    from {{ ref('int_trips_classified') }}
    where start_station_id is not null and quality_flag = 'valid'
    union all
    select end_station_id, end_station_name, end_lat, end_lng, ended_at, 0
    from {{ ref('int_trips_classified') }}
    where end_station_id is not null and quality_flag = 'valid'
)

select
    station_id,
    arg_max(station_name, seen_at)              as station_name,
    count(distinct station_name)                as name_variants,
    -- E-bike GPS jitters per ride; the median is a stable dock location.
    median(lat)                                 as lat,
    median(lng)                                 as lng,
    -- The "JC" feed is the Jersey City + Hoboken system. Numeric IDs are Manhattan docks,
    -- which appear only as destinations of rides that crossed the Hudson.
    case
        when station_id like 'JC%' then 'Jersey City'
        when station_id like 'HB%' then 'Hoboken'
        else 'New York'
    end                                         as city,
    sum(started)                                as trips_started,
    count(*) - sum(started)                     as trips_ended,
    min(seen_at)::date                          as first_seen,
    max(seen_at)::date                          as last_seen
from sightings
group by station_id
