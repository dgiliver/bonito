# Makefile for Bonito development
# Usage: make <target>

# Auto-detect venv python, fall back to system python
VENV_DIR := $(shell cd "$(CURDIR)" && while [ "$$PWD" != "/" ]; do [ -f "$$PWD/.venv/bin/python" ] && echo "$$PWD/.venv" && break; cd ..; done)
PYTHON := $(if $(VENV_DIR),$(VENV_DIR)/bin/python,python)
export PYTHONPATH := $(CURDIR)/src:$(PYTHONPATH)

.PHONY: help install install-dev test lint format typecheck pre-commit clean api web docker-build docker-up docker-down

# Default target
help:
	@echo "Available targets:"
	@echo "  install      - Install production dependencies"
	@echo "  install-dev  - Install development dependencies"
	@echo "  test         - Run tests"
	@echo "  test-fast    - Run tests (skip slow tests)"
	@echo "  test-cov     - Run tests with coverage"
	@echo "  lint         - Run linter (ruff)"
	@echo "  format       - Format code (ruff)"
	@echo "  typecheck    - Run type checker (mypy)"
	@echo "  pre-commit   - Run all pre-commit hooks"
	@echo "  clean        - Remove build artifacts"
	@echo "  setup        - Complete dev environment setup"
	@echo "  api          - Run the API server (port 8000)"
	@echo "  web          - Run the frontend (port 3000)"
	@echo "  chat         - Start CLI chat with agent"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-up    - Start containers"
	@echo "  docker-down  - Stop containers"
	@echo "  docker-logs  - View container logs"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test:
	pytest tests/ -v

test-fast:
	pytest tests/ -v -m "not slow"

test-cov:
	pytest tests/ --cov=bonito --cov-report=html --cov-report=term-missing

test-all:
	pytest tests/ -v --run-slow

# Code quality
lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

typecheck:
	mypy src/

# Pre-commit
pre-commit:
	pre-commit run --all-files

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Complete setup
setup: install-dev
	@echo "✓ Development environment ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Run 'make test-fast' to verify setup"
	@echo "  2. Run 'make pre-commit' to check code quality"

# API Server
api:
	uvicorn bonito.api.main:app --reload --host 0.0.0.0 --port 8000

# Live-trading dashboard (standalone, read-only)
dashboard:
	uvicorn bonito.dashboard.app:app --host 0.0.0.0 --port 8050

# CLI Chat
chat:
	$(PYTHON) -m bonito.cli chat -v

# Frontend
web:
	cd web && npm run dev

web-build:
	cd web && npm run build

# Docker
docker-build:
	docker build -t bonito .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f api

# Research
research:
	$(PYTHON) -m bonito.cli research run --symbol SPY --iterations 1000

ingest-universe:
	$(PYTHON) -m bonito.cli ingest SPY QQQ IWM AAPL MSFT GOOGL TSLA NFLX NVDA AMD MU PLTR --start 2020-01-01 --end 2025-03-20

# Live trading (Robinhood universe — see config/universe.json)
live-run:
	$(PYTHON) -m bonito.cli live run

live-status:
	$(PYTHON) -m bonito.cli live status

live-performance:
	$(PYTHON) -m bonito.cli live performance

live-sweep:
	$(PYTHON) -m bonito.cli live sweep --execute

live-backtest:
	$(PYTHON) -m bonito.cli live backtest-universe

live-backtest-account:
	$(PYTHON) -m bonito.cli live backtest-account
