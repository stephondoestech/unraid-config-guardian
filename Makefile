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
	@echo "$(GREEN)Development environment ready!$(NC)"

# Code Quality
lint: ## Run linting with flake8
	@echo "$(BLUE)Running linting...$(NC)"
	flake8 src/ --max-line-length=88 --extend-ignore=E203,W503

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(NC)"
	black src/ tests/

format-check: ## Check if code is formatted correctly
	@echo "$(BLUE)Checking code format...$(NC)"
	black --check src/ tests/

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
	@echo "$(BLUE)Starting Web GUI on http://localhost:8080$(NC)"
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
check: lint type-check test ## Run all quality checks

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