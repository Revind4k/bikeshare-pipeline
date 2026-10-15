-- The raw files as a relation, so tests can mock it (a file source has no catalog entry).
select * from {{ source('raw', 'trips') }}
