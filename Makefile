.PHONY: dev migrate seed test lint format build

VENV_PY := backend/.venv/Scripts/python.exe

dev:
	docker compose up -d postgres redis
	$(VENV_PY) -m app.bot_polling &
	cd backend && ../$(VENV_PY) -m uvicorn app.main:app --reload --port 8000

migrate:
	cd backend && ../$(VENV_PY) -m alembic upgrade head

migration:
	cd backend && ../$(VENV_PY) -m alembic revision --autogenerate -m "$(m)"

seed:
	cd backend && ../$(VENV_PY) -m app.db.seed

test:
	cd backend && ../$(VENV_PY) -m pytest -v

lint:
	cd backend && ../$(VENV_PY) -m ruff check app tests
	cd backend && ../$(VENV_PY) -m black --check app tests
	cd backend && ../$(VENV_PY) -m mypy app
	cd frontend && npm run typecheck

format:
	cd backend && ../$(VENV_PY) -m ruff check --fix app tests
	cd backend && ../$(VENV_PY) -m black app tests

build:
	docker compose build
