# Unraid Config Guardian Makefile

PYTHON ?= python3
PIP ?= pip3
APP_DIRS := src tests
DOCKER_COMPOSE := docker-compose
DOCKER_COMPOSE_DEV := $(DOCKER_COMPOSE) -f docker-compose.dev.yml
IMAGE_NAME := unraid-config-guardian
IMAGE_TAG ?= latest
CONTAINER_NAME := unraid-config-guardian

BLACK := black $(APP_DIRS)
ISORT := isort $(APP_DIRS)
FLAKE8 := flake8 $(APP_DIRS) --max-line-length=100 --extend-ignore=E203,W503,E231,E221,E272,E201,E202,E702,E271
PYTEST := pytest tests/ -v
PYTEST_COV := $(PYTEST) --cov=src/ --cov-report=html --cov-report=term

COLOR ?= 1
ifeq ($(COLOR),1)
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m
else
BLUE :=
GREEN :=
YELLOW :=
NC :=
endif

.PHONY: help dev-setup install install-dev hooks lint format format-check type-check test test-cov run run-gui run-prod health clean clean-all check fix-and-check docker-build docker-run docker-dev docker-stop docker-stop-dev docker-logs docker-logs-dev docker-shell docker-health docker-clean ci-test ci-build ci-push tag release-patch release-minor release-major list-releases all deploy

help: ## Show this help message
	@echo "$(BLUE)Unraid Config Guardian - Development Commands$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-18s$(NC) %s\n", $$1, $$2}'

dev-setup: ## Create venv and print next steps
	@echo "$(BLUE)Setting up development environment...$(NC)"
	$(PYTHON) -m venv venv
	@echo "$(YELLOW)Activate with: source venv/bin/activate$(NC)"
	@echo "$(YELLOW)Then run: make install-dev$(NC)"

install: ## Install runtime dependencies
	$(PIP) install -r requirements.txt

hooks: ## Install git hooks
	pre-commit install --install-hooks
	cp .githooks/pre-push .git/hooks/pre-push
	chmod +x .git/hooks/pre-push

install-dev: install hooks ## Install runtime + development dependencies
	$(PIP) install -r requirements-dev.txt

lint: ## Run flake8
	$(FLAKE8)

format: ## Format with black and isort
	$(BLACK)
	$(ISORT)

format-check: ## Check formatting
	$(BLACK) --check
	$(ISORT) --check-only

type-check: ## Run type checks with mypy
	mypy src/ --ignore-missing-imports

test: ## Run tests
	$(PYTEST)

test-cov: ## Run tests with coverage
	$(PYTEST_COV)

run: ## Run the CLI locally (debug)
	mkdir -p ./output
	$(PYTHON) src/unraid_config_guardian.py --output ./output --debug

run-gui: ## Run the dev web GUI
	mkdir -p ./output
	$(PYTHON) src/web_gui_dev.py

run-prod: ## Run the CLI in production mode
	mkdir -p ./output
	$(PYTHON) src/unraid_config_guardian.py --output ./output

health: ## Run health check
	$(PYTHON) src/health_check.py

docker-build: ## Build Docker image
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

docker-run: ## Run Docker container (production/Unraid)
	$(DOCKER_COMPOSE) up -d

docker-dev: ## Run Docker container (local development)
	mkdir -p ./config ./output
	$(DOCKER_COMPOSE_DEV) up -d

docker-stop: ## Stop Docker container
	$(DOCKER_COMPOSE) down

docker-stop-dev: ## Stop development Docker container
	$(DOCKER_COMPOSE_DEV) down

docker-logs: ## Show Docker container logs
	$(DOCKER_COMPOSE) logs -f

docker-logs-dev: ## Show development container logs
	$(DOCKER_COMPOSE_DEV) logs -f

docker-shell: ## Get shell in running container
	docker exec -it $(CONTAINER_NAME) /bin/bash

docker-health: ## Check container health
	docker exec $(CONTAINER_NAME) $(PYTHON) src/health_check.py

docker-clean: ## Clean up Docker resources
	$(DOCKER_COMPOSE) down --volumes --rmi all
	docker system prune -f

clean: ## Clean up generated files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/ output/ logs/

clean-all: clean docker-clean ## Clean everything including Docker resources

check: format-check lint type-check test ## Run all quality checks

fix-and-check: format lint type-check test ## Auto-format then run checks

all: clean install-dev check docker-build ## Run complete development workflow

deploy: check docker-build docker-run ## Deploy to production

ci-test: ## Run CI tests (coverage XML for CI)
	$(PYTEST) --cov=src/ --cov-report=xml --cov-report=term

ci-build: ## Build multi-platform image
	docker buildx build --platform linux/amd64,linux/arm64 -t $(IMAGE_NAME):$(IMAGE_TAG) .

ci-push: ## Push to Docker Hub
	docker push $(IMAGE_NAME):$(IMAGE_TAG)

tag: ## Create and push a new tag (usage: make tag VERSION=v1.0.0)
	@if [ -z "$(VERSION)" ]; then echo "Usage: make tag VERSION=v1.0.0"; exit 1; fi
	@VERSION_NUM=$$(echo $(VERSION) | sed 's/^v//'); \
	sed -i '' "s/__version__ = \".*\"/__version__ = \"$$VERSION_NUM\"/" src/version.py; \
	git add src/version.py; \
	git commit -m "Update version to $$VERSION_NUM"; \
	git tag -a $(VERSION) -m "Release $(VERSION)"; \
	git push origin main; \
	git push origin $(VERSION)

release-patch: ## Create patch release (v1.0.0 -> v1.0.1)
	@LATEST=$$(git tag -l "v*.*.*" | sort -V | tail -1); \
	if [ -z "$$LATEST" ]; then NEW_VERSION="v1.0.0"; \
	else MAJOR=$$(echo $$LATEST | cut -d. -f1); MINOR=$$(echo $$LATEST | cut -d. -f2); PATCH=$$(echo $$LATEST | cut -d. -f3); \
	NEW_PATCH=$$((PATCH + 1)); NEW_VERSION="$$MAJOR.$$MINOR.$$NEW_PATCH"; fi; \
	echo "Next version: $$NEW_VERSION"; \
	make tag VERSION=$$NEW_VERSION

release-minor: ## Create minor release (v1.0.x -> v1.1.0)
	@LATEST=$$(git tag -l "v*.*.*" | sort -V | tail -1); \
	if [ -z "$$LATEST" ]; then NEW_VERSION="v1.0.0"; \
	else MAJOR=$$(echo $$LATEST | cut -d. -f1); MINOR=$$(echo $$LATEST | cut -d. -f2); \
	NEW_MINOR=$$((MINOR + 1)); NEW_VERSION="$$MAJOR.$$NEW_MINOR.0"; fi; \
	echo "Next version: $$NEW_VERSION"; \
	make tag VERSION=$$NEW_VERSION

release-major: ## Create major release (v1.x.x -> v2.0.0)
	@LATEST=$$(git tag -l "v*.*.*" | sort -V | tail -1); \
	if [ -z "$$LATEST" ]; then NEW_VERSION="v1.0.0"; \
	else MAJOR=$$(echo $$LATEST | cut -d. -f1 | sed 's/v//'); \
	NEW_MAJOR=$$((MAJOR + 1)); NEW_VERSION="v$$NEW_MAJOR.0.0"; fi; \
	echo "Next version: $$NEW_VERSION"; \
	make tag VERSION=$$NEW_VERSION

list-releases: ## List recent releases
	@git tag -l "v*.*.*" | sort -V | tail -10
