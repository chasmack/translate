TRANSLATE := /home/charlie/dev/translate/
ACTIVATE := $(TRANSLATE).venv/bin/activate
ANKI := $(TRANSLATE)src/update_anki.py

export OAUTH2_CREDS = $(TRANSLATE)credentials/credentials.json
export OAUTH2_TOKEN = $(TRANSLATE)credentials/token.json

all: anki

anki:
	@. $(ACTIVATE) && python $(ANKI)

