# ============================================
# PRADY TRADER — Makefile (Windows / PowerShell)
# ============================================
# Usage:  make <target>   (GNU Make 4+ or nmake)
# On Windows without make:  powershell -File scripts\make.ps1 <target>
#
# All paths use PowerShell-compatible commands so the same
# Makefile works under Git-Bash, MSYS2, and Windows Terminal.
# ============================================

SHELL := powershell.exe
.SHELLFLAGS := -NoProfile -Command

.PHONY: install desktop run run-managed test backtest docker-up docker-down \
	train lint clean validate telegram-test health

# ---------- Setup ----------

install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

# ---------- Docker ----------

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-restart: docker-down docker-up

# ---------- Run ----------

desktop:
	python run_desktop.py

run:
	python scripts/start_paper.py

run-managed:
	python scripts/process_manager.py

# ---------- ML / Backtest ----------

train:
	python scripts/train_models.py

backtest:
	python scripts/backtest.py

# ---------- Testing ----------

test:
	pytest tests/ -v --tb=short

validate:
	python scripts/validate_build.py

# ---------- Linting ----------

lint:
	python -m py_compile config/settings.py
	python -m py_compile config/constants.py
	python -m py_compile utils/logger_setup.py
	python -m py_compile utils/rate_limiter.py
	python -m py_compile utils/health_monitor.py
	python -m py_compile utils/telegram_bot.py
	python -m py_compile scripts/process_manager.py
	python -m py_compile scripts/start_paper.py

# ---------- Utilities ----------

telegram-test:
	python -c "from utils.telegram_bot import get_telegram_bot; import asyncio; asyncio.run(get_telegram_bot().send_test())"

health:
	python -c "import json, pathlib; p=pathlib.Path('data/health_status.json'); print(json.dumps(json.loads(p.read_text()),indent=2) if p.exists() else 'No health data yet')"

# ---------- Cleanup ----------

clean:
	Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
	Get-ChildItem -Recurse -File -Filter *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue
	if (Test-Path .pytest_cache) { Remove-Item -Recurse -Force .pytest_cache }
	if (Test-Path htmlcov)       { Remove-Item -Recurse -Force htmlcov }
	if (Test-Path .coverage)     { Remove-Item -Force .coverage }
