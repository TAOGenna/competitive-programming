# vrating
#
#   make dev              start it and open the page (on VRATING_HANDLES from .env)
#   make dev H=handle     and warm that handle's contests first
#   make test             the offline tests
#   make test-all         including the network-bound ones
#   make warm             warm the .env handles' contests without starting the server
#   make warm H=handle    the same for a handle you name
#   make warm-all         warm the whole archive: ~25 min and ~600 MB kept
#   make clean            drop the cache (it is all re-fetchable)

PY ?= python3
VENV := .venv
BIN := $(VENV)/bin
H ?=

.PHONY: dev test test-all warm warm-all clean install

$(BIN)/python:
	@echo "setting up (first run only)…"
	@$(PY) -m venv $(VENV)
	@$(BIN)/pip install --quiet --upgrade pip
	@$(BIN)/pip install --quiet -r requirements.txt

install: $(BIN)/python

dev: $(BIN)/python
	@$(BIN)/python -m vrating $(H)

warm: $(BIN)/python
	@$(BIN)/python -m vrating.sources.prewarm $(H)

warm-all: $(BIN)/python
	@$(BIN)/python -m vrating.sources.prewarm --all

test: $(BIN)/python
	@$(BIN)/python -m pytest tests -q -m "not gate"

test-all: $(BIN)/python
	@$(BIN)/python -m pytest tests -q

clean:
	@rm -rf data
	@echo "cache dropped; it refetches on demand"
