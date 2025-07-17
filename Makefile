
TARGET = cv
SOURCE = $(TARGET).tex
GENERATED_PREFIX = $(TARGET)_gen
GENERATED = $(GENERATED_PREFIX).tex
OUTPUT = $(TARGET).pdf
HASH_FILE = .$(TARGET).tex.md5

LATEX = pdflatex -synctex=1 -interaction=nonstopmode
DATE = $(shell date +'%Y-%m-%d')

.PHONY: all build check-latex clean cleanall

all: check-latex build

build:
	@if [ ! -f $(HASH_FILE) ] || ! md5sum -c $(HASH_FILE) --status; then \
		echo "Detected change in $(SOURCE). Injecting date and compiling..."; \
		sed 's/\$$LAST_UPDATED\$$/$(DATE)/' $(SOURCE) > $(GENERATED); \
		$(LATEX) $(GENERATED); \
		$(LATEX) $(GENERATED); \
		mv $(TARGET)_gen.pdf $(OUTPUT); \
		md5sum $(SOURCE) > $(HASH_FILE); \
		rm $(GENERATED_PREFIX).*; \
	else \
		echo "No changes in $(SOURCE). Skipping compilation."; \
	fi

check-latex:
	@command -v pdflatex >/dev/null 2>&1 || { echo "Error: pdflatex is not installed."; exit 1; }

clean:
	rm -f $(TARGET).aux $(TARGET).log $(TARGET).synctex.gz $(TARGET).out $(TARGET).toc \
	      $(TARGET).bbl $(TARGET).blg $(TARGET).fdb_latexmk $(TARGET).fls \
	      $(GENERATED)

cleanall: clean
	rm -f $(OUTPUT) $(HASH_FILE)
