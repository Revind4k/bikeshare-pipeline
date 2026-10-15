-- Every staged trip with its duration and a single quality verdict. Nothing is dropped
-- here, so the quality report can account for every row.
with t as (
    select *, date_diff('second', started_at, ended_at) as duration_s
    from {{ ref('stg_trips') }}
)

select
    *,
    case
        when started_at is null or ended_at is null                    then 'unparseable_timestamp'
        when duration_s <= 0                                           then 'ends_before_start'
        when duration_s < {{ var('min_trip_seconds') }}                then 'false_start'
        when duration_s > {{ var('max_trip_hours') }} * 3600           then 'over_max_duration'
        else 'valid'
    end as quality_flag,
    -- E-bikes can be left outside a dock; those are real rides, just not station-to-station.
    end_station_id is not null as ended_at_station
from t
