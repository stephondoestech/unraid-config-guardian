# Unraid Config Guardian Makefile

# Variables
IMAGE_NAME := unraid-config-guardian
IMAGE_TAG := latest
CONTAINER_NAME := unraid-config-guardian
PYTHON := python3
PIP := pip3

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

.PHONY: help install install-dev test lint format type-check clean build run stop logs shell health dev-setup docker-build docker-run docker-stop docker-clean all

# Default target
help: ## Show this help message
	@echo "$(BLUE)Unraid Config Guardian - Development Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# Development Setup
dev-setup: ## Set up development environment
	@echo "$(BLUE)Setting up development environment...$(NC)"
	$(PYTHON) -m venv venv
	@echo "$(YELLOW)Activate with: source venv/bin/activate$(NC)"
	@echo "$(YELLOW)Then run: make install-dev$(NC)"

install: ## Install runtime dependencies
	@echo "$(BLUE)Installing runtime dependencies...$(NC)"
	$(PIP) install -r requirements.txt

install-dev: install ## Install development dependencies
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	$(PIP) install -r requirements-dev.txt
	@echo "$(BLUE)Setting up pre-commit hooks...$(NC)"
	pre-commit install --install-hooks
	@echo "$(BLUE)Installing custom pre-push hook...$(NC)"
	cp .githooks/pre-push .git/hooks/pre-push
	chmod +x .git/hooks/pre-push
	@echo "$(GREEN)Development environment ready!$(NC)"

# Code Quality
lint: ## Run linting with flake8
	@echo "$(BLUE)Running linting...$(NC)"
	flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503,E231,E221,E272,E201,E202,E702,E271

format: ## Format code with black and isort
	@echo "$(BLUE)Formatting code...$(NC)"
	black src/ tests/
	isort src/ tests/

format-check: ## Check if code is formatted correctly
	@echo "$(BLUE)Checking code format...$(NC)"
	black --check src/ tests/
	isort --check-only src/ tests/

format-fix: ## Auto-fix all formatting and linting issues
	@echo "$(BLUE)Auto-fixing formatting and linting...$(NC)"
	black src/ tests/
	isort src/ tests/
	@echo "$(GREEN)Auto-formatting complete!$(NC)"
	@echo "$(YELLOW)Run 'make lint' to see remaining issues$(NC)"

install-hooks: ## Install git hooks manually
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	pre-commit install --install-hooks
	@echo "$(BLUE)Installing custom pre-push hook...$(NC)"
	cp .githooks/pre-push .git/hooks/pre-push
	chmod +x .git/hooks/pre-push
	@echo "$(GREEN)Git hooks installed!$(NC)"
	@echo "$(YELLOW)Pre-commit will run on commits, pre-push will auto-fix formatting before pushes$(NC)"

pre-commit-run: ## Run all pre-commit hooks
	@echo "$(BLUE)Running pre-commit hooks...$(NC)"
	pre-commit run --all-files

pre-commit-update: ## Update pre-commit hook versions
	@echo "$(BLUE)Updating pre-commit hooks...$(NC)"
	pre-commit autoupdate

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checks...$(NC)"
	mypy src/ --ignore-missing-imports

# Testing
test: ## Run tests with pytest
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/ -v

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest tests/ -v --cov=src/ --cov-report=html --cov-report=term

# Application
run: ## Run the application locally (CLI)
	@echo "$(BLUE)Running Unraid Config Guardian CLI...$(NC)"
	mkdir -p ./output
	$(PYTHON) src/unraid_config_guardian.py --output ./output --debug

run-gui: ## Run the web GUI locally
	@echo "$(BLUE)Starting Web GUI on http://localhost:7842$(NC)"
	mkdir -p ./output
	$(PYTHON) src/web_gui_dev.py

run-prod: ## Run the application in production mode
	@echo "$(BLUE)Running in production mode...$(NC)"
	mkdir -p ./output
	$(PYTHON) src/unraid_config_guardian.py --output ./output

health: ## Run health check
	@echo "$(BLUE)Running health check...$(NC)"
	$(PYTHON) src/health_check.py

# Docker Commands
docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

docker-run: ## Run Docker container (production/Unraid)
	@echo "$(BLUE)Running Docker container...$(NC)"
	docker-compose up -d

docker-dev: ## Run Docker container (local development)
	@echo "$(BLUE)Running Docker container for development...$(NC)"
	mkdir -p ./config ./output
	docker-compose -f docker-compose.dev.yml up -d

docker-stop: ## Stop Docker container
	@echo "$(BLUE)Stopping Docker container...$(NC)"
	docker-compose down

docker-stop-dev: ## Stop development Docker container
	@echo "$(BLUE)Stopping development Docker container...$(NC)"
	docker-compose -f docker-compose.dev.yml down

docker-logs: ## Show Docker container logs
	@echo "$(BLUE)Showing container logs...$(NC)"
	docker-compose logs -f

docker-logs-dev: ## Show development container logs
	@echo "$(BLUE)Showing development container logs...$(NC)"
	docker-compose -f docker-compose.dev.yml logs -f

docker-shell: ## Get shell in running container
	@echo "$(BLUE)Entering container shell...$(NC)"
	docker exec -it $(CONTAINER_NAME) /bin/bash

docker-health: ## Check container health
	@echo "$(BLUE)Checking container health...$(NC)"
	docker exec $(CONTAINER_NAME) python src/health_check.py

docker-clean: ## Clean up Docker resources
	@echo "$(BLUE)Cleaning up Docker resources...$(NC)"
	docker-compose down --volumes --rmi all
	docker system prune -f

# Utility
clean: ## Clean up generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/
	rm -rf output/ logs/

clean-all: clean docker-clean ## Clean everything including Docker resources

# Quality checks combined
check: format-check lint type-check test ## Run all quality checks

# Auto-fix and check workflow
fix-and-check: format-fix lint type-check test ## Auto-fix issues then run checks

# Complete workflow
all: clean install-dev check docker-build ## Run complete development workflow

# Development workflow
dev: dev-setup ## Quick development setup
	@echo "$(GREEN)Development environment created!$(NC)"
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. source venv/bin/activate"
	@echo "  2. make install-dev"
	@echo "  3. make run"

# Production deployment
deploy: check docker-build docker-run ## Deploy to production
	@echo "$(GREEN)Deployment complete!$(NC)"
	@echo "$(YELLOW)Check status with: make docker-logs$(NC)"

# CI/CD commands
ci-test: ## Run CI tests (used by GitHub Actions)
	@echo "$(BLUE)Running CI test suite...$(NC)"
	pytest tests/ -v --cov=src/ --cov-report=xml --cov-report=term

ci-build: ## Build for CI (multi-platform)
	@echo "$(BLUE)Building multi-platform image...$(NC)"
	docker buildx build --platform linux/amd64,linux/arm64 -t $(IMAGE_NAME):$(IMAGE_TAG) .

ci-push: ## Push to Docker Hub (used by GitHub Actions)
	@echo "$(BLUE)Pushing to Docker Hub...$(NC)"
	docker push $(IMAGE_NAME):$(IMAGE_TAG)

# Release commands
tag: ## Create and push a new tag (usage: make tag VERSION=v1.0.0)
	@if [ -z "$(VERSION)" ]; then echo "Usage: make tag VERSION=v1.0.0"; exit 1; fi
	@echo "$(BLUE)Creating tag $(VERSION)...$(NC)"
	@VERSION_NUM=$$(echo $(VERSION) | sed 's/^v//'); \
	echo "Updating src/version.py to $$VERSION_NUM"; \
	sed -i '' "s/__version__ = \".*\"/__version__ = \"$$VERSION_NUM\"/" src/version.py; \
	git add src/version.py; \
	git commit -m "Update version to $$VERSION_NUM"; \
	git tag -a $(VERSION) -m "Release $(VERSION)"; \
	git push origin main; \
	git push origin $(VERSION)
	@echo "$(GREEN)Tag $(VERSION) created and pushed!$(NC)"
	@echo "$(YELLOW)GitHub Actions will automatically:$(NC)"
	@echo "  - Build and push Docker image: stephondoestech/unraid-config-guardian:$(VERSION)"
	@echo "  - Create GitHub Release"
	@echo "  - Update latest tag"

release-patch: ## Create patch release (v1.0.0 -> v1.0.1)
	@echo "$(BLUE)Creating patch release...$(NC)"
	@LATEST=$$(git tag -l "v*.*.*" | sort -V | tail -1); \
	if [ -z "$$LATEST" ]; then \
		NEW_VERSION="v1.0.0"; \
	else \
		MAJOR=$$(echo $$LATEST | cut -d. -f1); \
		MINOR=$$(echo $$LATEST | cut -d. -f2); \
		PATCH=$$(echo $$LATEST | cut -d. -f3); \
		NEW_PATCH=$$((PATCH + 1)); \
		NEW_VERSION="$$MAJOR.$$MINOR.$$NEW_PATCH"; \
	fi; \
	echo "Next version: $$NEW_VERSION"; \
	make tag VERSION=$$NEW_VERSION

release-minor: ## Create minor release (v1.0.x -> v1.1.0)
	@echo "$(BLUE)Creating minor release...$(NC)"
	@LATEST=$$(git tag -l "v*.*.*" | sort -V | tail -1); \
	if [ -z "$$LATEST" ]; then \
		NEW_VERSION="v1.0.0"; \
	else \
		MAJOR=$$(echo $$LATEST | cut -d. -f1); \
		MINOR=$$(echo $$LATEST | cut -d. -f2); \
		NEW_MINOR=$$((MINOR + 1)); \
		NEW_VERSION="$$MAJOR.$$NEW_MINOR.0"; \
	fi; \
	echo "Next version: $$NEW_VERSION"; \
	make tag VERSION=$$NEW_VERSION

release-major: ## Create major release (v1.x.x -> v2.0.0)
	@echo "$(BLUE)Creating major release...$(NC)"
	@LATEST=$$(git tag -l "v*.*.*" | sort -V | tail -1); \
	if [ -z "$$LATEST" ]; then \
		NEW_VERSION="v1.0.0"; \
	else \
		MAJOR=$$(echo $$LATEST | cut -d. -f1 | sed 's/v//'); \
		NEW_MAJOR=$$((MAJOR + 1)); \
		NEW_VERSION="v$$NEW_MAJOR.0.0"; \
	fi; \
	echo "Next version: $$NEW_VERSION"; \
	make tag VERSION=$$NEW_VERSION

list-releases: ## List all releases
	@echo "$(BLUE)Available releases:$(NC)"
	@git tag -l "v*.*.*" | sort -V | tail -10
