"""
Module: anki_import_ai.py

Description:
    This module provides functionality to create Anki flashcard notes from a
    list of Russian words and phrases. It leverages the Google Gemini AI
    and Text-to-Speech (TTS) APIs to generate English translations, romanized
    representations, and audio clips for the Russian text. The output is a
    semicolon-delimited text file that can be directly imported into Anki.

Key Features:
    - Spelling: Russian spelling is checked and spelling errors are flagged.
    - Stressed Vowels: A copy of the Russian test is returned with accute
      accents (U+0301) on stressed vowels.
    - Translation: Uses the Google Gemini AI API to translate Russian
      text into English.
    - Romanization: Uses the Google Gemini AI API to generate a BGN/PCGN style
      romanized representation of the Russian text.
    - Text-to-Speech: Optionally uses the Google Cloud TTS API to
      create audio clips (MP3 files) of the Russian text.
    - Anki Note Generation: Creates semicolon-delimited records suitable for
      importing into Anki. Each record contains the following fields:
        - russian: The original Russian word or phrase.
        - stressed_russian: The original Russian with accute accents.
        - romanize: The romanized representation (if enabled).
        - audio: A link to the generated audio clip (if enabled).
        - english: The English translation.
        - notes: An empty field for additional notes.
        - section: An optional category for the input texts.
    - Sound File Management: Saves generated audio clips to a specified
      directory (defaulting to the Anki media folder). Automatically manages
      sound file names with a prefix and numerical index.
    - Duplicate Handling: Removes duplicate Russian words/phrases from the input.
    - Command-Line Interface: Provides a command-line interface for easy
      configuration and execution.

Dependencies:
    - google-genai
    - google-cloud-texttospeech
    - pydantic
    - typing
    - html
    - json
    - os
    - re
    - glob
    - argparse

Usage:
    1.  Prepare a text file with Russian words and phrases, one per line.
    2.  Run the script from the command line, providing the input file, output
        file, and any desired options (romanization, sound file generation,
        media folder, etc.).

    Example:
        python anki-vocab.py russian_words.txt anki_notes.txt \
            -r -p vocab -m /path/to/anki/media

    -   `russian_words.txt`: Input file with Russian words/phrases.
    -   `anki_notes.txt`: Output file for Anki notes.
    -   `-r`: Enable romanization.
    -   `-p vocab`: Enable sound file generation and use the sound file prefix "vocab".
    -   `-m /path/to/anki/media`: Specify the Anki media folder for sound files.

Functions:
    - translate_text(texts, outfile, romanize, soundfile_folder,
            soundfile_prefix, soundfile_index):
        Translates, romanizes, and generates audio for a list of Russian texts.
        Creates the Anki note file.
    - main():
        Parses command-line arguments, reads the input file, and orchestrates
        the overall process.

Notes:
    - The script assumes that the Google Cloud project is properly configured
      with the necessary APIs enabled and credentials set up.
    - The default Anki media folder is set to a common location, but can be
      overridden with the `-m` option.
    - The script will automatically determine the next available index for
      sound files if no index is provided. If an index is provided the new
      sound files can potentially overwrite existing sound files in the Anki
      media folder.
    - The Anki note type is set to "RT Vocab" using the text file import header.
    - The script will create the sound files in the specified media folder.
"""

import os
import re
import glob
import argparse
import traceback
import time
import json
import unicodedata
from pydantic import BaseModel, Field
from typing import List, Optional

# Google Gemini AI and Text-to-Speech libraries
from google import genai
from google.cloud import texttospeech

# Google Cloud project ID for authorization
PROJECT_ID = "first-gc-tts-project"
PROJECT_PARENT = f"projects/{PROJECT_ID}/locations/global"

# The default Anki media folder. Override with -m option
ANKI_MEDIA_FOLDER = "/home/charlie/.local/share/Anki2/Charlie/collection.media"

# Location og the API key and name of the Gemini AI model
GEMINI_API_KEY = "/home/charlie/dev/translate/credentials/gemini_translate_key.txt"
GEMINI_AI_MODEL = "gemini-2.5-pro"
GEMINI_INPUT_CHUNK_SIZE = 25

DEBUG = False


# Data schema for the Anki base note. Only fields required for AI processing
# are included here to keep down clutter that could confule the AI.
# The stressed_russian, romanize and english fields are optional. If a spelling
# error is detected Gemini is requested to leave these fields unpopulated.
class AnkiBaseNote(BaseModel):
    russian: str = Field(
        description="The original unmodified russian text provided in the input."
    )
    section: str = Field(
        description="Copy of the unmodified section name provided in the input.",
    )
    stressed_russian: Optional[str] = Field(
        default=None,
        description="The russian text input with acute accents on stressed vowels.",
    )
    romanize: Optional[str] = Field(
        default=None, description="Latin transliteration using the BGN/PCGN system."
    )
    english: Optional[str] = Field(
        default=None, description="The English translation of the russian text."
    )
    spelling_error: Optional[str] = Field(
        default=None,
        description="If a spelling error is detected in russian text, describe it. Otherwise, null.",
    )


# A list of Anki base notes for JSON schema defination and return data validation
class AnkiNoteList(BaseModel):
    notes: List[AnkiBaseNote]


# Model for the full Anki note type.
class AnkiNote(AnkiBaseNote):
    audio: Optional[str] = Field(
        default="",
        description="The filename of the mp3 audio clip saved to the Anki media folder.",
    )
    notes: Optional[str] = Field(
        default="",
        description="Supplemental information about usage of the Russian.",
    )


# The System Instruction is provided to Gemini with each request to guide its response.
# It should be concise yet thoroughly explain what is expected from the processing.
# Unfortunately, since we are dealing with a probabilistic process subject to stochastic
# drift, strict adherence to the system instruction is not guaranteed.
#
# For example, though the system instruction requested U+0301 combining accents Gemini
# still managed to generate an NFC (Canonical Composition) accented "a". Subsequent
# addition of an explicit NFD requirement may or may not change Gemini's behavior.
# Any system utilizing this probabilistic output needs to guard against these misbehaviors.

system_instruction = """
Role: Russian Linguist.
COMMANDS:
  CHECK: Verify russian spelling and case. Ignore capitalization and punctuation.
  BYPASS: If section == "Nonstandard Spelling", ignore errors; process as CORRECT.
  FORMAT: Specified JSON data schema. Do not use semicolons in generated content.
If CORRECT or BYPASS:
  spelling_error: null
  stressed_russian: Add NFD accute accent U+0301 to stressed vowels except single-syllable words. \
Do not add accute accent to words containing the Russian letter ё (yo).
  romanize: Use BGN/PCGN.
  english: Translate. Minimize extra commentary.
If MISSPELLED:
  spelling_error: Brief explanation.
  stressed_russian, romanize, english: null
ECHO: Always return original russian and section.
"""


class APIConfigError(Exception):
    pass


class InputTextSpellingError(Exception):
    pass


def translate_text(
    texts,
    outfile,
    deckname,
    notetype,
    soundfile_prefix=None,
    soundfile_folder=None,
    soundfile_index=None,
):
    """Translate, romanize, and generate audio for a list of Russian texts."""

    # Get the API key from the key file and initialize the Gemini client.
    try:
        with open(GEMINI_API_KEY, "r", encoding="utf-8") as f:
            api_key = f.read()
    except FileNotFoundError as e:
        raise APIConfigError(f"Error: API Key File '{GEMINI_API_KEY}' not found") from e
    except Exception as e:
        raise APIConfigError(f"Error: API Key File error: {e}") from e

    ai_client = genai.Client(api_key=api_key)

    # Initialize the TTS client and request parameters.
    if soundfile_prefix is not None:

        tts_client = texttospeech.TextToSpeechClient()
        tts_voice = texttospeech.VoiceSelectionParams(
            language_code="ru-RU",
            name="ru-RU-Wavenet-A",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )
        tts_audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )

        # Anki media folder for sound files
        if soundfile_folder is None:
            soundfile_folder = ANKI_MEDIA_FOLDER

        # initialize the soundfile index
        if soundfile_index is None:

            # locate the next available soundfile index
            index = 1
            pattern = os.path.join(soundfile_folder, f"{soundfile_prefix}-*")
            for f in glob.glob(pattern):
                i = re.sub(
                    r".*-(\d+)\.mp3$", r"\1", os.path.basename(f), flags=re.IGNORECASE
                )
                if not i.isdigit():
                    continue
                i = int(i)
                if i >= index:
                    index = i + 1
            soundfile_index = index

    if DEBUG:
        print(f"Number of texts to process: {len(texts)}")
        print(f"Texts: {texts}\n")

    # A list to accumulate processed note data.
    notes = []

    # A list to aqccumulate spelling errors returned by Gemini.
    spelling_errors = []

    # JSON keys for the request data
    request_keys = ["russian", "section"]

    # First process all input texts through Gemini to generate
    # translation/transliteration and check for spelling errors.

    # We break the list of Russian texts into smaller chunks in order
    # to reduce the potential of AI stochastic drift.
    for i in range(0, len(texts), GEMINI_INPUT_CHUNK_SIZE):

        request_data = texts[i : i + GEMINI_INPUT_CHUNK_SIZE]
        request_data = [dict(zip(request_keys, values)) for values in request_data]

        request_prompt = (
            f"Process these Russian texts according to the schema: "
            + json.dumps(request_data, ensure_ascii=False)
        )

        if DEBUG:
            print(f"Request size: {len(request_data)}")
            print(f"Request data: {request_data}\n")
            print(f"Request prompt:\n{request_prompt}\n")

        nreqs = len(request_data)
        print(f"Request size: {nreqs} {'text' if nreqs == 1 else 'texts'}")
        start_time = time.perf_counter()
        response = ai_client.models.generate_content(
            model=GEMINI_AI_MODEL,
            contents=request_prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": AnkiNoteList.model_json_schema(),
                "system_instruction": system_instruction,
            },
        )
        end_time = time.perf_counter()
        print(f"Done: {(end_time - start_time):.2f} secs")

        if DEBUG:
            print(
                f"Response: {json.dumps(json.loads(response.text), ensure_ascii=False, indent=2)}\n"
            )

        # Validate Gemini response, check for spelling errors and
        # promote records to full AnkiNote data model.
        for note in AnkiNoteList.model_validate_json(response.text).notes:

            # Ensure spelling_error and data fields are mutually exclusive
            for field in [note.stressed_russian, note.romanize, note.english]:
                assert (note.spelling_error is None) != (
                    field is None
                ), f"AI data error: 'spelling_error' and '{field}': {note}"

            if note.spelling_error is not None:
                spelling_errors.append(
                    f'-- {note.section}: "{note.russian}" -- {note.spelling_error}'
                )

            notes.append(AnkiNote(**note.model_dump()))

    # If spelling errors were detected we pass an exception up to the caller.
    if spelling_errors:
        raise InputTextSpellingError("\n".join(spelling_errors))

    if len(notes) > 0:
        if soundfile_prefix:
            print(f"Creating audio clips.")
            start_time = time.perf_counter()
            for note in notes:

                # TTS expects the NFD decomposed form of accented characters.
                # Use the NFD stressed Russian for the TTS request.
                # text = unicodedata.normalize("NFD", note.stressed_russian)

                # Use of the stressed_russian can lcause TTS to generate unnatural
                # stress patterns. Where necessary (homograms) stress can be included
                # in the Russian source but in general TTS should be allowed to use
                # its native stress patterns.
                text = note.russian

                tts_response = tts_client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=text),
                    voice=tts_voice,
                    audio_config=tts_audio_config,
                )
                soundfile = f"{soundfile_prefix}-{soundfile_index:04}.mp3"
                with open(os.path.join(soundfile_folder, soundfile), mode="wb") as f:
                    f.write(tts_response.audio_content)

                note.audio = f"[sound:{soundfile}]"
                soundfile_index += 1

            end_time = time.perf_counter()
            print(f"Done: {(end_time - start_time):.2f} secs")

        with open(outfile, mode="wt", encoding="utf-8") as f:

            # Write the file headers.
            f.write(f"#separator:Semicolon\n")
            f.write(f"#notetype:{notetype}\n")
            f.write(f"#deck column:1\n")

            # Write the note data.
            for note in notes:

                # Initialize a new Anki text import record. The note fields are -
                # russian; stressed russian; romanize; audio; english; section; notes;

                # First column is the deck naame per the #deck column header
                rec = f"{deckname};"

                # Add the note data
                rec += f"{note.russian};{note.stressed_russian};"
                rec += f"{note.romanize};{note.audio};{note.english};"
                rec += f"{note.section};{note.notes};"

                # Write the note record.
                f.write(f"{rec}\n")


def main():
    """Parse arguments, read the input, and run the note generation process."""

    parser = argparse.ArgumentParser(
        description="Translate Russian words and phrases into English"
        " generating an Anki semicolon delimited text import file, "
        " optionally adding a sound clip of the Russian text"
    )
    parser.add_argument(
        "russian_textfile",
        help="comma separated list of Russian words and phrases " "to be translated",
    )
    parser.add_argument(
        "anki_outfile", help="semicolon delimited note file for Anki text import"
    )
    parser.add_argument(
        "--anki_deck_name", "-d", required=True, help="full deck name including parent"
    )
    parser.add_argument("--anki_note_type", "-n", required=True, help="note type")
    parser.add_argument(
        "--anki_media_folder", "-m", help="alternate media folder for sound files"
    )
    parser.add_argument(
        "--soundfile_prefix",
        "-p",
        help="alphanumeric prefix used to generate soundfile names "
        "(omission: disable soundfile creation)",
    )
    parser.add_argument(
        "--soundfile_index",
        "-i",
        type=int,
        help="numeric index used for soundfile names "
        "(default: next available index)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="increase diagnostic output"
    )
    args = parser.parse_args()

    # Build a list of words and phrases
    texts = []

    # Section names added to each text
    section = ""

    with open(args.russian_textfile, "r") as f:
        for line in f:

            line = line.strip()
            if len(line) == 0:
                continue
            if line.startswith("#"):
                section = line[1:].strip()
                continue

            # split line at semicolons
            for text in line.split(";"):
                # watch for blank words
                text = text.strip()
                if len(text) > 0:
                    texts.append((text, section))

    if len(texts) == 0:
        print(f"{os.path.basename(args.russian_textfile)}: Nothing to do.")
        return

    # remove duplicates
    texts = list(dict.fromkeys(texts).keys())

    if args.verbose:
        print(args)
        print(texts)

    try:
        translate_text(
            texts,
            args.anki_outfile,
            deckname=args.anki_deck_name,
            notetype=args.anki_note_type,
            soundfile_prefix=args.soundfile_prefix,
            soundfile_folder=args.anki_media_folder,
            soundfile_index=args.soundfile_index,
        )

    except APIConfigError as e:
        print(f"Gemini API Configuration Error: {e}")

    except InputTextSpellingError as e:
        print(f"Spelling Errors:\n{e}")

    except Exception as e:
        traceback.print_exc()


if __name__ == "__main__":

    main()
