TRANSLATE := /home/charlie/dev/translate/
VENV := $(TRANSLATE).venv/
VOCAB := $(TRANSLATE)src/anki-vocab.py
ARGS := --romanize --soundfile_prefix RT_VOCAB

SRC_FILES := $(wildcard *.rus)

OUT_FILES = $(SRC_FILES:.rus=.txt)

all: $(OUT_FILES)

%.txt: %.rus
	. $(VENV)bin/activate; python $(VOCAB) $< $@ $(ARGS)

show:
	@echo "Source files: $(SRC_FILES)"
	@echo "Output files: $(OUT_FILES)"
