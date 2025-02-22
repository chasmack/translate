# vocab.py - Translate Russian words and phrases to English and
# create an audio vocabulary lesson.
#

import os
import argparse
import xml.etree.ElementTree as ET
import subprocess

# Google Cloud Translation and Text-to-Speech libraries
from google.cloud import translate_v3 as translate
from google.cloud import texttospeech

# Google Cloud project ID for authorization
PROJECT_ID = "first-gc-tts-project"
PROJECT_PARENT = f"projects/{PROJECT_ID}/locations/global"

# Audio player
MPV_EXEC = ['/usr/bin/mpv', '-', '--really-quiet']

# Default voice names
VOICE_RUSSIAN_A = "ru-RU-Wavenet-A"
VOICE_RUSSIAN_B = "ru-RU-Wavenet-B"
VOICE_ENGLISH = "en-US-Standard-C"

# Delays between media elements
MEDIA_START_DELAY_RUSSIAN_A = '1200ms'
MEDIA_START_DELAY_RUSSIAN_B = '650ms'
MEDIA_START_DELAY_ENGLISH = '1200ms'

def make_lesson(args):

    # Get the list of russian words and phrases
    texts = []
    with open(args.textfile, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or len(line) == 0:
                continue
            texts += [s.strip() for s in  line.split(',')]

    # Remove duplicates
    texts = list(dict.fromkeys(texts).keys())

    # Voices for use in the ssml
    voice_russian_a = args.voice_russian_a if args.voice_russian_a else VOICE_RUSSIAN_A
    voice_russian_b = args.voice_russian_b if args.voice_russian_b else VOICE_RUSSIAN_B
    voice_english = args.voice_english if args.voice_english else VOICE_ENGLISH

    # Initialize the clients and the request parameters
    xlt_client = translate.TranslationServiceClient()
    tts_client = texttospeech.TextToSpeechClient()

    # Voice selection parameters
    voice_params = {
        'language_code': 'ru-RU',
        'name': voice_russian_a
    }

    voice_select = texttospeech.VoiceSelectionParams(mapping=voice_params)

    if args.verbose:
        print(f'Voice Select:\n{voice_select}')

    # Audio configuration parameters
    config_params = {
        'speaking_rate': args.speaking_rate,
        'pitch': args.pitch,
    }

    if args.outfile == '-':
        # Generate an mp3 file for the mpv player
        config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
    else:
        match os.path.splitext(args.outfile)[1].upper():
            case '.MP3':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
            case '.WAV':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.LINEAR16
            case '.OGG':
                config_params['audio_encoding'] = texttospeech.AudioEncoding.OGG_OPUS
            case _:
                raise ValueError(f"Invalid encoding format: {args.outfile}")

    audio_config = texttospeech.AudioConfig(mapping=config_params)

    if args.verbose:
        print(f'Audio Config:\n{audio_config}')

    # Make the translation request
    xlt_params = {
        'contents': texts,
        'source_language_code': 'ru',
        'target_language_code': 'en-US',
        'parent': PROJECT_PARENT,
    }
    request = translate.TranslateTextRequest(mapping=xlt_params)
    response = xlt_client.translate_text(request=request)
    texts = list(zip(texts, [t.translated_text for t in response.translations]))

    if args.verbose:
        print('Translations:')
        for rus, eng in texts:
            print(f"{rus} => {eng}")
        print('\n')

    # Create three media elements for each word/phrase
    # to synthesize Russian in voices A and B and English.
    # Media elements take the form -
    #
    # <media xml:id="rus-01a" begin="1000ms">
    #   <speak>
    #     <voice name="ru-RU-Wavenet-B">
    #       Медведь
    #     </voice>
    #   </speak>
    # </media>

     # Initialize the XML root elements
    root = ET.Element('speak')
    seq = ET.SubElement(root, 'seq')

    for i in range(len(texts)):
        rus, eng = texts[i]

        # Russian A media element
        media = ET.Element('media',
                          attrib={
                              'xml:id': f'rus{i:02}a',
                              'begin': MEDIA_START_DELAY_RUSSIAN_A,
                          })
        speak = ET.SubElement(media, 'speak')
        voice = ET.SubElement(speak, 'voice',
                                attrib={'name': VOICE_RUSSIAN_A})
        voice.text = rus
        seq.append(media)

        # Russian B media element
        media = ET.Element('media',
                          attrib={
                              'xml:id': f'rus{i:02}b',
                              'begin': f'rus{i:02}a.end+{MEDIA_START_DELAY_RUSSIAN_B}',
                          })
        speak = ET.SubElement(media, 'speak')
        voice = ET.SubElement(speak, 'voice',
                                attrib={'name': VOICE_RUSSIAN_B})
        voice.text = rus
        seq.append(media)

        # English translation media element
        media = ET.Element('media',
                          attrib={
                              'xml:id': f'eng{i:02}',
                              'begin': f'rus{i:02}b.end+{MEDIA_START_DELAY_ENGLISH}',
                          })
        speak = ET.SubElement(media, 'speak')
        voice = ET.SubElement(speak, 'voice',
                                attrib={'name': VOICE_ENGLISH})
        voice.text = eng
        seq.append(media)

    if args.verbose:
        ET.indent(root, space="  ")

    xml = ET.tostring(root,
                      encoding='unicode',
                      method='xml',
                      xml_declaration=True)

    if args.verbose:
        print(xml + '\n')

    response = tts_client.synthesize_speech(
        input=texttospeech.SynthesisInput(mapping={'ssml': xml}),
        voice=voice_select,
        audio_config=audio_config,)

    if args.outfile == '-':
        # pipe data to the mpv player
        proc = subprocess.Popen(MPV_EXEC,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)

        print("Playing results... ", end='', flush=True)
        stderr = proc.communicate(input=response.audio_content)[1]
        print("done.")

        if stderr:
            print(f"Error: {stderr.decode('utf-8')}")

    else:
        with open(args.outfile, mode='wb') as f:
            f.write(response.audio_content)

        print("Done.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Generate Russian vocabulary lesson")

    # Required arguments
    parser.add_argument("textfile", help="Russian words and phrases")
    parser.add_argument("outfile", help="audio output file or '-' to send output to player")

    # Options
    parser.add_argument("--voice_russian_a", help="name of the first Russian voice")
    parser.add_argument("--voice_russian_b", help="name of the second Russian voice")
    parser.add_argument("--voice_english", help="name of the English voice")
    parser.add_argument("--speaking_rate", type=float,
                        help="speaking rates between 0.25 and 4.0")
    parser.add_argument("--pitch", type=float,
                        help="speaking pitch between 20.0 and -20.0 (semitones)")

    # Debugging
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="increase diagnostic output")
    args = parser.parse_args()

    if args.verbose:
        print(f'\nCommand line arguments:\n{args}\n')

    make_lesson(args)


