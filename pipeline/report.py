"""Print the headline tables from the warehouse: weather and temperature effects, data quality, cities."""

import os

import duckdb

con = duckdb.connect(os.environ.get("BIKESHARE_DB", "data/warehouse.duckdb"), read_only=True)
for title, sql in [
    ("Ridership vs. dry days of the same month and day type", "select * from rpt_weather_effect"),
    ("Dry-day ridership by daily high", "select temp_band, is_weekend, days, avg_rides, avg_member, avg_casual, casual_pct from rpt_temperature_effect order by is_weekend, band_order"),
    ("Where every raw row went", "select quality_flag, sum(trips) as trips, sum(undocked) as undocked from rpt_trip_quality group by 1 order by 2 desc"),
    ("Rides by starting city", "select s.city, count(*) as rides, round(100.0 * count(*) / sum(count(*)) over (), 1) as pct from fct_trips t join dim_stations s on s.station_id = t.start_station_id group by 1 order by 2 desc"),
]:
    print(f"\n{title}")
    print(con.sql(sql))
