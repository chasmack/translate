#
# vocab.py - Translate Russian words and phrases to English and
# create an audio vocabulary lesson.
#

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
BREAK_RUSSIAN_A = '650ms'
BREAK_RUSSIAN_B = '1200ms'
BREAK_ENGLISH = '1500ms'


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

    # Initialize the clients and the request parameters
    xlt_client = translate.TranslationServiceClient()
    tts_client = texttospeech.TextToSpeechClient()

    # Voice selection parameters. Actual voice names are set in the SSML.
    voice_params = {'language_code': 'ru-RU'}
    voice_select = texttospeech.VoiceSelectionParams(mapping=voice_params)

    if args.verbose:
        print(f'Voice Select:\n{voice_select}')

    # Audio configuration parameters
    config_params = {
        'speaking_rate': args.speaking_rate,
        'pitch': args.pitch,
        'volume_gain_db': args.volume_gain_db,
    }

    match args.outfile[-3:].upper():
        case 'MP3' | '-':
            # Generate an mp3 file for the mpv player
            config_params['audio_encoding'] = texttospeech.AudioEncoding.MP3
        case 'WAV':
            config_params['audio_encoding'] = texttospeech.AudioEncoding.LINEAR16
        case 'OGG':
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

    # Create three <voice> elements for each Russian word/phrase
    # to synthesize voices in Russian A and B and in English.
    #
    #  <voice name="ru-RU-Wavenet-A">Каша<break time="650ms"/></voice>
    #  <voice name="ru-RU-Wavenet-B">Каша<break time="1200ms"/></voice>
    #  <voice name="en-US-Standard-C">Porridge<break time="1200ms"/></voice>

    # Initialize the XML root element
    elem_root = ET.Element('speak')

    # For each Russian text/translation generate three voice elements
    for rus, eng in texts:

        elem_voice = ET.Element('voice', attrib={'name': VOICE_RUSSIAN_A})
        elem_voice.text = rus
        elem_voice.append(ET.Element('break', attrib={'time': BREAK_RUSSIAN_A}))
        elem_root.append(elem_voice)

        elem_voice = ET.Element('voice', attrib={'name': VOICE_RUSSIAN_B})
        elem_voice.text = rus
        elem_voice.append(ET.Element('break', attrib={'time': BREAK_RUSSIAN_B}))
        elem_root.append(elem_voice)

        elem_voice = ET.Element('voice', attrib={'name': VOICE_ENGLISH})
        elem_voice.text = eng
        elem_voice.append(ET.Element('break', attrib={'time': BREAK_ENGLISH}))
        elem_root.append(elem_voice)

    if args.verbose:
        # Expand XML for pretty print
        ET.indent(elem_root, space="  ")

    xml = ET.tostring(elem_root,
                      encoding='unicode',
                      method='xml',
                      xml_declaration=True)

    if args.verbose:
        print(xml + '\n')

    response = tts_client.synthesize_speech(
        input=texttospeech.SynthesisInput(mapping={'ssml': xml}),
        voice=voice_select,
        audio_config=audio_config)

    if args.outfile == '-':
        # Pipe the audio data to the mpv player
        proc = subprocess.Popen(MPV_EXEC,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)

        print("Playing results...  ", end='', flush=True)
        proc_out = proc.communicate(input=response.audio_content)
        stderr = proc_out[1]

        print("Done.")

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
    parser.add_argument("outfile",
                        help="audio output file or '-' to send to player")
    # Options
    parser.add_argument("--speaking_rate", type=float,
                        help="speaking rates between 0.25 and 4.0")
    parser.add_argument("--pitch", type=int,
                        help="pitch between -20 and +20 (semitones)")
    parser.add_argument("--volume_gain_db", type=int,
                        help="volume between -96 and +16 (decibels)")
    # Debugging
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="increase diagnostic output")
    args = parser.parse_args()

    if args.verbose:
        print(f'\nCommand line arguments:\n{args}\n')

    make_lesson(args)


