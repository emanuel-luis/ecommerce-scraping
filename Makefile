.PHONY: help install lint format test test-fast demo up down docker-build clean

help:           ## list the targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install:        ## sync the environment from uv.lock
	uv sync --locked

lint:           ## what CI's lint job runs
	uv run ruff check
	uv run ruff format --check
	uv run mypy

format:         ## apply ruff fixes and formatting
	uv run ruff check --fix
	uv run ruff format

test:           ## offline tests with the 85 % coverage gate
	uv run pytest --cov=ecommerce_scraping --cov-fail-under=85

test-fast:      ## offline tests without coverage
	uv run pytest -q

demo:           ## small live run (5 products per store), then the table counts
	uv run ecommerce-scraping run --limit 5
	uv run ecommerce-scraping stats

up:             ## build and start the stack
	docker compose up --build

down:           ## stop the stack
	docker compose down

docker-build:   ## build the image
	docker build -t ecommerce-scraping .

clean:          ## remove caches and build output
	rm -rf .venv .mypy_cache .pytest_cache .ruff_cache .hypothesis .coverage htmlcov dist
