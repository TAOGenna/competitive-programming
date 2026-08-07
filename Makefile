# vrating
#
#   make dev              start it and open the page
#   make dev H=handle     and warm that handle's contests first
#   make test             the offline tests
#   make test-all         including the network-bound ones
#   make warm H=handle    warm a handle's contests without starting the server
#   make clean            drop the cache (it is all re-fetchable)

PY ?= python3
VENV := .venv
BIN := $(VENV)/bin
H ?=

.PHONY: dev test test-all warm clean install

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

test: $(BIN)/python
	@$(BIN)/python -m pytest tests -q -m "not gate"

test-all: $(BIN)/python
	@$(BIN)/python -m pytest tests -q

clean:
	@rm -rf data
	@echo "cache dropped; it refetches on demand"
