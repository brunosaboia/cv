# ========== CONFIGURATION ==========
TARGET = cv
OUTDIR = out
SRC_DIR = src
TEMPLATE_DIR = $(SRC_DIR)/template
INPUT_JSON = data/cv.json

VENV ?= .venv
VENV_BIN = $(VENV)/bin
PYTHON = $(VENV_BIN)/python
LATEX = pdflatex -synctex=1 -interaction=nonstopmode -output-directory=$(OUTDIR)

GENERATOR = $(SRC_DIR)/generate_cv.py
SOURCE = $(OUTDIR)/$(TARGET).tex
OUTPUT = $(OUTDIR)/$(TARGET).pdf
COMMIT_SHA = $(shell git rev-parse --short HEAD)

# ========== PHONY TARGETS ==========
.PHONY: all build clean cleanall check-latex \
        setup setup-dev install install-dev \
        create-venv prod-build local-build \
        setup-all check-venv

# ========== DEFAULT TARGET ==========
all: setup-all check-latex build

# ========== BUILD ==========
build: check-venv
	@mkdir -p $(OUTDIR)
	@echo "Generating CV LaTeX source..."
	@$(PYTHON) $(GENERATOR) --input $(INPUT_JSON) --output $(SOURCE) --template-dir $(TEMPLATE_DIR) --commit-sha $(COMMIT_SHA)
	@$(LATEX) $(SOURCE)

check-latex:
	@command -v pdflatex >/dev/null 2>&1 || { echo "Error: pdflatex is not installed."; exit 1; }

check-venv:
	@test -x "$(PYTHON)" || (echo "Missing venv! Run: make setup-dev"; exit 1)

clean:
	@rm -f $(OUTDIR)/*.{aux,log,synctex.gz,out,toc,bbl,blg,fdb_latexmk,fls,tex}

cleanall: clean
	@rm -rf $(OUTDIR)/

# ========== ENVIRONMENT ==========
create-venv:
	@if [ ! -d $(VENV) ]; then \
		echo "Creating virtual environment at $(VENV)..."; \
		PY=$(shell command -v python3 || command -v python); \
		if [ -z "$$PY" ]; then \
			echo "Error: No suitable Python interpreter found."; \
			exit 1; \
		fi; \
		$$PY -m venv $(VENV); \
	fi
	@$(PYTHON) -m pip install --upgrade pip

install:
	@$(PYTHON) -m pip install -r $(SRC_DIR)/requirements.txt

install-dev:
	@$(PYTHON) -m pip install -r $(SRC_DIR)/requirements-dev.txt
	@$(PYTHON) -m pip show pre-commit >/dev/null || { echo "ERROR: pre-commit not installed"; exit 1; }
	@$(PYTHON) -m pre_commit install

setup-dev: create-venv install install-dev
setup: create-venv install
setup-all: setup-dev

# ========== PROD / LOCAL ==========
local-build: check-latex build
prod-build: setup check-latex build
