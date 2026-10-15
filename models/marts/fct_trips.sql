{{
  config(
    materialized = 'incremental',
    unique_key = 'ride_id',
    incremental_strategy = 'delete+insert',
    on_schema_change = 'fail'
  )
}}
-- Valid rides only (see int_trips_classified for what's excluded and why).
-- Incremental: a run only processes months at or after the newest month already loaded,
-- reprocessing that month in full so late-arriving rows replace their earlier copies.
select
    ride_id,
    rideable_type,
    rider_type,
    started_at,
    ended_at,
    started_at::date                     as ride_date,
    duration_s,
    start_station_id,
    end_station_id,
    ended_at_station,
    start_station_id = end_station_id    as round_trip,
    source_month
from {{ ref('int_trips_classified') }}
where quality_flag = 'valid'
{% if is_incremental() %}
  and source_month >= (select max(source_month) from {{ this }})
{% endif %}
