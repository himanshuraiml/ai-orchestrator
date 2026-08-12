.PHONY: up down migrate test shell logs

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run alembic upgrade head

test:
	uv run pytest

shell:
	docker compose exec api /bin/bash

logs:
	docker compose logs -f
