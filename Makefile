TARGET = cv
SOURCE = $(TARGET).tex
GENERATED_PREFIX = $(TARGET)_gen
GENERATED = $(GENERATED_PREFIX).tex
OUTPUT = $(TARGET).pdf
HASH_FILE = .cv.json.md5

LATEX = pdflatex -synctex=1 -interaction=nonstopmode

.PHONY: all build check-latex clean cleanall

all: check-latex build
force-build: cleanall all

build:
	@echo "Running generator..."
	python generate_cv.py
	@if [ ! -f $(HASH_FILE) ] || ! md5sum -c $(HASH_FILE) --status; then \
		python generate_cv.py \
		echo "Detected change in cv.json. Compiling..."; \
		$(LATEX) $(SOURCE); \
		$(LATEX) $(SOURCE); \
		md5sum cv.json > $(HASH_FILE); \
		rm -f $(TARGET).aux $(TARGET).log $(TARGET).synctex.gz; \
	else \
		echo "No changes in cv.json. Skipping compilation."; \
	fi

check-latex:
	@command -v pdflatex >/dev/null 2>&1 || { echo "Error: pdflatex is not installed."; exit 1; }

clean:
	rm -f $(TARGET).aux $(TARGET).log $(TARGET).synctex.gz $(TARGET).out $(TARGET).toc \
	      $(TARGET).bbl $(TARGET).blg $(TARGET).fdb_latexmk $(TARGET).fls \
	      $(GENERATED) $(SOURCE)

cleanall: clean
	rm -f $(OUTPUT) $(HASH_FILE)
