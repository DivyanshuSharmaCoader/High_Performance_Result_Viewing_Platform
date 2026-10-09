# ScoreCode developer commands. CI runs the same targets (.github/workflows/ci.yml).
SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
COMPOSE := docker compose

.PHONY: help up down stack logs migrate seed api worker web lint typecheck test test-unit test-int \
        test-frontend e2e openapi fmt build clean platform-user

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Start infrastructure (postgres, redis, s3, mailpit)
	$(COMPOSE) up -d --build postgres redis s3 mailpit
	@echo "Postgres :55432 · Redis :56379 · S3 :59000 · Mailpit http://localhost:58025"

stack: ## Run the whole product in containers → http://thapar.localhost:8080 (after `make seed-stack`)
	$(COMPOSE) --profile app up -d --build

down: ## Stop all containers
	$(COMPOSE) --profile app down

logs: ## Tail application logs
	$(COMPOSE) --profile app logs -f api worker

migrate: ## Apply migrations + sync plan catalogue (host)
	cd $(BACKEND) && uv run scorecode migrate

seed: ## Create Thapar, Demo School and Demo Coaching tenants with synthetic data (host)
	cd $(BACKEND) && uv run scorecode seed

seed-stack: ## Seed inside the running container stack
	$(COMPOSE) --profile app exec api scorecode seed

seed-demo: ## Seed the stack with results history for the presentation (docs/demo/README.md)
	$(COMPOSE) --profile app exec api scorecode seed --with-history

monitoring: ## Prometheus, Alertmanager (→ Mailpit) and Grafana next to the stack → http://localhost:53000
	$(COMPOSE) --profile app --profile monitoring up -d

smoke: ## Read-only smoke test of a running deployment (SMOKE_BASE_DOMAIN, SMOKE_SCHEME; local stack by default)
	infra/ops/smoke.sh

platform-user: ## Create a platform (ScoreCode staff) account: make platform-user EMAIL=you@x NAME="You"
	cd $(BACKEND) && uv run scorecode create-platform-user --email "$(EMAIL)" --name "$(NAME)"

api: ## Run the API with autoreload on :8000 (host)
	cd $(BACKEND) && uv run scorecode api --reload

worker: ## Run a background worker (host)
	cd $(BACKEND) && uv run scorecode worker

web: ## Run the tenant, platform and site dev servers (Vite)
	cd $(FRONTEND) && pnpm dev

fmt: ## Format code
	cd $(BACKEND) && uv run ruff format app tests migrations && uv run ruff check --fix app tests migrations
	cd $(FRONTEND) && pnpm format

lint: ## Lint + type-check everything
	cd $(BACKEND) && uv run ruff format --check app tests migrations && uv run ruff check app tests migrations
	cd $(BACKEND) && uv run mypy app && uv run lint-imports
	@if [ -f $(FRONTEND)/package.json ]; then cd $(FRONTEND) && pnpm lint && pnpm typecheck; fi

test-unit: ## Backend unit tests (no services needed)
	cd $(BACKEND) && uv run pytest tests/unit -q

test-int: ## Backend integration + security suites (needs `make up`)
	cd $(BACKEND) && uv run pytest tests/integration -q

test: ## All backend + frontend tests
	cd $(BACKEND) && uv run pytest -q
	@if [ -f $(FRONTEND)/package.json ]; then cd $(FRONTEND) && pnpm test; fi

test-frontend: ## Frontend unit/component tests
	cd $(FRONTEND) && pnpm test

e2e: ## Playwright end-to-end tests against a running stack
	cd $(FRONTEND) && pnpm e2e

openapi: ## Regenerate backend/openapi.json and the TypeScript client types
	cd $(BACKEND) && uv run python -m app.openapi > openapi.json
	cd $(FRONTEND) && pnpm --filter @scorecode/api-client generate

build: ## Build production images
	$(COMPOSE) --profile app build
