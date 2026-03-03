.PHONY: help install dev up down logs test lint format clean build deploy worker migrate

help:
	@echo "Nexus Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install    - Install dependencies"
	@echo "  make dev        - Start development server"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linters"
	@echo "  make format     - Format code"
	@echo ""
	@echo "Docker:"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View logs"
	@echo "  make shell      - Open shell in API container"
	@echo ""
	@echo "Database:"
	@echo "  make migrate    - Run database migrations"
	@echo "  make migrate-new - Create new migration"
	@echo ""
	@echo "Background Jobs:"
	@echo "  make worker     - Start background worker"
	@echo ""
	@echo "Production:"
	@echo "  make build      - Build Docker images"
	@echo "  make deploy     - Deploy to Kubernetes"

# === Development ===

install:
	cd core && pip install -e ".[dev]"

dev:
	cd core && uvicorn nexus.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd core && pytest tests/ -v --cov=nexus --cov-report=term-missing

test-fast:
	cd core && pytest tests/ -v -x --tb=short

lint:
	cd core && ruff check nexus/ tests/
	cd core && ruff format --check nexus/ tests/

format:
	cd core && ruff format nexus/ tests/
	cd core && ruff check --fix nexus/ tests/

# === Docker ===

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

logs-api:
	docker-compose logs -f api

shell:
	docker-compose exec api bash

# === Database ===

migrate:
	cd core && alembic upgrade head

migrate-new:
	@read -p "Migration message: " msg; \
	cd core && alembic revision --autogenerate -m "$$msg"

migrate-down:
	cd core && alembic downgrade -1

# === Background Jobs ===

worker:
	cd core && python -m nexus.jobs.worker

# === Production ===

build:
	docker build -t nexus/api:latest ./core
	docker build -t nexus/worker:latest -f ./core/Dockerfile.worker ./core

deploy:
	cd deploy/kubernetes && kubectl apply -k .

deploy-status:
	kubectl get pods -n nexus
	kubectl get svc -n nexus

# === Utilities ===

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true

health:
	@curl -s http://localhost:8000/health | python -m json.tool

metrics:
	@curl -s http://localhost:8000/metrics
