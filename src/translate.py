import sys, os, glob, re, argparse

# Imports the Google Cloud Translation library
from google.cloud import translate_v3 as translate
from google.cloud import texttospeech

PROJECT_ID = "first-gc-tts-project"
PROJECT_PARENT = f"projects/{PROJECT_ID}/locations/global"
ANKI_MEDIA_FOLDER = '/home/charlie/.local/share/Anki2/Charlie/collection.media'

# Translate Russian words and phrases to English.

def translate_text(russian_texts, anki_outfile, romanize, soundfile_prefix, soundfile_index):

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

    card_count = 0
    with open(anki_outfile, "w") as results:
        for text in russian_texts:

            # initialize a new semicolon delimited result string with russian text
            result = f"{text};"

            if romanize:
                # generate romanized text
                romanize_request = translate.RomanizeTextRequest(
                    contents=[text],
                    source_language_code='ru',
                    parent=PROJECT_PARENT,
                )
                romanize_response = xlt_client.romanize_text(request=romanize_request)
                result += f"{romanize_response.romanizations[0].romanized_text};"

            else:
                result += ";"

            if soundfile_prefix:

                # make the request to tts service
                tts_response = tts_client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=text),
                    voice=tts_voice,
                    audio_config=tts_audio_config
                )
                soundfile = f"{soundfile_prefix}-{soundfile_index:04}.mp3"
                with open(os.path.join(ANKI_MEDIA_FOLDER, soundfile), "wb") as f:
                    f.write(tts_response.audio_content)
                result += f"[sound:{soundfile}];"
                soundfile_index += 1

            else:
                result += ";"

            # make the translation request
            xlt_request = translate.TranslateTextRequest(
                contents=[text],
                source_language_code='ru',
                target_language_code='en-US',
                parent=PROJECT_PARENT,
            )
            xlt_response = xlt_client.translate_text(request=xlt_request)
            result += f"{xlt_response.translations[0].translated_text};"

            # add an empty field for Notes and complete the record
            result += ";\n"
            results.write(result)
            card_count += 1

    print(f"{card_count} Anki note records created.")


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description="Translate Russian words and phrases into English"
                    " generating an Anki semicolon delimited note file, "
                    " optionally adding romanized text and a sound clip of the Russian text"
    )
    parser.add_argument("russian_textfile",
                        help="comma separated list of Russian words and phrases to be translated")
    parser.add_argument("anki_outfile",
                        help="semicolon delimited note file for Anki text import")
    parser.add_argument("--romanize", "-r", action="store_true",
                        help="add romanized text to the record if available")
    parser.add_argument("--soundfile_prefix", "-s",
                        help="alphanumeric prefix used to generate soundfile names (omission: disable soundfile creation)")
    parser.add_argument("--soundfile_index", "-i", type=int,
                        help="numeric index used for soundfile names (default: next available index)")
    args = parser.parse_args()

    # build a list of words and phrases from comma delimited Russian text
    russian_texts = []
    with open(args.russian_textfile, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#'):
                continue
            for text in line.split(','):
                russian_texts.append(text.strip())

    # remove duplicates
    russian_texts = list(dict.fromkeys(russian_texts).keys())

    # initialize the soundfile index from the command line

    if args.soundfile_prefix is not None and args.soundfile_index is None:

        # locate the next available soundfile index
        index = 1
        pattern = os.path.join(ANKI_MEDIA_FOLDER, f"{args.soundfile_prefix}-*")
        for f in glob.glob(pattern):
            i = re.sub(r'.*-(\d+)\.mp3$', r'\1', os.path.basename(f), flags=re.IGNORECASE)
            if not i.isdigit():
                continue
            i = int(i)
            if i >= index:
                index = i + 1
        args.soundfile_index = index

    # print(args)
    translate_text(russian_texts=russian_texts,
                   anki_outfile=args.anki_outfile,
                   romanize=args.romanize,
                   soundfile_prefix=args.soundfile_prefix,
                   soundfile_index=args.soundfile_index)
