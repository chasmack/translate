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
import html
import json
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
        default=None,
        description="The filename of the mp3 audio clip saved to the Anki media folder.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Supplemental information about usage of the Russian.",
    )


system_instruction = """
    You are a Russian linguistic expert. Process the provided JSON list of Russian words and phrases.

    RULES:
    1. PRIMARY CHECK: For each item, verify the spelling of 'russian'.
    2. IF MISSPELLED: 
       - Populate 'spelling_error' with a brief explanation.
       - You MUST leave 'stressed_russian', 'romanize', and 'english' unpopulated.
       - You MUST still echo the original 'russian' and 'section' fields.
    3. IF CORRECT:
       - Set 'spelling_error' to a JSON null.
       - STRESSED: Populate 'stressed_russian' using the combining acute accent (U+0301).
       - ROMANIZE: Use BGN/PCGN style (e.g., 'щ'->'shch', 'й'->'y', 'ё'->'yo', 'ь'->').
       - TRANSLATE: Provide the 'english' translation.
    4. ECHO: Always return the 'section' and 'russian' fields exactly as they were received.
"""


class APIConfigError(Exception):
    pass


def translate_text(
    texts,
    outfile,
    deckname,
    notetype,
    romanize=False,
    soundfile_prefix=None,
    soundfile_folder=None,
    soundfile_index=None,
):
    """Translate, romanize, and generate audio for a list of Russian texts."""

    # initialize the clients and request parameters

    try:
        with open(GEMINI_API_KEY, "r", encoding="utf-8") as f:
            api_key = f.read()
    except FileNotFoundError as e:
        raise APIConfigError(f"Error: API Key File '{GEMINI_API_KEY}' not found") from e
    except Exception as e:
        raise APIConfigError(f"Error: API Key File error: {e}") from e

    ai_client = genai.Client(api_key=api_key)

    tts_client = texttospeech.TextToSpeechClient()
    tts_voice = texttospeech.VoiceSelectionParams(
        language_code="ru-RU",
        name="ru-RU-Wavenet-A",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
    )
    tts_audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    if soundfile_prefix is not None:

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

    note_list = []
    for text in texts:

        # split out the section field
        text, section = text

        if romanize:
            note += f"{romanize_response.romanizations[0].romanized_text};"
        else:
            note += ";"

        if soundfile_prefix:

            # make the request to tts service
            tts_response = tts_client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=tts_voice,
                audio_config=tts_audio_config,
            )
            soundfile = f"{soundfile_prefix}-{soundfile_index:04}.mp3"
            with open(os.path.join(soundfile_folder, soundfile), mode="wb") as f:
                f.write(tts_response.audio_content)
            note += f"[sound:{soundfile}];"
            soundfile_index += 1
        else:
            note += ";"

        # translated response can return semicolon terminated html escape sequences
        note += f"{html.unescape(xlt_response.translations[0].translated_text)};"

        # initialize a new record with the deck name
        note = f"{deckname};"

        # add the Russian text
        note += f"{text};"

        # add an empty field for notes
        note += ";"

        # add the section field
        note += f"{section};"

        note_list.append(note)

    if len(note_list) > 0:
        with open(outfile, mode="wt", encoding="utf-8") as f:
            f.write(f"#separator:Semicolon\n")
            f.write(f"#notetype:{notetype}\n")
            f.write(f"#deck column:1\n")
            f.write("\n".join(note_list))

        print(f"{os.path.basename(outfile)}: {len(note_list)} Anki notes created.")


def main():
    """Parse arguments, read the input, and run the note generation process."""

    parser = argparse.ArgumentParser(
        description="Translate Russian words and phrases into English"
        " generating an Anki semicolon delimited note file, "
        " optionally adding romanized text and a sound clip of the Russian text"
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
        "--romanize",
        "-r",
        action="store_true",
        help="add romanized text to the record if available",
    )
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

    # build a list of words and phrases
    russian_texts = []
    with open(args.russian_textfile, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or len(line) == 0:
                continue
            for word in line.split(";"):
                russian_texts.append(word.strip())

    if len(russian_texts) == 0:
        print(f"{os.path.basename(args.russian_textfile)}: Nothing to do.")
        return

    # remove duplicates
    russian_texts = list(dict.fromkeys(russian_texts).keys())

    if args.verbose:
        print(args)
        print(russian_texts)

    translate_text(
        russian_texts,
        args.anki_outfile,
        deckname=args.anki_deck_name,
        notetype=args.anki_note_type,
        romanize=args.romanize,
        soundfile_prefix=args.soundfile_prefix,
        soundfile_folder=args.anki_media_folder,
        soundfile_index=args.soundfile_index,
    )


if __name__ == "__main__":

    main()
