-- How much does weather cut ridership? Season and weekday/weekend are the big confounders
-- (a rainy July day still beats a dry February one), so each wet day is compared with dry
-- days of the same month and the same day type, then the ratios are averaged.
with days as (
    select * from {{ ref('fct_daily_ridership') }}
),

dry_baseline as (
    select month, is_weekend,
           avg(rides)        as dry_rides,
           avg(member_rides) as dry_member,
           avg(casual_rides) as dry_casual,
           count(*)          as dry_days
    from days
    where weather = 'dry'
    group by all
)

select
    d.weather,
    d.is_weekend,
    count(*)                                                        as days,
    round(avg(d.rides / b.dry_rides - 1) * 100, 1)                  as pct_change_all,
    round(avg(d.member_rides / b.dry_member - 1) * 100, 1)          as pct_change_member,
    round(avg(d.casual_rides / nullif(b.dry_casual, 0) - 1) * 100, 1) as pct_change_casual
from days d
join dry_baseline b using (month, is_weekend)
where d.weather <> 'dry' and b.dry_days >= 3   -- need a real baseline
group by all
order by d.is_weekend, d.weather
