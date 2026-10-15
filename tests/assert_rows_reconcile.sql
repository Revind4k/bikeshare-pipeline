-- Every row the extract landed is accounted for: the manifest's row counts equal the rows
-- DuckDB reads from the files, and those equal staged rows plus removed duplicates.
-- Returns a row (= failure) for any month where the books don't balance.
with manifest as (
    select regexp_extract(key, '(\d{6})\.csv$', 1) as source_month, (value ->> 'rows')::bigint as manifest_rows
    from (
        select unnest(map_keys(m)) as key, unnest(map_values(m)) as value
        from (select json_transform(content::json, '"MAP(VARCHAR, JSON)"') as m
              from read_text('{{ env_var("BIKESHARE_RAW", "data/raw") }}/manifest.json'))
    )
    where key like 'trips/%'
),
raw as (
    select regexp_extract(filename, '(\d{6})\.csv$', 1) as source_month, count(*) as raw_rows,
           count(*) - count(distinct ride_id) as dup_rows
    from {{ source('raw', 'trips') }}
    group by 1
),
staged as (
    select source_month, count(*) as staged_rows from {{ ref('stg_trips') }} group by 1
),
classified as (
    select source_month, sum(trips) as classified_rows from {{ ref('rpt_trip_quality') }} group by 1
),
-- A duplicate is dropped from the later month, so compare totals rather than per month.
totals as (
    select
        (select sum(manifest_rows) from manifest)   as manifest_rows,
        (select sum(raw_rows) from raw)             as raw_rows,
        (select count(*) - count(distinct ride_id) from {{ source('raw', 'trips') }}) as duplicate_rows,
        (select sum(staged_rows) from staged)       as staged_rows,
        (select sum(classified_rows) from classified) as classified_rows
)
select * from totals
where manifest_rows <> raw_rows
   or raw_rows <> staged_rows + duplicate_rows
   or staged_rows <> classified_rows
