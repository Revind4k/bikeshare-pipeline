"""Print the headline tables from the warehouse: weather effect, data quality, cities."""

import os

import duckdb

con = duckdb.connect(os.environ.get("BIKESHARE_DB", "data/warehouse.duckdb"), read_only=True)
for title, sql in [
    ("Ridership vs. dry days of the same month and day type", "select * from rpt_weather_effect"),
    ("Where every raw row went", "select quality_flag, sum(trips) as trips, sum(undocked) as undocked from rpt_trip_quality group by 1 order by 2 desc"),
    ("Rides by starting city", "select s.city, count(*) as rides, round(100.0 * count(*) / sum(count(*)) over (), 1) as pct from fct_trips t join dim_stations s on s.station_id = t.start_station_id group by 1 order by 2 desc"),
]:
    print(f"\n{title}")
    print(con.sql(sql))
