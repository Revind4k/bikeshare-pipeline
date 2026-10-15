"""Extract: download Citi Bike Jersey City trip files and daily weather into data/raw/.

Idempotent: a month already extracted (and matching its recorded checksum) is skipped,
so re-running only fetches what's new. Every file landed is recorded in
data/raw/manifest.json with its source URL, SHA-256 and row count, which is what the
dbt source tests compare against.

    uv run python -m pipeline.extract --start 2025-10 --end 2026-09
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import re
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import httpx

BUCKET = "https://s3.amazonaws.com/tripdata"
WEATHER_API = "https://archive-api.open-meteo.com/v1/archive"
# Jersey City (Grove St). Open-Meteo snaps to its nearest grid cell.
LAT, LON = 40.7196, -74.0431
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


@dataclass
class Landed:
    path: str
    source: str
    sha256: str
    rows: int


def http_get(client: httpx.Client, url: str, *, params: dict | None = None, attempts: int = 4) -> httpx.Response:
    """GET with retries on network errors, 429 and 5xx (exponential backoff)."""
    for i in range(attempts):
        try:
            r = client.get(url, params=params)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r
            err: Exception = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
        except httpx.TransportError as e:
            err = e
        if i == attempts - 1:
            raise err
        time.sleep(2**i)
    raise AssertionError("unreachable")


def months(start: str, end: str) -> list[str]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def list_bucket(client: httpx.Client, prefix: str) -> list[str]:
    """Object keys under prefix. The bucket names files inconsistently
    (JC-202510-citibike-tripdata.zip vs JC-202509-citibike-tripdata.csv.zip),
    so keys are discovered rather than guessed."""
    keys, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        xml = http_get(client, BUCKET, params=params).text
        keys += re.findall(r"<Key>([^<]+)</Key>", xml)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", xml)
        if not m:
            return keys
        token = m.group(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_trips(client: httpx.Client, yyyymm: str, keys: list[str], manifest: dict[str, Landed]) -> Landed | None:
    out = RAW / "trips" / f"{yyyymm}.csv"
    if out.exists() and str(out.relative_to(RAW)) in manifest and manifest[str(out.relative_to(RAW))].sha256 == sha256(out):
        return None  # already landed and unchanged
    key = next((k for k in keys if k.startswith(f"JC-{yyyymm}-") and k.endswith(".zip")), None)
    if key is None:
        raise SystemExit(f"no Jersey City trip file for {yyyymm} in the bucket")
    blob = http_get(client, f"{BUCKET}/{key}").content
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        # Skip macOS resource forks (__MACOSX/._name.csv) that ship inside the archives.
        members = [n for n in zf.namelist() if n.endswith(".csv") and "__MACOSX" not in n and not Path(n).name.startswith("._")]
        if not members:
            raise SystemExit(f"{key}: no CSV inside")
        out.parent.mkdir(parents=True, exist_ok=True)
        rows, header = 0, None
        with out.open("w", newline="") as dst:
            for name in sorted(members):  # some months split across several CSVs
                with zf.open(name) as src:
                    reader = csv.reader(io.TextIOWrapper(src, encoding="utf-8-sig"))
                    h = next(reader)
                    if header is None:
                        header = h
                        writer = csv.writer(dst)
                        writer.writerow(h)
                    elif h != header:
                        raise SystemExit(f"{key}/{name}: header differs from the month's first file")
                    for row in reader:
                        writer.writerow(row)
                        rows += 1
    return Landed(str(out.relative_to(RAW)), f"{BUCKET}/{key}", sha256(out), rows)


def extract_weather(client: httpx.Client, first: str, last: str) -> Landed:
    start = date(int(first[:4]), int(first[4:]), 1)
    ly, lm = int(last[:4]), int(last[4:])
    end = date(ly, lm, calendar.monthrange(ly, lm)[1])
    daily = "temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,wind_speed_10m_max"
    r = http_get(client, WEATHER_API, params={
        "latitude": LAT, "longitude": LON, "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": daily, "timezone": "America/New_York",
    })
    d = r.json()["daily"]
    out = RAW / "weather" / "daily.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date"] + daily.split(",")
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, day in enumerate(d["time"]):
            w.writerow([day] + [d[c][i] for c in cols[1:]])
    return Landed(str(out.relative_to(RAW)), str(r.url), sha256(out), len(d["time"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2025-10")
    ap.add_argument("--end", default="2026-09")
    a = ap.parse_args()

    mpath = RAW / "manifest.json"
    manifest = {k: Landed(**v) for k, v in json.loads(mpath.read_text()).items()} if mpath.exists() else {}
    wanted = months(a.start, a.end)
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "bikeshare-pipeline (github.com/Revind4k)"}) as client:
        keys = list_bucket(client, "JC-")
        for m in wanted:
            landed = extract_trips(client, m, keys, manifest)
            if landed:
                manifest[landed.path] = landed
                print(f"trips {m}: {landed.rows:,} rows")
            else:
                print(f"trips {m}: unchanged, skipped")
        w = extract_weather(client, wanted[0], wanted[-1])
        manifest[w.path] = w
        print(f"weather: {w.rows} days")
    RAW.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps({k: asdict(v) for k, v in sorted(manifest.items())}, indent=2) + "\n")


if __name__ == "__main__":
    main()
