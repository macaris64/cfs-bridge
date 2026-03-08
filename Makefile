.PHONY: build test coverage start-mission stop integration clean help

# ── Help ──────────────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Build ─────────────────────────────────────────────────────────────
build: ## Build all Docker containers
	docker compose build

# ── Test ──────────────────────────────────────────────────────────────
test: ## Run all unit tests (sensor_manager + ground_station)
	python -m pytest sensor_manager/tests/ ground_station/tests/ -v

# ── Coverage ──────────────────────────────────────────────────────────
coverage: ## Run tests with coverage report
	python -m pytest sensor_manager/tests/ ground_station/tests/ \
		--cov=sensor_manager/core --cov=sensor_manager/sensors \
		--cov=ground_station \
		--cov-report=term-missing -v

# ── Start Mission ─────────────────────────────────────────────────────
start-mission: build ## Build and start all services
	docker compose up -d
	@echo ""
	@echo "Mission started. Services:"
	@echo "  cFS Flight Software:  container 'cfs-flight'"
	@echo "  Sensor Manager UI:    http://localhost:8501"
	@echo "  Ground Station UI:    http://localhost:8502"
	@echo ""

# ── Stop ──────────────────────────────────────────────────────────────
stop: ## Stop all services
	docker compose down

# ── Integration ───────────────────────────────────────────────────────
integration: ## Run full integration verification (containers must be running)
	python -m pytest -m integration -v
	python integration_suite.py

integration-full: build ## Build, start, and run integration suite
	docker compose up -d
	@echo "Waiting for services to initialize..."
	@sleep 15
	python integration_suite.py

# ── Clean ─────────────────────────────────────────────────────────────
clean: ## Stop containers and remove images
	docker compose down --rmi local --remove-orphans
