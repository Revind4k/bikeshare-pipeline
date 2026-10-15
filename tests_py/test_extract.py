"""Extract-step tests. HTTP is served by httpx.MockTransport, so these run offline."""

import io
import json
import zipfile

import httpx
import pytest

from pipeline import extract

HEADER = "ride_id,rideable_type,started_at,ended_at\n"


def zip_of(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return buf.getvalue()


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "RAW", tmp_path)
    monkeypatch.setattr(extract.time, "sleep", lambda s: None)
    return tmp_path


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_months_spans_year_boundary():
    assert extract.months("2025-11", "2026-02") == ["202511", "202512", "202601", "202602"]


def test_list_bucket_follows_continuation_tokens():
    pages = {
        None: "<Key>JC-202510-citibike-tripdata.zip</Key><NextContinuationToken>t2</NextContinuationToken>",
        "t2": "<Key>JC-202511-citibike-tripdata.csv.zip</Key>",
    }

    def handler(req):
        return httpx.Response(200, text=pages[req.url.params.get("continuation-token")])

    assert extract.list_bucket(client(handler), "JC-") == [
        "JC-202510-citibike-tripdata.zip",
        "JC-202511-citibike-tripdata.csv.zip",
    ]


def test_extract_skips_macos_resource_forks_and_joins_split_files(raw):
    blob = zip_of({
        "JC-202609-a.csv": HEADER + "r1,classic_bike,2026-09-01 08:00,2026-09-01 08:10\n",
        "JC-202609-b.csv": HEADER + "r2,electric_bike,2026-09-02 08:00,2026-09-02 08:10\n",
        "__MACOSX/._JC-202609-a.csv": "\x00\x05binary junk",
    })
    c = client(lambda req: httpx.Response(200, content=blob))
    landed = extract.extract_trips(c, "202609", ["JC-202609-citibike-tripdata.csv.zip"], {})
    assert landed.rows == 2
    lines = (raw / "trips" / "202609.csv").read_text().splitlines()
    assert lines[0] == HEADER.strip() and len(lines) == 3


def test_extract_finds_either_file_naming(raw):
    blob = zip_of({"x.csv": HEADER + "r1,classic_bike,a,b\n"})
    c = client(lambda req: httpx.Response(200, content=blob) if req.url.path.endswith("JC-202510-citibike-tripdata.zip") else httpx.Response(404))
    keys = ["JC-202509-citibike-tripdata.csv.zip", "JC-202510-citibike-tripdata.zip"]
    assert extract.extract_trips(c, "202510", keys, {}).source.endswith("JC-202510-citibike-tripdata.zip")


def test_extract_rejects_mismatched_headers(raw):
    blob = zip_of({"a.csv": HEADER + "r1,x,y,z\n", "b.csv": "ride_id,started_at\nr2,y\n"})
    c = client(lambda req: httpx.Response(200, content=blob))
    with pytest.raises(SystemExit, match="header differs"):
        extract.extract_trips(c, "202609", ["JC-202609-citibike-tripdata.zip"], {})


def test_extract_is_idempotent(raw):
    calls = []
    blob = zip_of({"a.csv": HEADER + "r1,classic_bike,a,b\n"})

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, content=blob)

    keys = ["JC-202609-citibike-tripdata.zip"]
    first = extract.extract_trips(client(handler), "202609", keys, {})
    manifest = {first.path: first}
    assert extract.extract_trips(client(handler), "202609", keys, manifest) is None
    assert len(calls) == 1
    # A file edited on disk no longer matches its checksum and is fetched again.
    (raw / first.path).write_text("tampered\n")
    assert extract.extract_trips(client(handler), "202609", keys, manifest) is not None
    assert len(calls) == 2


def test_missing_month_fails_loudly(raw):
    with pytest.raises(SystemExit, match="no Jersey City trip file for 202701"):
        extract.extract_trips(client(lambda r: httpx.Response(500)), "202701", ["JC-202609-x.zip"], {})


def test_retries_transient_errors_then_succeeds(monkeypatch):
    monkeypatch.setattr(extract.time, "sleep", lambda s: None)
    responses = iter([httpx.Response(503), httpx.Response(429), httpx.Response(200, text="ok")])
    assert extract.http_get(client(lambda r: next(responses)), "https://x").text == "ok"


def test_does_not_retry_client_errors():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(403)

    with pytest.raises(httpx.HTTPStatusError):
        extract.http_get(client(handler), "https://x")
    assert len(calls) == 1


def test_weather_writes_one_row_per_day(raw):
    days = ["2026-09-01", "2026-09-02"]
    payload = {"daily": {"time": days, **{k: [1.0, 2.0] for k in [
        "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "snowfall_sum", "wind_speed_10m_max"]}}}
    landed = extract.extract_weather(client(lambda r: httpx.Response(200, json=payload)), "202609", "202609")
    assert landed.rows == 2
    assert (raw / "weather" / "daily.csv").read_text().splitlines()[1].startswith("2026-09-01,1.0")


def test_manifest_round_trips(raw):
    landed = extract.Landed("trips/202609.csv", "s3://x", "abc", 3)
    (raw / "manifest.json").write_text(json.dumps({landed.path: landed.__dict__}))
    loaded = {k: extract.Landed(**v) for k, v in json.loads((raw / "manifest.json").read_text()).items()}
    assert loaded[landed.path] == landed
