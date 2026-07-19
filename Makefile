.DEFAULT_GOAL := help

PYTHON ?= python
PIP ?= pip
PYTEST ?= ./zera-ai-core/bin/pytest -q
UVICORN ?= uvicorn
COMPOSE ?= docker compose

APP_MODULE ?= app.api.main:app
HOST ?= 0.0.0.0
PORT ?= 8000
COVERAGE_MIN ?= 80

.PHONY: help install test test-cov run dev up up-debug down logs restart clean

help:
	@echo "Available targets:"
	@echo "  install    Install project dependencies"
	@echo "  test       Run the test suite"
	@echo "  test-cov   Run tests with coverage"
	@echo "  run        Start the API server"
	@echo "  dev        Start the API server with reload"
	@echo "  up         Start docker-compose services"
	@echo "  up-debug   Start docker-compose services in detached mode for debugging"
	@echo "  down       Stop docker-compose services"
	@echo "  logs       Follow docker-compose logs for mongo"
	@echo "  restart    Restart docker-compose services"
	@echo "  clean      Remove local caches and coverage artifacts"

install:
	$(PIP) install -r requirements.txt

test:
	$(PYTEST)

coverage:
	$(PYTEST) --cov=. --cov-report=xml --cov-fail-under=$(COVERAGE_MIN)

run:
	$(UVICORN) $(APP_MODULE) --host $(HOST) --port $(PORT)

dev:
	$(UVICORN) $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

up:
	$(COMPOSE) up -d

up-debug:
	$(COMPOSE) up -d --remove-orphans

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f mongo

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

clean:
	@powershell -NoProfile -Command "Get-ChildItem -Recurse -Force -Directory __pycache__,.pytest_cache,htmlcov | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; Get-ChildItem -Force coverage.xml,.coverage,.coverage.* -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue"
