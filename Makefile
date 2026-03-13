VENV := backend/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup install-backend install-frontend index sample backend frontend run test

run: setup
	@echo "==> Starting backend and frontend..."
	@(cd backend && $(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) & \
	 (cd frontend && npm run dev) & \
	 wait

setup: install-backend install-frontend
	@echo "==> Ensuring Ollama is running..."
	@if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then \
		echo "    Starting Ollama..."; \
		ollama serve > /dev/null 2>&1 & \
		sleep 3; \
	fi
	@echo "==> Pulling Ollama models (this may take a while on first run)..."
	-@ollama pull nomic-embed-text || echo "    WARNING: Failed to pull nomic-embed-text"
	-@ollama pull mistral || echo "    WARNING: Failed to pull mistral"
	@echo "==> Setup complete."

$(VENV):
	python3 -m venv $(VENV)

install-backend: $(VENV)
	@echo "==> Installing backend dependencies..."
	cd backend && $(abspath $(PIP)) install -e ".[dev]"

install-frontend:
	@echo "==> Installing frontend dependencies..."
	cd frontend && npm install

model:
	@bash scripts/setup_model.sh

backend: $(VENV)
	cd backend && $(abspath $(VENV))/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

index:
	@if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then \
		echo "==> Ollama not running, starting it..."; \
		ollama serve > /dev/null 2>&1 & \
		sleep 3; \
	fi
	@if ! curl -s http://localhost:8000/healthz > /dev/null 2>&1; then \
		echo "==> Backend not running, starting it in background..."; \
		(cd backend && $(abspath $(VENV))/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &) ; \
		echo "==> Waiting for backend to be ready..."; \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			sleep 1; \
			if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then break; fi; \
		done; \
	fi
	@echo "==> Indexing documents..."
	@curl -s -X POST http://localhost:8000/index -H "Content-Type: application/json" -d '{}' | python3 -m json.tool

sample:
	@bash scripts/run_sample.sh

test: install-backend
	cd backend && $(abspath $(PYTHON)) -m pytest tests/ -v
