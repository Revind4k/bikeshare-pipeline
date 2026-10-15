-- Where every raw row went, by month: kept, or excluded and why.
-- Reconciles back to the manifest in tests/assert_rows_reconcile.sql.
select
    source_month,
    quality_flag,
    count(*)                                      as trips,
    count(*) filter (where not ended_at_station)  as undocked
from {{ ref('int_trips_classified') }}
group by all
order by source_month, quality_flag
