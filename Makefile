# ========== CONFIGURATION ==========
TARGET = cv
OUTDIR = out
SRC_DIR = src
TEMPLATE_DIR = $(SRC_DIR)/template
INPUT_JSON = data/cv.json
MARKET_RULES = data/target_market_rules.json
MARKET ?= default

UV = uv
PYTHON = $(UV) run python
LATEX = pdflatex -synctex=1 -interaction=nonstopmode -output-directory=$(OUTDIR)

GENERATOR = $(SRC_DIR)/generate_cv.py
SOURCE = $(OUTDIR)/$(TARGET).tex
OUTPUT = $(OUTDIR)/$(TARGET).pdf
COMMIT_SHA = $(shell git rev-parse --short HEAD)

# ========== PHONY TARGETS ==========
.PHONY: all build clean cleanall check-latex check-uv \
        setup setup-dev install install-dev \
        prod-build local-build setup-all

# ========== DEFAULT TARGET ==========
all: setup-all check-latex build

# ========== BUILD ==========
build: check-uv
	@mkdir -p $(OUTDIR)
	@echo "Generating CV LaTeX source..."
	@$(PYTHON) $(GENERATOR) --input $(INPUT_JSON) --output $(SOURCE) --template-dir $(TEMPLATE_DIR) --commit-sha $(COMMIT_SHA) --market $(MARKET) --market-rules $(MARKET_RULES)
	@$(LATEX) $(SOURCE)

check-latex:
	@command -v pdflatex >/dev/null 2>&1 || { echo "Error: pdflatex is not installed."; exit 1; }

check-uv:
	@command -v $(UV) >/dev/null 2>&1 || { echo "Error: uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }

clean:
	@rm -f $(OUTDIR)/*.{aux,log,synctex.gz,out,toc,bbl,blg,fdb_latexmk,fls,tex}

cleanall: clean
	@rm -rf $(OUTDIR)/

# ========== ENVIRONMENT ==========
install: check-uv
	@$(UV) sync --no-dev

install-dev: check-uv
	@$(UV) sync
	@$(UV) run pre-commit install

setup-dev: install-dev
setup: install
setup-all: setup-dev

# ========== PROD / LOCAL ==========
local-build: check-latex build
prod-build: setup check-latex build
