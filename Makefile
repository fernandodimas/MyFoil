VENV ?= venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
RUFF ?= $(VENV)/bin/ruff

.PHONY: dev test lint clean install

dev:
	$(PYTHON) app/app.py

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

lint:
	$(RUFF) check app/ tests/ --fix

install:
	$(PIP) install -r requirements.txt -r requirements-dev.txt

clean:
	rm -rf htmlcov/ .coverage .pytest_cache __pycache__
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
