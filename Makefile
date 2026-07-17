# ========== CONFIGURATION ==========
# Everything here is overridable from the command line or the environment,
# e.g.:  make build DATA_DIR=/path/to/cv-data MARKET=CH
MARKET ?= default

# Default output name carries the market so matrix builds don't overwrite
# each other; the default market keeps the plain name.
ifeq ($(MARKET),default)
TARGET ?= cv
else
TARGET ?= cv-$(MARKET)
endif

OUTDIR ?= out
SRC_DIR = src
TEMPLATE_DIR ?= $(SRC_DIR)/template
DATA_DIR ?= data
INPUT_JSON ?= $(DATA_DIR)/cv.json
MARKET_RULES ?= config/market_rules.json
STRICT ?= 0
COMMIT_SHA ?= $(shell git rev-parse --short HEAD)

UV = uv
PYTHON = $(UV) run python
LATEX = pdflatex -synctex=1 -interaction=nonstopmode -output-directory=$(OUTDIR)

GENERATOR = $(SRC_DIR)/generate_cv.py
GEN_FLAGS = --input $(INPUT_JSON) --output $(SOURCE) --template-dir $(TEMPLATE_DIR) \
            --data-dir $(DATA_DIR) --commit-sha $(COMMIT_SHA) \
            --market $(MARKET) --market-rules $(MARKET_RULES) \
            $(if $(filter 1,$(STRICT)),--strict)
SOURCE = $(OUTDIR)/$(TARGET).tex
OUTPUT = $(OUTDIR)/$(TARGET).pdf

# ========== PHONY TARGETS ==========
.PHONY: all build clean cleanall check-latex check-uv \
        setup setup-dev install install-dev install-frozen \
        prod-build local-build setup-all

# ========== DEFAULT TARGET ==========
all: setup-all check-latex build

# ========== BUILD ==========
build: check-uv
	@mkdir -p $(OUTDIR)
	@echo "Generating CV LaTeX source..."
	@$(PYTHON) $(GENERATOR) $(GEN_FLAGS)
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

# CI variant: the lockfile is authoritative; fail on drift instead of re-resolving.
install-frozen: check-uv
	@$(UV) sync --frozen --no-dev

install-dev: check-uv
	@$(UV) sync
	@$(UV) run pre-commit install

setup-dev: install-dev
setup: install
setup-all: setup-dev

# ========== PROD / LOCAL ==========
local-build: check-latex build

prod-build: STRICT = 1
prod-build: install-frozen check-latex build
