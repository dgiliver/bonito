# Makefile for quant-agent development
# Usage: make <target>

.PHONY: help install install-dev test lint format typecheck pre-commit clean

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
	pytest tests/ --cov=quant_agent --cov-report=html --cov-report=term-missing

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

