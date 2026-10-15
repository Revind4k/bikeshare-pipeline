# bikeshare-pipeline

How much does weather cut bike-share ridership? An ELT pipeline over a year of Citi Bike trips in Jersey City and Hoboken (972,092 rides, Oct 2025 – Sep 2026) joined to daily weather, built with Python, DuckDB and dbt, with 31 tests that run on every push.

## Results

Each wet day is compared with **dry days in the same month and of the same day type** (weekday or weekend), because season swamps everything else: a rainy July day still beats a dry February one.

| Weather | Days | Weekday change | Weekend change |
|---|---|---|---|
| Light rain (1–10 mm) | 87 | **−6%** | −12% |
| Heavy rain (≥ 10 mm) | 39 | **−29%** | −44% |
| Snow (≥ 1 cm) | 12 | **−53%** | −58% |

- **Commuters keep riding; leisure riders don't.** On heavy-rain weekdays, members drop 27% and casual riders drop 37%. On weekends both fall harder, because most weekend riding is optional.
- **Light rain barely matters on a weekday** (−6%), so a forecast of drizzle isn't a reason to pull bikes off the street.
- **Two cities in one feed.** The "JC" files cover Jersey City (80 docks, 55% of rides) and Hoboken (34 docks, 45%). Another 384 Manhattan docks appear only as destinations: 3,048 rides crossed the Hudson.

`make report` prints these tables from the warehouse.

## Pipeline

```
s3://tripdata (Citi Bike) ──┐
                            ├─ pipeline/extract.py ─→ data/raw/*.csv + manifest.json
Open-Meteo archive API ─────┘     retries, checksums,           (row counts, SHA-256)
                                  skips unchanged months
                                            │
                    DuckDB reads the CSVs in place (dbt-duckdb external sources)
                                            │
 staging     base_trips → stg_trips (typed, one row per ride)     stg_weather
 intermediate             int_trips_classified (duration + one quality verdict per row)
 marts       fct_trips (incremental) · dim_stations · fct_daily_ridership
 reports     rpt_weather_effect · rpt_trip_quality
```

**Extract.** The bucket names files inconsistently (`JC-202510-citibike-tripdata.zip` vs `JC-202509-citibike-tripdata.csv.zip`), so keys are discovered from the bucket listing rather than guessed. Zips ship with macOS `__MACOSX/._*.csv` resource forks, which are skipped. Months split across several CSVs are joined, failing if their headers differ. Every landed file goes into `manifest.json` with its source URL, SHA-256 and row count. A re-run fetches only months that are missing or whose checksum changed; all 12 months land in about 6 seconds.

**Data quality.** Profiling the raw files turned up five problems, and each one has a rule:

| Problem in the raw data | Rows | Handling |
|---|---|---|
| Ride appears in two monthly files (crosses midnight at month end) | 18 | keep the copy from the earlier month |
| Ends before it starts | 7 | excluded |
| Longer than 24 hours (537 of 563 never docked: lost bikes) | 563 | excluded |
| No end station (e-bike left outside a dock) | 5,025 | **kept**: real rides, flagged `ended_at_station = false` |
| Station renamed mid-year (`JC118`: "Pacific Ave & Communipaw Ave" ↔ "Communipaw Ave & Pacific Ave") | 2 stations | latest name wins; `name_variants` records it |

Nothing is silently dropped. `rpt_trip_quality` counts every row by verdict and month, and a reconciliation test proves the books balance: manifest rows = rows read = staged + duplicates = classified.

**Incremental load.** `fct_trips` reprocesses only the newest loaded month onward, with delete+insert on `ride_id`, so late or corrected rows replace their old copies. Loading September onto an August warehouse gives a result identical to a full rebuild: same 971,504 rows and the same checksum over every ride.

## Tests

`dbt build` runs **31 checks** and fails on any of them:

- **Unit tests** (dbt 1.8+) on mocked inputs. One pins each exclusion rule at its boundary (a 60 s ride is kept, a 59 s ride is a false start, 24 h + 1 s is dropped, and an undocked e-bike ride stays valid). The other checks that a month-boundary duplicate keeps its earlier copy.
- **Data tests.** Unique and not-null keys; accepted values for rider, bike, city and weather types; foreign keys from trips to stations; durations inside the allowed range; station coordinates inside the NYC area.
- **Reconciliation.** Every raw row is accounted for, checked against the extract manifest.

`pytest` covers the extract step offline using `httpx.MockTransport`: bucket pagination, both file namings, resource-fork skipping, header mismatches, checksum-based idempotency, retry on 429/5xx, no retry on 4xx, and the weather file. CI runs everything on every push, plus a monthly scheduled run against two live months of data.

## Run it

```bash
uv sync
make extract          # 12 months (~185 MB of CSV) + weather; or START=2026-08 END=2026-09
make build            # dbt models + all tests
make report
make test lint
```

## Limits

- This is observational, not causal. Same-month, same-day-type baselines remove season and weekday effects, but not holidays or events. With only 12 snow days, the snow figure is the least certain.
- Weather is one grid point (Open-Meteo reanalysis near Grove St) for both cities.
- Station IDs carry the city: `JC…` is Jersey City, `HB…` is Hoboken, and numeric IDs are New York. That prefix rule is inferred from the data, not a documented contract.

Data: [Citi Bike system data](https://citibikenyc.com/system-data) (Lyft, used under its data license agreement) and the [Open-Meteo](https://open-meteo.com) historical weather API (CC BY 4.0). Not affiliated with either.
