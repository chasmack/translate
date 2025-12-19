"""
Module: anki_import_ai.py

Description:
    This module provides functionality to create Anki flashcard notes from a
    list of Russian words and phrases. It leverages the Google Cloud Translation
    and Text-to-Speech APIs to generate English translations, romanized
    representations, and audio clips for the Russian text. The output is a
    semicolon-delimited text file that can be directly imported into Anki.

Key Features:
    - Input Processing: Reads a text file containing Russian words and phrases,
      one per line. Ignores blank lines and lines starting with '#'.
    - Translation: Uses the Google Cloud Translation API to translate Russian
      text into English.
    - Romanization: Optionally uses the Google Cloud Translation API to
      generate a romanized representation of the Russian text.
    - Text-to-Speech: Optionally uses the Google Cloud Text-to-Speech API to
      create audio clips (MP3 files) of the Russian text.
    - Anki Note Generation: Creates semicolon-delimited records suitable for
      importing into Anki. Each record contains the following fields:
        - Russian: The original Russian word or phrase.
        - Romanize: The romanized representation (if enabled).
        - Audio: A link to the generated audio clip (if enabled).
        - English: The English translation.
        - Notes: An empty field for additional notes.
    - Sound File Management: Saves generated audio clips to a specified
      directory (defaulting to the Anki media folder). Automatically manages
      sound file names with a prefix and numerical index.
    - Duplicate Handling: Removes duplicate Russian words/phrases from the input.
    - Command-Line Interface: Provides a command-line interface for easy
      configuration and execution.

Dependencies:
    - google-cloud-translate
    - google-cloud-texttospeech
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

# Google Cloud Translation and Text-to-Speech libraries
from google.cloud import translate_v3 as translate
from google.cloud import texttospeech

# Google Cloud project ID for authorization
PROJECT_ID = "first-gc-tts-project"
PROJECT_PARENT = f"projects/{PROJECT_ID}/locations/global"

# The default Anki media folder. Override with -m option
ANKI_MEDIA_FOLDER = "/home/charlie/.local/share/Anki2/Charlie/collection.media"


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
    xlt_client = translate.TranslationServiceClient()

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

    records = []
    for text in texts:

        # split out the section field
        text, section = text

        # initialize a new record with the deck name
        record = f"{deckname};"

        # add the Russian text
        record += f"{text};"

        if romanize:
            # generate romanized text
            romanize_request = translate.RomanizeTextRequest(
                contents=[text],
                source_language_code="ru",
                parent=PROJECT_PARENT,
            )
            romanize_response = xlt_client.romanize_text(request=romanize_request)
            record += f"{romanize_response.romanizations[0].romanized_text};"
        else:
            record += ";"

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
            record += f"[sound:{soundfile}];"
            soundfile_index += 1
        else:
            record += ";"

        # make the translation request
        xlt_request = translate.TranslateTextRequest(
            contents=[text],
            source_language_code="ru",
            target_language_code="en-US",
            parent=PROJECT_PARENT,
        )
        xlt_response = xlt_client.translate_text(request=xlt_request)
        # translated response can return semicolon terminated html escape sequences
        record += f"{html.unescape(xlt_response.translations[0].translated_text)};"

        # add an empty field for notes
        record += ";"

        # add the section field
        record += f"{section};"

        records.append(record)

    if len(records) > 0:
        with open(outfile, mode="wt", encoding="utf-8") as f:
            f.write(f"#separator:Semicolon\n")
            f.write(f"#notetype:{notetype}\n")
            f.write(f"#deck column:1\n")
            f.write("\n".join(records))

        print(f"{os.path.basename(outfile)}: {len(records)} Anki notes created.")


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
