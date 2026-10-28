-- Every dry day lands in exactly one temperature band: the band day counts add up to the
-- number of dry days, per day type. Returns a row (= failure) if any day is lost or doubled.
with banded as (
    select is_weekend, sum(days) as banded_days
    from {{ ref('rpt_temperature_effect') }}
    group by 1
),
dry as (
    select is_weekend, count(*) as dry_days
    from {{ ref('fct_daily_ridership') }}
    where weather = 'dry'
    group by 1
)
select *
from dry
full outer join banded using (is_weekend)
where coalesce(dry_days, 0) <> coalesce(banded_days, 0)
