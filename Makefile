TRANSLATE := /home/charlie/dev/translate/
VENV := $(TRANSLATE).venv/
VOCAB := $(TRANSLATE)src/vocab.py
ARGS := --speaking_rate 0.85 --pitch -2 --volume_gain_db +3

srcfiles := $(wildcard *.txt)
mp3files := $(srcfiles:.txt=.mp3)

all: $(mp3files)

%.mp3: %.txt
	. $(VENV)bin/activate; python $(VOCAB) $< $@ $(ARGS)
