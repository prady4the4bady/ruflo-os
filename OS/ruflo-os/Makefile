# Makefile for NemOS (Ruflo OS)

.PHONY: test lint format clean install run

# Install dependencies
install:
	pip install -r requirements.txt
	pip install -r model-gateway/requirements.txt
	pip install -r control-plane/requirements.txt
	pip install -r ruflo-shell/requirements.txt

# Run all tests
test:
	pytest tests/ -v

# Run specific test suites
test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-e2e:
	pytest tests/e2e/ -v

test-desktop:
	pytest tests/desktop/ -v

# Lint code
lint:
	ruff check .
	mypy .

# Format code
format:
	ruff format .
	black .

# Clean build artifacts
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage

# Run the desktop (requires GTK4/Adwaita)
run:
	python ruflo-shell/main.py

# Run model gateway
run-gateway:
	cd model-gateway && uvicorn src.main:app --host 0.0.0.0 --port 8001

# Run control plane
run-control:
	cd control-plane && uvicorn src.main:app --host 0.0.0.0 --port 8000

# Run agent orchestrator
run-agent:
	cd agents && python -m src.orchestrator

# Build distribution (if building ISO)
build-iso:
	cd distro && make -f Makefile

# Full system check
check: lint test
	@echo "All checks passed!"

# Help
help:
	@echo "NemOS (Ruflo OS) Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  install    - Install dependencies"
	@echo "  test       - Run all tests"
	@echo "  lint       - Lint code"
	@echo "  format     - Format code"
	@echo "  clean      - Clean artifacts"
	@echo "  run        - Run desktop"
	@echo "  check      - Run lint and tests"
