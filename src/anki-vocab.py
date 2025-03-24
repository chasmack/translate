# anki-vocab.py - Create Anki notes from russian word lists.
#
# The input text file consists of Russian words and phrases to be translated.
# Each line can have one word and phrase. Blank lines and lines starting with 
# hash (#) are ignored.
#
# The output file is a semicolon delimited text file compatible with
# Anki text import.
#
# The Anki note records have following fields -
#
#   Russian - the Russian word or phrase to be translated from the input file
#   Romanize - a romanized representation of the Russian by Translate
#   Audio - an MP3 sound clip of the Russian by Text-to-Speech
#   English - an English translation of the Russian generated by Translate
#   Notes - additional translation/usage information not populated by this app
#
# Sound files are saved to the ANKI_MEDIA_FOLDER. A sound filename prefix
# is specified on the command line. A numerical index is added to the sound filename.

import os
import re
import glob
import argparse

# Google Cloud Translation and Text-to-Speech libraries
from google.cloud import translate_v3 as translate
from google.cloud import texttospeech

# Google Cloud project ID for authorization
PROJECT_ID = "first-gc-tts-project"
PROJECT_PARENT = f"projects/{PROJECT_ID}/locations/global"

# The default Anki media folder. Override with -m option
ANKI_MEDIA_FOLDER = '/home/charlie/.local/share/Anki2/Charlie/collection.media'


def translate_text(texts, outfile, romanize, 
                   soundfile_folder, soundfile_prefix, soundfile_index):

    # initialize the clients and request parameters
    xlt_client = translate.TranslationServiceClient()

    tts_client = texttospeech.TextToSpeechClient()
    tts_voice = texttospeech.VoiceSelectionParams(
        language_code='ru-RU',
        name='ru-RU-Wavenet-A',
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
    )
    tts_audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    records = []
    for text in texts:

        # initialize a new record with the Russian text
        record = f"{text};"

        if romanize:
            # generate romanized text
            romanize_request = translate.RomanizeTextRequest(
                contents=[text],
                source_language_code='ru',
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
                audio_config=tts_audio_config
            )
            soundfile = f"{soundfile_prefix}-{soundfile_index:04}.mp3"
            with open(os.path.join(soundfile_folder, soundfile), mode='wb') as f:
                f.write(tts_response.audio_content)
            record += f"[sound:{soundfile}];"
            soundfile_index += 1
        else:
            record += ";"

        # make the translation request
        xlt_request = translate.TranslateTextRequest(
            contents=[text],
            source_language_code='ru',
            target_language_code='en-US',
            parent=PROJECT_PARENT,
        )
        xlt_response = xlt_client.translate_text(request=xlt_request)
        record += f"{xlt_response.translations[0].translated_text};"

        # add an empty field for Notes
        record += ";"

        records.append(record)

    with open(outfile, mode='wt', encoding='utf-8') as f:
        f.write('\n'.join(records))

    print(f"{len(records)} Anki note records created.")


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description="Translate Russian words and phrases into English"
                    " generating an Anki semicolon delimited note file, "
                    " optionally adding romanized text and a sound clip of the Russian text"
    )
    parser.add_argument("russian_textfile",
                        help="comma separated list of Russian words and phrases "
                             "to be translated")
    parser.add_argument("anki_outfile",
                        help="semicolon delimited note file for Anki text import")
    parser.add_argument("--romanize", "-r", action="store_true",
                        help="add romanized text to the record if available")
    parser.add_argument("--anki_media_folder", "-m",
                        help="alternate media folder for sound files")
    parser.add_argument("--soundfile_prefix", "-p",
                        help="alphanumeric prefix used to generate soundfile names "
                             "(omission: disable soundfile creation)")
    parser.add_argument("--soundfile_index", "-i", type=int,
                        help="numeric index used for soundfile names "
                             "(default: next available index)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="increase diagnostic output")
    args = parser.parse_args()

    # build a list of words and phrases
    russian_texts = []
    with open(args.russian_textfile, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or len(line) == 0:
                continue
            russian_texts.append(line)

    # remove duplicates
    russian_texts = list(dict.fromkeys(russian_texts).keys())

    # Anki media folder for sound files
    if args.anki_media_folder is None:
        args.anki_media_folder = ANKI_MEDIA_FOLDER

    # initialize the soundfile index
    if args.soundfile_prefix is not None and args.soundfile_index is None:

        # locate the next available soundfile index
        index = 1
        pattern = os.path.join(args.anki_media_folder,
                               f"{args.soundfile_prefix}-*")
        for f in glob.glob(pattern):
            i = re.sub(r'.*-(\d+)\.mp3$', r'\1', os.path.basename(f),
                       flags=re.IGNORECASE)
            if not i.isdigit():
                continue
            i = int(i)
            if i >= index:
                index = i + 1
        args.soundfile_index = index

    if args.verbose:
        print(args)
        print(russian_texts)

    translate_text(texts=russian_texts,
                   outfile=args.anki_outfile,
                   romanize=args.romanize,
                   soundfile_folder=args.anki_media_folder,
                   soundfile_prefix=args.soundfile_prefix,
                   soundfile_index=args.soundfile_index)
