.PHONY: help up down build test test-security test-stress benchmark logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --------------- Docker ---------------

up: ## Start CortexDB (router + infrastructure)
	docker compose up -d relational-core memory-core stream-core vector-core
	docker compose up -d cortex-router

up-all: ## Start everything including observability
	docker compose --profile observability up -d

down: ## Stop all containers
	docker compose --profile observability --profile dashboard down

build: ## Build the CortexDB router image
	docker compose build cortex-router

rebuild: ## Force rebuild (no cache)
	docker compose build --no-cache cortex-router

logs: ## Tail router logs
	docker compose logs -f cortex-router

ps: ## Show container status
	docker compose ps

# --------------- Testing ---------------

test: ## Run all tests (benchmark + security)
	docker run --rm --network cortexdb_cortex-net \
		-v "$$(pwd):/app" -w /app python:3.12-slim \
		bash -c "pip install -q httpx pytest pytest-asyncio && \
		python -m pytest tests/benchmark/ tests/security/ -v \
		--benchmark-url=http://cortex-router:5400 \
		--pentest-url=http://cortex-router:5400"

test-security: ## Run security pentest suite
	docker run --rm --network cortexdb_cortex-net \
		-v "$$(pwd):/app" -w /app python:3.12-slim \
		bash -c "pip install -q httpx pytest pytest-asyncio && \
		python -m pytest tests/security/ -v \
		--pentest-url=http://cortex-router:5400"

test-stress: ## Run stress tests
	docker run --rm --network cortexdb_cortex-net \
		-v "$$(pwd):/app" -w /app python:3.12-slim \
		bash -c "pip install -q httpx pytest pytest-asyncio && \
		python -m pytest tests/stress/ -v \
		--stress-url=http://cortex-router:5400"

benchmark: ## Run benchmark CLI
	docker run --rm --network cortexdb_cortex-net \
		-v "$$(pwd):/app" -w /app python:3.12-slim \
		bash -c "pip install -q httpx && \
		python scripts/benchmark.py --http --url http://cortex-router:5400"

# --------------- Database ---------------

db-init: ## Run database migrations manually
	docker exec cortex-relational psql -U cortex -d cortexdb \
		-f /docker-entrypoint-initdb.d/01-init.sql
	docker exec cortex-relational psql -U cortex -d cortexdb \
		-f /docker-entrypoint-initdb.d/02-sharding.sql

db-shell: ## Open psql shell
	docker exec -it cortex-relational psql -U cortex -d cortexdb

# --------------- Utilities ---------------

health: ## Check CortexDB health
	@curl -s http://localhost:5400/health/live | python -m json.tool 2>/dev/null || echo "CortexDB not running"

deep-health: ## Detailed health check
	@curl -s http://localhost:5400/health/deep | python -m json.tool 2>/dev/null || echo "CortexDB not running"

clean: ## Remove all volumes and data
	docker compose --profile observability --profile dashboard down -v
	@echo "All volumes removed"
