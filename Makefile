.PHONY: install lint test test-postgres test-sqlite upgrade downgrade seed run up down fresh owner cashier backup restore smoke

PY ?= python3

install:
	$(PY) -m pip install -e .[dev]

lint:
	ruff check .

test:
	pytest

test-postgres:
	DATABASE_URL=postgresql+psycopg://shopdesk:shopdesk@localhost:5432/shopdesk_test pytest

test-sqlite:
	DATABASE_URL=sqlite:///./shopdesk.db pytest

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

seed:
	$(PY) scripts/seed.py

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

up:
	docker compose up --build

down:
	docker compose down

fresh:
	docker compose down -v

owner:
	$(PY) scripts/create_owner.py

cashier:
	$(PY) scripts/create_user.py

backup:
	bash scripts/backup.sh

restore:
	bash scripts/restore.sh backups/latest.sql

smoke:
	bash scripts/smoke_test.sh http://127.0.0.1:8000
