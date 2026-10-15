START ?= 2025-10
END   ?= 2026-09
export DBT_PROFILES_DIR := .

.PHONY: all extract build test lint report clean

all: extract build report

extract:            ## download trips + weather into data/raw (skips unchanged months)
	uv run python -m pipeline.extract --start $(START) --end $(END)

build:              ## models + data tests + unit tests
	uv run dbt build

test:               ## extract-step tests (offline)
	uv run pytest -q

lint:
	uv run ruff check pipeline tests_py

report:             ## print the headline tables
	uv run python -m pipeline.report

clean:
	rm -rf target data/warehouse.duckdb
