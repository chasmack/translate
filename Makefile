TRANSLATE := /home/charlie/dev/translate/
ACTIVATE := $(TRANSLATE).venv/bin/activate
UPDATE := $(TRANSLATE)src/update-vocab.py
VOCAB := $(TRANSLATE)src/anki-vocab.py
VOCAB_ARGS := --romanize --soundfile_prefix RT_VOCAB

export OAUTH2_CREDS = $(TRANSLATE)credentials/credentials.json
export OAUTH2_TOKEN = $(TRANSLATE)credentials/token.json

SRC_FILES := $(wildcard *.rus)
OUT_FILES = $(SRC_FILES:.rus=.txt)

all: $(OUT_FILES)

update:
	. $(ACTIVATE) && python $(UPDATE)

%.txt: %.rus
	. $(ACTIVATE) && python $(VOCAB) $< $@ $(VOCAB_ARGS)

show:
	@echo "Source files: $(SRC_FILES)"
	@echo "Output files: $(OUT_FILES)"
