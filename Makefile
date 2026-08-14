.PHONY: help up down logs build clean test lint format migrate seed

help:
	@echo "Available commands:"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
	@echo "  make logs        - Show logs"
	@echo "  make build       - Rebuild containers"
	@echo "  make clean       - Remove containers and volumes"
	@echo "  make test        - Run backend tests"
	@echo "  make lint        - Run linters (ruff, mypy)"
	@echo "  make format      - Format code (ruff)"
	@echo "  make migrate     - Run database migrations"
	@echo "  make seed        - Seed demo data"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

clean:
	docker compose down -v

test:
	docker compose exec backend pytest

lint:
	docker compose exec backend ruff check .
	docker compose exec backend mypy .

format:
	docker compose exec backend ruff format .

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python -c "import asyncio; from app.seeds import seed_demo_data; asyncio.run(seed_demo_data())"
