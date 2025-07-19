TARGET = cv
OUTDIR = out

SOURCE = $(OUTDIR)/$(TARGET).tex
OUTPUT = $(OUTDIR)/$(TARGET).pdf
HASH_FILE = data/.cv.json.md5

LATEX = pdflatex -synctex=1 -interaction=nonstopmode -output-directory=$(OUTDIR)
PYTHON = python
GENERATOR = src/generate_cv.py
INPUT_JSON = data/cv.json
TEMPLATE_DIR=src/template

AUX_FILES = $(TARGET).aux $(TARGET).log $(TARGET).synctex.gz $(TARGET).out \
            $(TARGET).toc $(TARGET).bbl $(TARGET).blg $(TARGET).fdb_latexmk $(TARGET).fls

.PHONY: all build check-latex clean cleanall force-build

all: check-latex build
force-build: cleanall all

build:
	@mkdir -p $(OUTDIR)
	@if [ ! -f $(HASH_FILE) ] || ! md5sum -c $(HASH_FILE) --status; then \
		echo "Running generator..."; \
		$(PYTHON) $(GENERATOR) --input $(INPUT_JSON) --output $(SOURCE) --template-dir $(TEMPLATE_DIR)  ; \
		echo "Detected change in cv.json. Compiling..."; \
		$(LATEX) $(SOURCE); \
		$(LATEX) $(SOURCE); \
		md5sum $(INPUT_JSON) > $(HASH_FILE); \
	else \
		echo "No changes in cv.json. Skipping compilation."; \
	fi

check-latex:
	@command -v pdflatex >/dev/null 2>&1 || { echo "Error: pdflatex is not installed."; exit 1; }

clean:
	@rm -f $(addprefix $(OUTDIR)/, $(AUX_FILES)) $(SOURCE)

cleanall: clean
	@rm -f $(OUTPUT) $(HASH_FILE)
